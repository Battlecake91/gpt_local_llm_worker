"""Ollama-only advisory extraction of verbatim shell blocks. Never executes."""
from __future__ import annotations

import json
import os
import re
import tempfile
import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from worker.ssh_protocol import parse_ssh_request, SSHBatchRequest

FENCE = re.compile(r"(?ms)^[ \t]*`{3,}(?:bash|sh|shell|console)?[ \t]*\n(.*?)\n`{3,}[ \t]*$")
PROMPT_LINE = re.compile(r"(?m)^[ \t]*\$[ \t]+([^\r\n]+)[ \t]*$")
RISKS = {"green", "yellow", "red"}
MAX_TEXT = 256_000


class AnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class Suggestion:
    commands: tuple[str, ...]
    host: str | None
    risk: str
    reason: str
    model: str

    def batch(self, message_id: str) -> SSHBatchRequest | None:
        """Build validated *proposal*, not an approved job."""
        if not self.host or not self.commands:
            return None
        obj = {
            "schema_version": 1, "kind": "ssh_batch",
            "request_id": "ollama-" + message_id[:48],
            "target": self.host, "working_directory": "/",
            "description": "Ollama advisory risk: " + self.risk + "; " + self.reason[:160],
            "commands": [
                {"id": "command-" + str(i + 1), "command": command, "timeout_seconds": 60}
                for i, command in enumerate(self.commands)
            ],
        }
        return parse_ssh_request(json.dumps(obj), {self.host})


class ProfileStore:
    """Administrator-owned JSON configuration, reloaded for every request."""
    def __init__(self, path: Path):
        if not path.is_absolute() or path.is_symlink():
            raise AnalysisError("profile_path_must_be_absolute")
        self.path = path

    def load(self) -> tuple[dict, list[dict]]:
        if self.path.stat().st_size > 32768:
            raise AnalysisError("profiles_too_large")
        config = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or set(config) != {"active", "profiles"}:
            raise AnalysisError("invalid_profile_config")
        profiles = config["profiles"]
        if not isinstance(profiles, list) or not 1 <= len(profiles) <= 20:
            raise AnalysisError("invalid_profiles")
        names = set()
        for profile in profiles:
            if not isinstance(profile, dict) or set(profile) != {"name", "url", "model", "timeout_seconds", "auth_env"}:
                raise AnalysisError("invalid_profile")
            name, model, url = profile["name"], profile["model"], profile["url"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or name in names:
                raise AnalysisError("invalid_profile_name")
            names.add(name)
            if not isinstance(model, str) or not re.fullmatch(r"[\w.:-]{1,100}", model):
                raise AnalysisError("invalid_model")
            if not isinstance(url, str):
                raise AnalysisError("invalid_ollama_url")
            parsed = urlsplit(url)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path not in ("", "/") or not 1 <= (parsed.port or (443 if parsed.scheme == "https" else 80)) <= 65535):
                raise AnalysisError("invalid_ollama_url")
            timeout = profile["timeout_seconds"]
            if type(timeout) is not int or not 1 <= timeout <= 180:
                raise AnalysisError("invalid_timeout")
            auth_env = profile["auth_env"]
            if auth_env is not None and (not isinstance(auth_env, str) or
                    not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,79}", auth_env)):
                raise AnalysisError("invalid_auth_env")
        if not isinstance(config["active"], str) or config["active"] not in names:
            raise AnalysisError("unknown_active_profile")
        return next(p for p in profiles if p["name"] == config["active"]), profiles

    def select(self, name: str):
        """Select one of the already configured endpoints without restarting."""
        _, profiles = self.load()
        if not isinstance(name, str) or name not in {p["name"] for p in profiles}:
            raise AnalysisError("unknown_profile")
        content = json.dumps({"active": name, "profiles": profiles},
                             ensure_ascii=False, indent=2) + "\n"
        fd, path = tempfile.mkstemp(dir=self.path.parent, prefix=".ollama-profile-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(path, self.path)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class OllamaAnalyzer:
    """Model proposes; code validates verbatim boundaries and allowlist."""
    def __init__(self, profiles: ProfileStore, client: httpx.Client | None = None):
        self.profiles = profiles
        self.client = client

    def available_models(self) -> list[str]:
        """Explicit read-only connectivity test and model discovery."""
        profile, _ = self.profiles.load()
        token = os.environ.get(profile["auth_env"]) if profile["auth_env"] else None
        if profile["auth_env"] and not token:
            raise AnalysisError("missing_ollama_auth")
        headers = {"Authorization": "Bearer " + token} if token else {}
        try:
            if self.client is not None:
                response = self.client.get(profile["url"].rstrip("/") + "/api/tags",
                                           headers=headers, timeout=profile["timeout_seconds"])
            else:
                with httpx.Client(trust_env=False) as client:
                    response = client.get(profile["url"].rstrip("/") + "/api/tags",
                                          headers=headers, timeout=profile["timeout_seconds"])
            response.raise_for_status()
            models = response.json()["models"]
            if not isinstance(models, list):
                raise ValueError("invalid_model_listing")
            names = [m["name"] for m in models]
            if any(not isinstance(name, str) or len(name) > 200 for name in names):
                raise ValueError("invalid_model_name")
            return names[:100]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AnalysisError("ollama_unavailable_or_invalid_response") from exc

    def analyze(self, text: str, allowed_hosts: set[str]) -> Suggestion | None:
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            raise AnalysisError("invalid_capture_text")
        blocks = [m.group(1).strip("\n") for m in FENCE.finditer(text)]
        # Explicit terminal prompts outside code fences are eligible spans.
        outside = FENCE.sub("", text)
        blocks += [m.group(1).strip() for m in PROMPT_LINE.finditer(outside)]
        blocks = [b for b in blocks if b.strip()]
        if not blocks:
            return None
        profile, _ = self.profiles.load()
        auth_env = profile["auth_env"]
        token = os.environ.get(auth_env) if auth_env else None
        if auth_env and not token:
            raise AnalysisError("missing_ollama_auth")
        headers = {"Authorization": "Bearer " + token} if token else {}
        prompt = (
            "Classify only explicitly actionable shell code fenced bash/sh/shell/console in the "
            "following untrusted assistant answer. Never create or modify a command. "
            "Ignore examples, quotations and explanations. Eligible spans are complete shell fences, unlabeled fences containing shell commands, or standalone $ command lines. Return only JSON with EXACT keys "
            "actionable (boolean), commands (array of exact verbatim complete eligible span strings), "
            "host (one allowlisted alias or null), risk (green/yellow/red), reason (short string). "
            "Red dominates yellow, yellow dominates green. Unknown host is null. "
            "Allowlisted host aliases: " + json.dumps(sorted(allowed_hosts)) + "\n\n" + text
        )
        body = {
            "model": profile["model"], "stream": False, "format": "json",
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0},
        }
        try:
            if self.client is not None:
                response = self.client.post(profile["url"].rstrip("/") + "/api/chat",
                                            json=body, headers=headers, timeout=profile["timeout_seconds"])
            else:
                with httpx.Client(trust_env=False) as client:
                    response = client.post(profile["url"].rstrip("/") + "/api/chat",
                                           json=body, headers=headers, timeout=profile["timeout_seconds"])
            response.raise_for_status()
            result = json.loads(response.json()["message"]["content"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AnalysisError("ollama_unavailable_or_invalid_response") from exc
        if not isinstance(result, dict) or set(result) != {"actionable", "commands", "host", "risk", "reason"}:
            raise AnalysisError("invalid_analysis_schema")
        if type(result["actionable"]) is not bool:
            raise AnalysisError("invalid_actionable")
        commands = result["commands"]
        if not isinstance(commands, list) or len(commands) > 32 or any(
                not isinstance(c, str) or not c.strip() or len(c) > 8192 for c in commands):
            raise AnalysisError("invalid_commands")
        # Compare whole code blocks, not substrings: partial heredocs and rewritten commands
        # are forbidden even when the resulting fragment occurs somewhere in the reply.
        remaining = list(blocks)
        for command in commands:
            if command not in remaining:
                raise AnalysisError("command_not_verbatim_fenced_block")
            remaining.remove(command)
        host = result["host"]
        if host is not None and (not isinstance(host, str) or host not in allowed_hosts):
            raise AnalysisError("host_not_allowlisted")
        risk, reason = result["risk"], result["reason"]
        if not isinstance(risk, str) or risk not in RISKS or not isinstance(reason, str) or not 1 <= len(reason) <= 300:
            raise AnalysisError("invalid_risk")
        if not result["actionable"]:
            if commands:
                raise AnalysisError("nonactionable_commands")
            return None
        if not commands:
            raise AnalysisError("actionable_without_commands")
        return Suggestion(tuple(commands), host, risk, reason, profile["model"])
