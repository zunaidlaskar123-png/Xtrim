"""Shared Premium entitlement helpers for Xtrim."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from discord.ext import commands

from utils.config import BotName

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "premium.json")


def _ensure_store() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)


def _load() -> dict:
    _ensure_store()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _ensure_store()
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)


def premium_entry(guild_id: int) -> Optional[dict]:
    data = _load()
    entry = data.get(str(guild_id))
    if not isinstance(entry, dict):
        return None

    expires = entry.get("expires_at")
    if expires:
        try:
            expiry = datetime.fromisoformat(expires)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                data.pop(str(guild_id), None)
                _save(data)
                return None
        except ValueError:
            return None
    return entry


def is_premium(guild_id: int) -> bool:
    return premium_entry(guild_id) is not None


def premium_check():
    """Decorator requiring the current server to have an active Premium entitlement."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("Premium features are only available in servers.")
        if not is_premium(ctx.guild.id):
            raise commands.CheckFailure(
                f"💎 **{BotName} Premium**\n"
                "This server is on the Free tier.\n"
                "Ask the bot owner to enable Premium for this server."
            )
        return True
    return commands.check(predicate)


def premium_remaining(guild_id: int) -> Optional[timedelta]:
    entry = premium_entry(guild_id)
    if not entry:
        return None
    expires = entry.get("expires_at")
    if not expires:
        return None
    expiry = datetime.fromisoformat(expires)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry - datetime.now(timezone.utc)


def premium_data() -> dict:
    """Return the raw entitlement store for owner/admin views."""
    return _load()


def save_premium_data(data: dict) -> None:
    _save(data)
