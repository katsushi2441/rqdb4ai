import os
from dataclasses import dataclass
from typing import Iterable

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class TokenIdentity:
    role: str

    def can(self, required: str) -> bool:
        order = {"read": 1, "operate": 2, "admin": 3}
        return order.get(self.role, 0) >= order.get(required, 99)


def _split_tokens(value: str) -> Iterable[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _token_map() -> dict[str, str]:
    tokens: dict[str, str] = {}
    for role, env_name in (
        ("read", "RQDB4AI_READ_TOKEN"),
        ("operate", "RQDB4AI_OPERATE_TOKEN"),
        ("admin", "RQDB4AI_ADMIN_TOKEN"),
    ):
        for token in _split_tokens(os.environ.get(env_name, "")):
            tokens[token] = role

    shared = os.environ.get("RQDB4AI_API_TOKEN", "").strip()
    if shared:
        tokens[shared] = os.environ.get("RQDB4AI_API_TOKEN_ROLE", "admin").strip() or "admin"

    return tokens


def require_identity(authorization: str | None = Header(default=None)) -> TokenIdentity:
    tokens = _token_map()
    if not tokens:
        raise HTTPException(status_code=503, detail="RQDB4AI token is not configured")

    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization[len(prefix):].strip()
    role = tokens.get(token)
    if not role:
        raise HTTPException(status_code=403, detail="Invalid bearer token")

    return TokenIdentity(role=role)


def require_role(identity: TokenIdentity, role: str) -> None:
    if not identity.can(role):
        raise HTTPException(status_code=403, detail=f"{role} role required")
