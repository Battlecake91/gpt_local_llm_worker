import pytest
from pydantic import ValidationError

from gpt_local_llm_worker.contracts import SSHBatch
from gpt_local_llm_worker.store import Store


def example():
    return {"schema_version": 1, "kind": "ssh_batch", "request_id": "req-1",
            "target": "nas", "working_directory": "/tmp", "description": "Read only",
            "commands": [{"id": "one", "command": "uname -a"}]}


def test_digest_stable():
    batch = SSHBatch.model_validate(example())
    assert batch.approval_digest() == SSHBatch.model_validate(example()).approval_digest()


def test_duplicate_command_ids_rejected():
    data = example()
    data["commands"].append(data["commands"][0])
    with pytest.raises(ValidationError):
        SSHBatch.model_validate(data)


def test_approval_is_single_use(tmp_path):
    store = Store(tmp_path / "state.db")
    batch = SSHBatch.model_validate(example())
    proposed = store.propose(batch)
    assert store.decide(batch.request_id, proposed["digest"], True)["state"] == "APPROVED"
    with pytest.raises(ValueError):
        store.decide(batch.request_id, proposed["digest"], True)


def test_request_id_cannot_be_reused_with_modified_command(tmp_path):
    store = Store(tmp_path / "state.db")
    store.propose(SSHBatch.model_validate(example()))
    data = example()
    data["commands"][0]["command"] = "id"
    with pytest.raises(ValueError):
        store.propose(SSHBatch.model_validate(data))


def test_running_recovery_requires_reconciliation(tmp_path):
    store = Store(tmp_path / "state.db")
    store.propose(SSHBatch.model_validate(example()))
    store.db.execute("UPDATE batches SET state='RUNNING'")
    store.db.commit()
    store.recover()
    assert store.get("req-1")["state"] == "UNKNOWN"
