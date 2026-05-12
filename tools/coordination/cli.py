"""
cli — Command-line interface for coordination substrate.

Usage:
    python -m pipernet.tools.coordination.cli assign --content "fix the bug" --to shannon --priority p1
    python -m pipernet.tools.coordination.cli claim T-fix-the-bug
    python -m pipernet.tools.coordination.cli progress T-fix-the-bug --note "halfway done"
    python -m pipernet.tools.coordination.cli complete T-fix-the-bug --result "shipped with tests"
    python -m pipernet.tools.coordination.cli list-open
    python -m pipernet.tools.coordination.cli list-mine
"""
import argparse
import json
import sys
from . import (
    assign, claim, progress, release, complete, cancel, block, unblock,
    open_tasks, my_tasks, task_history, mesh_status
)


def cmd_assign(args):
    """Create a new task."""
    obs_id, task_id = assign(
        content=args.content,
        to=args.to,
        priority=args.priority,
        estimate=args.estimate,
        depends_on=args.depends_on.split(",") if args.depends_on else None,
        topic=args.topic,
        rationale=args.rationale,
        task_id=args.task_id,
    )
    print(json.dumps({"obs_id": obs_id, "task_id": task_id}, indent=2))


def cmd_claim(args):
    """Claim a task."""
    obs_id = claim(args.task_id, rationale=args.rationale)
    print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))


def cmd_progress(args):
    """Post a progress update."""
    obs_id = progress(args.task_id, args.note)
    print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))


def cmd_release(args):
    """Release a claimed task."""
    obs_id = release(args.task_id, rationale=args.rationale)
    print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))


def cmd_complete(args):
    """Complete a task."""
    obs_id = complete(args.task_id, result=args.result, artifact_cid=args.artifact_cid)
    print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))


def cmd_cancel(args):
    """Cancel a task (assigner-only)."""
    try:
        obs_id = cancel(args.task_id, rationale=args.rationale)
        print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))
    except ValueError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


def cmd_block(args):
    """Block a task."""
    obs_id = block(args.task_id, args.on)
    print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))


def cmd_unblock(args):
    """Unblock a task."""
    obs_id = unblock(args.task_id)
    print(json.dumps({"obs_id": obs_id, "task_id": args.task_id}, indent=2))


def cmd_list_open(args):
    """List open tasks."""
    tasks = open_tasks(to=args.to)
    for task in tasks:
        print(f"{task.task_id:30} | {task.priority:3} | {task.content[:50]}")


def cmd_list_mine(args):
    """List tasks claimed by current handle."""
    handle = args.handle
    tasks = my_tasks(handle)
    for task in tasks:
        print(f"{task.task_id:30} | {task.state:15} | {task.content[:50]}")


def cmd_history(args):
    """Show full history of a task."""
    obs = task_history(args.task_id)
    print(json.dumps(obs, indent=2))


def cmd_status(args):
    """Show mesh-wide task counts."""
    counts = mesh_status(handle=args.handle)
    print(json.dumps(counts, indent=2))


def main():
    """Main CLI entrypoint."""
    p = argparse.ArgumentParser(
        prog="coordination",
        description="Pipernet coordination substrate v0.1 CLI",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # assign
    p_assign = sub.add_parser("assign", help="Create a new task")
    p_assign.add_argument("--content", required=True, help="Task summary")
    p_assign.add_argument("--to", default="all", help="Target handle or 'all'")
    p_assign.add_argument("--priority", default="p2", help="p0, p1, p2, p3")
    p_assign.add_argument("--estimate", type=int, help="Estimated minutes")
    p_assign.add_argument("--depends-on", help="Comma-separated task IDs")
    p_assign.add_argument("--topic", help="Topic tag")
    p_assign.add_argument("--rationale", help="Why this task matters")
    p_assign.add_argument("--task-id", help="Explicit task ID (auto-generated if not provided)")
    p_assign.set_defaults(func=cmd_assign)

    # claim
    p_claim = sub.add_parser("claim", help="Claim a task")
    p_claim.add_argument("task_id", help="Task ID to claim")
    p_claim.add_argument("--rationale", help="Why you're claiming it")
    p_claim.set_defaults(func=cmd_claim)

    # progress
    p_progress = sub.add_parser("progress", help="Post a progress update")
    p_progress.add_argument("task_id", help="Task ID")
    p_progress.add_argument("--note", required=True, help="Status update")
    p_progress.set_defaults(func=cmd_progress)

    # release
    p_release = sub.add_parser("release", help="Release a claimed task")
    p_release.add_argument("task_id", help="Task ID to release")
    p_release.add_argument("--rationale", help="Why you're releasing it")
    p_release.set_defaults(func=cmd_release)

    # complete
    p_complete = sub.add_parser("complete", help="Mark a task as done")
    p_complete.add_argument("task_id", help="Task ID")
    p_complete.add_argument("--result", help="Summary of what was accomplished")
    p_complete.add_argument("--artifact-cid", help="BLAKE3 CID of result artifact")
    p_complete.set_defaults(func=cmd_complete)

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a task (assigner-only)")
    p_cancel.add_argument("task_id", help="Task ID")
    p_cancel.add_argument("--rationale", help="Why it's being cancelled")
    p_cancel.set_defaults(func=cmd_cancel)

    # block
    p_block = sub.add_parser("block", help="Block a task")
    p_block.add_argument("task_id", help="Task ID")
    p_block.add_argument("--on", required=True, help="What it's blocked on")
    p_block.set_defaults(func=cmd_block)

    # unblock
    p_unblock = sub.add_parser("unblock", help="Unblock a task")
    p_unblock.add_argument("task_id", help="Task ID")
    p_unblock.set_defaults(func=cmd_unblock)

    # list-open
    p_list_open = sub.add_parser("list-open", help="List open tasks")
    p_list_open.add_argument("--to", help="Filter to tasks routed to this handle")
    p_list_open.set_defaults(func=cmd_list_open)

    # list-mine
    p_list_mine = sub.add_parser("list-mine", help="List my claimed tasks")
    p_list_mine.add_argument("--handle", help="Which handle's tasks (default: current)")
    p_list_mine.set_defaults(func=cmd_list_mine)

    # history
    p_history = sub.add_parser("history", help="Show task history")
    p_history.add_argument("task_id", help="Task ID")
    p_history.set_defaults(func=cmd_history)

    # status
    p_status = sub.add_parser("status", help="Show task counts")
    p_status.add_argument("--handle", help="Filter to a specific handle")
    p_status.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
