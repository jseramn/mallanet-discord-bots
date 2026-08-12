from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _opt(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    guild_id: int
    role_verificado: int
    role_pendiente: int
    role_mallanet: int
    role_root: int
    channel_reglas: int
    channel_verificacion: int
    channel_bot_admin: int
    channel_logs: int
    approver_role_ids: frozenset[int]

    @classmethod
    def from_env(cls) -> "Settings":
        approvers = {
            int(x)
            for x in _opt(
                "APPROVER_ROLE_IDS",
                f"{_req('ROLE_ROOT')},{_req('ROLE_MALLANET')}",
            ).split(",")
            if x.strip()
        }
        return cls(
            guild_id=int(_req("GUILD_ID")),
            role_verificado=int(_req("ROLE_VERIFICADO")),
            role_pendiente=int(_req("ROLE_PENDIENTE")),
            role_mallanet=int(_req("ROLE_MALLANET")),
            role_root=int(_req("ROLE_ROOT")),
            channel_reglas=int(_req("CHANNEL_REGLAS")),
            channel_verificacion=int(_req("CHANNEL_VERIFICACION")),
            channel_bot_admin=int(_req("CHANNEL_BOT_ADMIN")),
            channel_logs=int(_req("CHANNEL_LOGS")),
            approver_role_ids=frozenset(approvers),
        )


def onboard_token() -> str:
    return _req("ONBOARD_TOKEN")


def watch_token() -> str:
    return _req("WATCH_TOKEN")
