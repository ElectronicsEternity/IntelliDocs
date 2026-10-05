"""Private retention maintenance; never deletes usage or financial ledgers."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil

from app.config import settings
from app.database.connection import get_connection

logger = logging.getLogger(__name__)


def _linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _debug_files(root: Path):
    # Inspect only the date folders created by AnswerDebugCapture. Never follow
    # junctions/symlinks, or recursively walk an arbitrary configured directory.
    if not root.is_dir() or _linked(root):
        return
    for folder in root.iterdir():
        if _linked(folder) or not folder.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name):
            continue
        for path in folder.iterdir():
            if (not _linked(path) and path.is_file()
                    and re.fullmatch(r"\d{8}-\d{6}_[0-9a-fA-F-]{36}\.json(?:\.tmp)?", path.name)):
                yield path


def _payload(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}


def purge_debug_files(*, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.DEBUG_RETENTION_DAYS)
    removed = 0
    for path in _debug_files(settings.RAG_DEBUG_CAPTURE_DIRECTORY):
        try:
            payload = _payload(path)
            # Creation time, not finish time; corrupt/unfinished captures use
            # last modification time as a conservative fallback.
            try:
                created = datetime.fromisoformat(payload["started_at"])
                if created.tzinfo is None:
                    raise ValueError("Missing timezone")
            except (KeyError, TypeError, ValueError):
                created = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if created < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            logger.warning("retention_debug_file_failed", exc_info=False)
    return removed


def purge_chat_records(*, now: datetime | None = None) -> dict:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.CHAT_RETENTION_DAYS)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '30s'")
        cur.execute("SET LOCAL lock_timeout = '5s'")
        cur.execute("DELETE FROM messages WHERE created_at < %s", (cutoff,))
        messages = cur.rowcount
        # Never cascade-delete a conversation containing newer messages.
        # updated_at protects an empty conversation with an in-flight request.
        cur.execute("""
            DELETE FROM conversations c
            WHERE c.created_at < %s AND c.updated_at < %s
              AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
        """, (cutoff, cutoff))
        conversations = cur.rowcount
    return {"messages": messages, "conversations": conversations}


def remove_document_support(user_id: str, document_id: str) -> None:
    # Use the same folder-name mapping as the extraction/checkpoint writers.
    def segment(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"

    root = settings.DOCUMENT_PROFILES_DIRECTORY.absolute()
    owner = root / segment(user_id)
    target = owner / segment(document_id)
    if any(_linked(path) for path in (root, owner, target)):
        raise ValueError("Refusing linked document cache directory")
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    # Check the exact resolved target before any recursive deletion.
    if not resolved_target.is_relative_to(resolved_root) or len(resolved_target.relative_to(resolved_root).parts) != 2:
        raise ValueError("Invalid document cache directory")
    if target.exists():
        # Refuse linked descendants, including Windows junctions.
        for folder, dirs, files in os.walk(target, followlinks=False):
            if any(_linked(Path(folder) / name) for name in dirs + files):
                raise ValueError("Refusing linked document cache contents")
        shutil.rmtree(resolved_target)
    # Captures contain verbatim supporting document text. Remove whole matching
    # captures (not just excerpts), while restricting removal to this owner.
    for path in _debug_files(settings.RAG_DEBUG_CAPTURE_DIRECTORY):
        payload = _payload(path)
        if payload.get("user_id") != user_id:
            continue
        if any(str(chunk.get("document_id")) == document_id for chunk in payload.get("chunks", []) if isinstance(chunk, dict)):
            path.unlink(missing_ok=True)


def run_cleanup() -> None:
    # Independent stages: unavailable DB must not stop local file expiry.
    for name, action in (("chat", purge_chat_records), ("debug", purge_debug_files)):
        try:
            logger.info("retention_cleanup stage=%s removed=%s", name, action())
        except Exception:
            # Log no prompts, SQL parameters, credentials or exception bodies.
            logger.error("retention_cleanup_failed stage=%s", name)


async def retention_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(run_cleanup)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.RETENTION_CLEANUP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
