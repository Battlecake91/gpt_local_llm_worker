from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    command: str = Field(min_length=1, max_length=4096)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class SSHBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    kind: Literal["ssh_batch"]
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    target: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    working_directory: str = Field(min_length=1, max_length=1024)
    commands: list[Command] = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=2048)

    @field_validator("commands")
    @classmethod
    def unique_ids(cls, commands: list[Command]) -> list[Command]:
        if len({command.id for command in commands}) != len(commands):
            raise ValueError("duplicate command id")
        return commands

    def approval_digest(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()
