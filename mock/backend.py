"""Isolated loopback test adapter. Never executes SSH or grants approval from text."""
import os
from dataclasses import dataclass, field
from typing import Literal
import hashlib
import re
from threading import Lock
from pathlib import Path
from functools import lru_cache
from worker.ssh_protocol import parse_ssh_request, InvalidSSHRequest
from worker.approval_state import ApprovalStore, ApprovalStateError
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

class ApprovalBinding(BaseModel):
    job_id: str
    approval_id: str
    host_id: str
    command_sha256: str
    result_sha256: str

class Outbound(BaseModel):
    id: str
    conversation_id: str
    tab_id: int
    mode: Literal["STAGE_ONLY", "AUTO_SEND_APPROVED_RESULT"]
    text: str
    approval: ApprovalBinding | None = None
    # Internal fixture marker; the API cannot create approvals from received text.
    approved_ssh_result: bool = False
    claim_id: str | None = None
    status: str = "PENDING"

class ClaimRequest(BaseModel):
    conversation_id: str
    tab_id: int
    job_id: str | None = None
    approval_id: str | None = None
    result_sha256: str | None = None

class Ack(BaseModel):
    status: Literal["STAGED", "SUBMIT_CLICKED", "ERROR", "UNKNOWN"]
    error: str | None = None
    claim_id: str | None = None

@dataclass
class Database:
    captures: dict = field(default_factory=dict)
    outbound: dict = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

db = Database()


def require_token(authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Unauthorized")

@lru_cache(maxsize=8)
def approval_store(path: str) -> ApprovalStore:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return ApprovalStore(path)


def configured_approval_store() -> ApprovalStore | None:
    """Approval preview is disabled unless explicitly configured for local fixtures."""
    db_path = os.environ.get("BRIDGE_APPROVAL_DB")
    if not db_path:
        return None
    return approval_store(str(Path(db_path).resolve()))


def allowed_hosts() -> set[str]:
    return {host.strip() for host in os.environ.get("BRIDGE_ALLOWED_HOSTS", "").split(",") if host.strip()}


class ReviewDecision(BaseModel):
    command_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]
    conversation_id: str
    tab_id: int


@app.get('/api/bridge/v1/ssh/proposals', dependencies=[Depends(require_token)] )
def list_proposals():
    store = configured_approval_store()
    return {"items": [] if store is None else store.pending()}


@app.post('/api/bridge/v1/ssh/proposals/{request_id}/approve', dependencies=[Depends(require_token)])
def approve_proposal(request_id: str, decision: ReviewDecision):
    store = configured_approval_store()
    if store is None:
        raise HTTPException(403, "Approval review not configured")
    proposal = store.get(request_id)
    if proposal is None or proposal["status"] != "PROPOSED" or proposal["conversation_id"] != decision.conversation_id or proposal["tab_id"] != decision.tab_id:
        raise HTTPException(409, "Origin or state changed")
    if proposal["command_sha256"] != decision.command_sha256:
        raise HTTPException(409, "Proposal digest changed")
    try:
        # This is a mock-only UI decision record, NOT permission to execute SSH or auto-send.
        store.approve(request_id, command_sha256=decision.command_sha256,
                      authenticated_operator="mock-sidepanel-confirmation")
    except ApprovalStateError:
        raise HTTPException(409, "Proposal already decided")
    return {"status": "APPROVED_FOR_MOCK_REVIEW", "request_id": request_id}


@app.post('/api/bridge/v1/ssh/proposals/{request_id}/reject', dependencies=[Depends(require_token)])
def reject_proposal(request_id: str, decision: ReviewDecision):
    store = configured_approval_store()
    if store is None:
        raise HTTPException(403, "Approval review not configured")
    proposal = store.get(request_id)
    if proposal is None or proposal["status"] != "PROPOSED" or proposal["command_sha256"] != decision.command_sha256 or (
        proposal["conversation_id"] != decision.conversation_id or proposal["tab_id"] != decision.tab_id
    ):
        raise HTTPException(409, "Proposal changed")
    try:
        store.reject(request_id)
    except ApprovalStateError:
        raise HTTPException(409, "Proposal already decided")
    return {"status": "REJECTED", "request_id": request_id}

@app.post('/api/bridge/v1/captures', dependencies=[Depends(require_token)])
def capture(data: Capture):
    if data.message_id in db.captures:
        return {"message_id":data.message_id,"status":"duplicate"}
    store = configured_approval_store()
    hosts = allowed_hosts()
    if store is not None and hosts:
        try:
            proposal = parse_ssh_request(data.text, hosts)
            store.propose(proposal, tab_id=data.tab_id, conversation_id=data.conversation_id)
        except InvalidSSHRequest:
            pass  # Not an eligible explicit SSH request.
        except ApprovalStateError:
            # Request-ID collisions are never silently approved.
            raise HTTPException(409, "SSH proposal request-ID collision")
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
    with db.lock:
        msg=db.outbound.get(id)
        if not msg or msg.status != 'PENDING' or msg.mode!='AUTO_SEND_APPROVED_RESULT' or not msg.approved_ssh_result:
            raise HTTPException(403,'Not approved')
        if msg.conversation_id!=request.conversation_id or msg.tab_id!=request.tab_id:
            raise HTTPException(409,'Conversation mismatch')
        binding=msg.approval
        # A fixture flag alone is never enough to approve an outbound browser send.
        if not binding:
            raise HTTPException(403,'Missing immutable job binding')
        expected={'job_id':binding.job_id,'approval_id':binding.approval_id,
                  'host_id':binding.host_id,'command_sha256':binding.command_sha256,
                  'result_sha256':binding.result_sha256}
        if not all(re.fullmatch(r'[A-Za-z0-9._:-]{1,160}',v) for v in
                   (binding.job_id,binding.approval_id,binding.host_id)):
            raise HTTPException(403,'Invalid job binding')
        if not all(re.fullmatch(r'[0-9a-f]{64}',v) for v in
                   (binding.command_sha256,binding.result_sha256)):
            raise HTTPException(403,'Invalid digest binding')
        if hashlib.sha256(msg.text.encode('utf-8')).hexdigest()!=binding.result_sha256:
            raise HTTPException(403,'Result content has changed')
        if request.job_id!=binding.job_id or request.approval_id!=binding.approval_id or request.result_sha256!=binding.result_sha256:
            raise HTTPException(403,'Claim request mismatch')
        if msg.claim_id is not None:
            raise HTTPException(409,'Already claimed')
        # An approval claim is intentionally one-time, including for a failed browser attempt.
        from secrets import token_urlsafe
        msg.claim_id=token_urlsafe(24)
        msg.status='CLAIMED'
        return {"allowed":True,"claim_id":msg.claim_id,"kind":"approved_ssh_result",
                "outbound_id":id,"conversation_id":msg.conversation_id,"tab_id":msg.tab_id,
                **expected}

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
