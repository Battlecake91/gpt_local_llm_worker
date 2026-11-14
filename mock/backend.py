"""Isolated loopback test adapter. Never executes SSH or grants approval from text."""
import os
from dataclasses import dataclass, field
from typing import Literal
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

TOKEN = os.environ.get("BRIDGE_MOCK_TOKEN", "mock-test-token")
app = FastAPI(docs_url=None, redoc_url=None)
# Browser extension IDs vary. Require the operator to configure the exact origin.
origin = os.environ.get("BRIDGE_EXTENSION_ORIGIN")
if origin:
    app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type"])

class Capture(BaseModel):
    schema_version: Literal[1]
    message_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    conversation_id: str
    tab_id: int
    text: str
    observed_at: str

class Outbound(BaseModel):
    id: str
    conversation_id: str
    tab_id: int
    mode: Literal["STAGE_ONLY", "AUTO_SEND_APPROVED_RESULT"]
    text: str
    # Internal fixture marker; the API cannot create approvals from received text.
    approved_ssh_result: bool = False
    claim_id: str | None = None
    status: str = "PENDING"

class ClaimRequest(BaseModel):
    conversation_id: str
    tab_id: int

class Ack(BaseModel):
    status: Literal["STAGED", "SUBMIT_CLICKED", "ERROR", "UNKNOWN"]
    error: str | None = None
    claim_id: str | None = None

@dataclass
class Database:
    captures: dict = field(default_factory=dict)
    outbound: dict = field(default_factory=dict)

db = Database()

def require_token(authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Unauthorized")

@app.post('/api/bridge/v1/captures', dependencies=[Depends(require_token)])
def capture(data: Capture):
    if data.message_id in db.captures:
        return {"message_id":data.message_id,"status":"duplicate"}
    db.captures[data.message_id] = data
    return {"message_id":data.message_id,"status":"accepted"}

@app.get('/api/bridge/v1/outbound', dependencies=[Depends(require_token)])
def outbound():
    return {"items":[v.model_dump(exclude={"approved_ssh_result", "claim_id", "status"}) for v in db.outbound.values() if v.status == "PENDING"]}

class StageFixture(BaseModel):
    id: str
    conversation_id: str
    tab_id: int
    text: str

@app.post('/api/bridge/v1/mock/enqueue-stage', dependencies=[Depends(require_token)])
def enqueue_stage(data: StageFixture):
    if os.environ.get('BRIDGE_MOCK_FIXTURES') != '1':
        raise HTTPException(404, 'Mock fixture endpoint disabled')
    if data.id in db.outbound:
        raise HTTPException(409, 'Duplicate message id')
    db.outbound[data.id] = Outbound(**data.model_dump(), mode='STAGE_ONLY')
    return {'status':'queued','id':data.id}

@app.post('/api/bridge/v1/outbound/{id}/claim', dependencies=[Depends(require_token)])
def claim(id: str, request: ClaimRequest):
    msg=db.outbound.get(id)
    if not msg or msg.status != 'PENDING' or msg.mode!='AUTO_SEND_APPROVED_RESULT' or not msg.approved_ssh_result:
        raise HTTPException(403,'Not approved')
    if msg.conversation_id!=request.conversation_id or msg.tab_id!=request.tab_id:
        raise HTTPException(409,'Conversation mismatch')
    if msg.claim_id is not None:
        raise HTTPException(409,'Already claimed')
    # An approval claim is intentionally one-time, including for a failed browser attempt.
    from secrets import token_urlsafe
    msg.claim_id=token_urlsafe(24)
    msg.status='CLAIMED'
    return {"allowed":True,"claim_id":msg.claim_id,"kind":"approved_ssh_result"}

@app.post('/api/bridge/v1/outbound/{id}/ack', dependencies=[Depends(require_token)])
def ack(id: str, receipt: Ack):
    msg=db.outbound.get(id)
    if msg is None:raise HTTPException(404,'Unknown outbound message')
    if msg.mode=='AUTO_SEND_APPROVED_RESULT' and (not msg.claim_id or receipt.claim_id!=msg.claim_id):
        raise HTTPException(403,'Wrong claim')
    if msg.status not in ('PENDING','CLAIMED'):
        return {"status":"duplicate"}
    msg.status=receipt.status
    return {"status":"accepted"}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8765)
