from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .contracts import SSHBatch
from .store import Store


class Decision(BaseModel):
    digest: str
    approve: bool


def create_app(db_path: str | Path, token: str, allowed_targets: set[str]) -> FastAPI:
    if len(token) < 32:
        raise ValueError("A random token of at least 32 characters is required")
    app = FastAPI(title="GPT Local LLM Worker", docs_url=None, redoc_url=None)
    store = Store(db_path)
    store.recover()

    def authenticate(authorization: str = Header(default="")) -> None:
        import hmac
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    def health(_: None = Depends(authenticate)):
        return {"status": "ok", "mode": "dry-run"}

    @app.post("/batches", status_code=201)
    def propose(batch: SSHBatch, _: None = Depends(authenticate)):
        if batch.target not in allowed_targets:
            raise HTTPException(403, "Target not allowlisted")
        try:
            row = store.propose(batch)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"request_id": row["request_id"], "digest": row["digest"], "state": row["state"]}

    @app.get("/batches/{request_id}")
    def get_batch(request_id: str, _: None = Depends(authenticate)):
        try:
            return store.get(request_id)
        except KeyError as exc:
            raise HTTPException(404, "Not found") from exc

    @app.post("/batches/{request_id}/decision")
    def decide(request_id: str, decision: Decision, _: None = Depends(authenticate)):
        try:
            row = store.decide(request_id, decision.digest, decision.approve)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"request_id": row["request_id"], "state": row["state"]}

    return app


def run() -> None:
    import uvicorn
    token = os.environ["GPT_WORKER_TOKEN"]
    targets = {t.strip() for t in os.getenv("GPT_WORKER_TARGETS", "").split(",") if t.strip()}
    db_path = os.getenv("GPT_WORKER_DB", str(Path.home() / ".local/state/gpt-local-llm-worker/state.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(db_path, token, targets), host="127.0.0.1", port=8765)


if __name__ == "__main__":
    run()
