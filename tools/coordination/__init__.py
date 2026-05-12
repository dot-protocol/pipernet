"""
coordination — Pipernet coordination substrate v0.1 reference implementation.

Public API for task-based work allocation without a central coordinator.
All operations are signed observations stored in Oracle.

Example usage:
    from pipernet.tools.coordination import assign, claim, complete, open_tasks

    obs_id, task_id = assign(
        "build the thing",
        to="shannon",
        priority="p1",
        estimate=120,
        topic="core"
    )
    claim(task_id, rationale="I can do this")
    open_tasks(to="shannon")
    complete(task_id, result="ship + tests passing")
"""

from .tasks import (
    Task,
    assign,
    claim,
    progress,
    release,
    complete,
    cancel,
    block,
    unblock,
    open_tasks,
    my_tasks,
    task_history,
    mesh_status,
)

__all__ = [
    "Task",
    "assign",
    "claim",
    "progress",
    "release",
    "complete",
    "cancel",
    "block",
    "unblock",
    "open_tasks",
    "my_tasks",
    "task_history",
    "mesh_status",
]
