"""
tasks — Coordination substrate v0.1 reference implementation.

Provides a typed state machine for work allocation without a central coordinator.
Tasks are signed observations with state tracked across multiple writers via
first-valid-write semantics.

Public API:
  - assign(content, to, priority, estimate, depends_on, topic, rationale, task_id)
  - claim(task_id, rationale)
  - progress(task_id, note)
  - release(task_id, rationale)
  - complete(task_id, result, artifact_cid)
  - cancel(task_id, rationale)  [assigner-only]
  - block(task_id, on)
  - unblock(task_id)
  - open_tasks(to)
  - my_tasks(handle)
  - task_history(task_id)
  - mesh_status(handle)
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import from sibling dotpost module.
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
from dotpost.identity import load_or_generate, load_pubkey, pubkey_hex
from dotpost.canonical import canonicalize
from dotpost.transport import tool_call, load_token

logger = logging.getLogger(__name__)

# Task state constants (tag names).
STATE_OPEN = "task:open"
STATE_CLAIMED = "task:claimed"
STATE_BLOCKED = "task:blocked"
STATE_RESUMED = "task:resumed"
STATE_RELEASED = "task:released"
STATE_PROGRESS = "task:progress"
STATE_DONE = "task:done"
STATE_CANCELLED = "task:cancelled"
STATE_REASSIGNED = "task:reassigned"

TERMINAL_STATES = {STATE_DONE, STATE_CANCELLED}
ACTIVE_STATES = {STATE_CLAIMED, STATE_BLOCKED, STATE_RESUMED}


@dataclass
class _CoordRecord:
    """Represents a task's current state (the latest observation for a given task_id)."""
    task_id: str
    obs_id: str
    content: str
    state: str
    tags: list[str]
    assigner: str
    claimer: str | None = None
    priority: str = "p2"
    estimate: int | None = None
    created_at: str = ""
    rationale: str | None = None
    blocked_on: str | None = None
    result: str | None = None
    artifact_cid: str | None = None


# Public alias — spec terminology.
Task = _CoordRecord


def _get_current_handle() -> str:
    """Return the current handle from env or state file.

    Resolution order:
      1. $PIPERNET_HANDLE environment variable
      2. File at $PIPERNET_HOME/handle (defaults to a Pipernet config dir)
      3. Fallback default: 'anonymous'
    """
    handle = os.getenv("PIPERNET_HANDLE")
    if not handle:
        home = os.getenv("PIPERNET_HOME") or str(Path.home() / ".pipernet")
        handle_file = Path(home) / "handle"
        if handle_file.exists():
            handle = handle_file.read_text().strip()
        else:
            handle = "anonymous"
    return handle


def _gen_task_id(content: str) -> str:
    """Generate a task_id slug from content (first few words, kebab-cased)."""
    words = content.lower().split()[:3]
    slug = "-".join(w for w in words if w.isalnum())[:48]
    return f"T-{slug}" if slug else "T-task"


def _utcnow_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sign_observation(
    content: str,
    tags: list[str],
    rationale: str | None = None,
    in_reply_to: str | None = None,
    handle: str | None = None,
) -> dict[str, Any]:
    """Build and sign an observation dict for writing to Oracle.

    Returns a dict ready for oracle_ingest (write_observation call).
    """
    if handle is None:
        handle = _get_current_handle()

    priv, pubkey_bytes, _ = load_or_generate(handle)

    # Build the observation body (canonical).
    obs_body = {
        "type": "task",
        "content": content,
        "created_at": _utcnow_iso(),
        "tags": tags,
    }
    if rationale:
        obs_body["rationale"] = rationale
    if in_reply_to:
        obs_body["in_reply_to"] = in_reply_to

    # Sign it.
    canonical = canonicalize(obs_body)
    from dotpost.identity import sign
    sig_bytes = sign(priv, canonical)

    # Build the final observation for ingest.
    obs = {
        "type": "task",
        "content": content,
        "tags": tags,
    }
    if rationale:
        obs["rationale"] = rationale
    if in_reply_to:
        obs["in_reply_to"] = in_reply_to

    # Add signature as tags (b64url-encoded).
    import base64
    sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
    pub_b64 = base64.urlsafe_b64encode(pubkey_bytes).rstrip(b"=").decode("ascii")
    obs["tags"].append(f"ed25519_sig:{sig_b64}")
    obs["tags"].append(f"pubkey:{pub_b64}")

    return obs


def assign(
    content: str,
    to: str = "all",
    priority: str = "p2",
    estimate: int | None = None,
    depends_on: list[str] | None = None,
    topic: str | None = None,
    rationale: str | None = None,
    task_id: str | None = None,
) -> tuple[str, str]:
    """Create a task. Returns (obs_id, task_id).

    Parameters:
      content: one-line task summary (human-readable)
      to: "all" (open call) or a specific handle (direct assignment)
      priority: p0, p1, p2, p3
      estimate: estimated minutes to complete (optional)
      depends_on: list of task_ids this depends on (optional)
      topic: free-form topic tag for discovery (optional)
      rationale: why this task matters (optional)
      task_id: explicit task_id (optional; auto-generated if not provided)

    Returns:
      (obs_id, task_id) tuple for reference
    """
    if task_id is None:
        task_id = _gen_task_id(content)

    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_OPEN,
        f"task_id:{task_id}",
        f"assigner:{handle}",
        f"to:{to}",
        f"priority:{priority}",
    ]
    if estimate:
        tags.append(f"estimate:{estimate}")
    if topic:
        tags.append(f"topic:{topic}")
    if depends_on:
        for dep in depends_on:
            tags.append(f"depends_on:{dep}")

    obs = _sign_observation(content, tags, rationale=rationale, handle=handle)

    # Write to Oracle via tool_call.
    result = tool_call("oracle_ingest", {"source": "coordination-assign", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"assigned task {task_id} (obs {obs_id})")
    return obs_id, task_id


def claim(task_id: str, rationale: str | None = None) -> str:
    """Claim an open task. Returns obs_id.

    Parameters:
      task_id: the task to claim
      rationale: why you're claiming it (optional)

    Returns:
      obs_id of the claim observation
    """
    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_CLAIMED,
        f"task_id:{task_id}",
        f"claimer:{handle}",
    ]
    content = f"claiming {task_id}"
    obs = _sign_observation(content, tags, rationale=rationale, handle=handle)

    result = tool_call("oracle_ingest", {"source": "coordination-claim", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"claimed task {task_id}")
    return obs_id


def progress(task_id: str, note: str) -> str:
    """Post a progress update. Returns obs_id.

    Parameters:
      task_id: the task being worked on
      note: brief status update

    Returns:
      obs_id of the progress observation
    """
    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_PROGRESS,
        f"task_id:{task_id}",
        f"claimer:{handle}",
    ]
    content = f"progress: {note}"
    obs = _sign_observation(content, tags, handle=handle)

    result = tool_call("oracle_ingest", {"source": "coordination-progress", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"progress update on {task_id}")
    return obs_id


def release(task_id: str, rationale: str | None = None) -> str:
    """Release a claimed task back to open. Returns obs_id.

    Parameters:
      task_id: the task to release
      rationale: why you're releasing it (optional)

    Returns:
      obs_id of the release observation
    """
    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_RELEASED,
        f"task_id:{task_id}",
        f"claimer:{handle}",
    ]
    content = f"releasing {task_id}"
    obs = _sign_observation(content, tags, rationale=rationale, handle=handle)

    result = tool_call("oracle_ingest", {"source": "coordination-release", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"released task {task_id}")
    return obs_id


def complete(
    task_id: str,
    result: str | None = None,
    artifact_cid: str | None = None,
) -> str:
    """Complete a task (terminal state). Returns obs_id.

    Parameters:
      task_id: the task to mark done
      result: optional summary of what was accomplished
      artifact_cid: optional BLAKE3 CID of a blob artifact

    Returns:
      obs_id of the done observation
    """
    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_DONE,
        f"task_id:{task_id}",
        f"claimer:{handle}",
    ]
    if artifact_cid:
        tags.append(f"artifact_cid:{artifact_cid}")

    content = f"done: {task_id}"
    obs = _sign_observation(content, tags, rationale=result, handle=handle)

    result_dict = tool_call("oracle_ingest", {"source": "coordination-complete", "extracted": {"items": [obs]}})
    obs_id = result_dict.get("obs_id", result_dict.get("id", "OBS-unknown"))

    logger.info(f"completed task {task_id}")
    return obs_id


def cancel(task_id: str, rationale: str | None = None) -> str:
    """Cancel a task (assigner-only, terminal state). Returns obs_id.

    Parameters:
      task_id: the task to cancel
      rationale: why it's being cancelled (optional)

    Returns:
      obs_id of the cancel observation

    Raises:
      ValueError if the current handle is not the original assigner
    """
    handle = _get_current_handle()

    # Query for the task's assigner to verify authority.
    history = task_history(task_id)
    if not history:
        raise ValueError(f"task {task_id} not found")

    assigner = None
    for obs in history:
        for tag in obs.get("tags", []):
            if tag.startswith("assigner:"):
                assigner = tag[9:]
                break
        if assigner:
            break

    if assigner and assigner != handle:
        raise ValueError(f"only the assigner ({assigner}) may cancel this task")

    tags = [
        "type:task",
        STATE_CANCELLED,
        f"task_id:{task_id}",
        f"assigner:{handle}",
    ]
    content = f"cancelled: {task_id}"
    obs = _sign_observation(content, tags, rationale=rationale, handle=handle)

    result = tool_call("oracle_ingest", {"source": "coordination-cancel", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"cancelled task {task_id}")
    return obs_id


def block(task_id: str, on: str) -> str:
    """Block a claimed task on a reason or another task_id. Returns obs_id.

    Parameters:
      task_id: the task being blocked
      on: what it's blocked on (free-form reason or another task_id)

    Returns:
      obs_id of the block observation
    """
    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_BLOCKED,
        f"task_id:{task_id}",
        f"claimer:{handle}",
        f"blocked_on:{on}",
    ]
    content = f"blocked: {task_id}"
    obs = _sign_observation(content, tags, handle=handle)

    result = tool_call("oracle_ingest", {"source": "coordination-block", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"blocked task {task_id} on {on}")
    return obs_id


def unblock(task_id: str) -> str:
    """Unblock a blocked task, returning it to claimed state. Returns obs_id.

    Parameters:
      task_id: the task to unblock

    Returns:
      obs_id of the unblock observation
    """
    handle = _get_current_handle()
    tags = [
        "type:task",
        STATE_RESUMED,
        f"task_id:{task_id}",
        f"claimer:{handle}",
    ]
    content = f"unblocked: {task_id}"
    obs = _sign_observation(content, tags, handle=handle)

    result = tool_call("oracle_ingest", {"source": "coordination-unblock", "extracted": {"items": [obs]}})
    obs_id = result.get("obs_id", result.get("id", "OBS-unknown"))

    logger.info(f"unblocked task {task_id}")
    return obs_id


def open_tasks(to: str | None = None) -> list[Task]:
    """Query Oracle for tasks in open state. Returns list of Task objects.

    Parameters:
      to: filter to tasks routed to this handle (optional; default: all open tasks)

    Returns:
      List of Task objects with state == 'open'
    """
    # Query Oracle for all task observations.
    try:
        result = tool_call("oracle_query", {
            "query": "type:task task:open",
            "limit": 1000,
        })
    except Exception as e:
        logger.error(f"error querying open tasks: {e}")
        return []

    # Parse results.
    tasks = []
    seen_task_ids = set()

    for item in result.get("results", []):
        task_id_tag = None
        for tag in item.get("tags", []):
            if tag.startswith("task_id:"):
                task_id_tag = tag[8:]
                break

        if not task_id_tag or task_id_tag in seen_task_ids:
            continue
        seen_task_ids.add(task_id_tag)

        # Extract fields.
        assigner = None
        priority = "p2"
        estimate = None
        for tag in item.get("tags", []):
            if tag.startswith("assigner:"):
                assigner = tag[9:]
            elif tag.startswith("priority:"):
                priority = tag[9:]
            elif tag.startswith("estimate:"):
                try:
                    estimate = int(tag[9:])
                except ValueError:
                    pass

        # Filter by 'to' if specified.
        if to:
            routed = False
            for tag in item.get("tags", []):
                if tag == "to:all" or tag == f"to:{to}":
                    routed = True
                    break
            if not routed:
                continue

        record = _CoordRecord(
            task_id=task_id_tag,
            obs_id=item.get("id", ""),
            content=item.get("content", ""),
            state=STATE_OPEN,
            tags=item.get("tags", []),
            assigner=assigner or "unknown",
            priority=priority,
            estimate=estimate,
            created_at=item.get("created_at", ""),
        )
        tasks.append(record)

    return sorted(tasks, key=lambda t: (t.priority, t.created_at))


def my_tasks(handle: str | None = None) -> list[Task]:
    """Query Oracle for tasks claimed by the current handle. Returns list of Task objects.

    Parameters:
      handle: which handle's tasks to fetch (default: current handle)

    Returns:
      List of Task objects where state in ('claimed', 'blocked', 'resumed')
    """
    if handle is None:
        handle = _get_current_handle()

    try:
        result = tool_call("oracle_query", {
            "query": f"type:task claimer:{handle}",
            "limit": 1000,
        })
    except Exception as e:
        logger.error(f"error querying tasks for {handle}: {e}")
        return []

    tasks = []
    seen_task_ids = set()

    for item in result.get("results", []):
        task_id_tag = None
        state_tag = None
        for tag in item.get("tags", []):
            if tag.startswith("task_id:"):
                task_id_tag = tag[8:]
            elif tag in (STATE_CLAIMED, STATE_BLOCKED, STATE_RESUMED, STATE_PROGRESS):
                state_tag = tag

        if not task_id_tag or task_id_tag in seen_task_ids:
            continue

        # Only include active (non-terminal) states.
        if state_tag not in (STATE_CLAIMED, STATE_BLOCKED, STATE_RESUMED, STATE_PROGRESS):
            continue

        seen_task_ids.add(task_id_tag)

        assigner = None
        for tag in item.get("tags", []):
            if tag.startswith("assigner:"):
                assigner = tag[9:]
                break

        record = _CoordRecord(
            task_id=task_id_tag,
            obs_id=item.get("id", ""),
            content=item.get("content", ""),
            state=state_tag or STATE_CLAIMED,
            tags=item.get("tags", []),
            assigner=assigner or "unknown",
            claimer=handle,
            created_at=item.get("created_at", ""),
        )
        tasks.append(record)

    return tasks


def task_history(task_id: str) -> list[dict[str, Any]]:
    """Query Oracle for all observations related to a task_id. Returns list in creation order.

    Parameters:
      task_id: the task to fetch history for

    Returns:
      List of observation dicts, oldest first
    """
    try:
        result = tool_call("oracle_query", {
            "query": f"task_id:{task_id}",
            "limit": 1000,
        })
    except Exception as e:
        logger.error(f"error querying history for {task_id}: {e}")
        return []

    # Sort by created_at (oldest first).
    observations = result.get("results", [])
    return sorted(observations, key=lambda x: x.get("created_at", ""))


def mesh_status(handle: str | None = None) -> dict[str, int]:
    """Query Oracle for task counts by state. Returns counts dict.

    Parameters:
      handle: filter to a specific handle's tasks (optional)

    Returns:
      Dict with keys: open, claimed, blocked, done, cancelled
    """
    try:
        result = tool_call("oracle_query", {
            "query": "type:task",
            "limit": 10000,
        })
    except Exception as e:
        logger.error(f"error querying mesh status: {e}")
        return {}

    counts = {"open": 0, "claimed": 0, "blocked": 0, "done": 0, "cancelled": 0}

    for item in result.get("results", []):
        if handle:
            claimer = None
            for tag in item.get("tags", []):
                if tag.startswith("claimer:"):
                    claimer = tag[8:]
                    break
            if claimer != handle:
                continue

        for tag in item.get("tags", []):
            if tag == STATE_OPEN:
                counts["open"] += 1
            elif tag == STATE_CLAIMED:
                counts["claimed"] += 1
            elif tag == STATE_BLOCKED:
                counts["blocked"] += 1
            elif tag == STATE_DONE:
                counts["done"] += 1
            elif tag == STATE_CANCELLED:
                counts["cancelled"] += 1

    return counts
