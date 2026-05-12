"""
test_tasks — Tests for coordination substrate v0.1.

Tests are mocked against Oracle calls (no live Oracle dependency).
Focus areas:
  - State machine transitions (assign → claim → complete)
  - First-valid-write conflict resolution (two claims)
  - Assigner-only operations (cancel)
  - Release-then-reclaim flow
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Make sure coordination module can be imported.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from coordination import (
    assign, claim, release, complete, cancel, block, unblock,
    open_tasks, my_tasks, task_history, mesh_status
)


class MockOracleResponse:
    """Mock Oracle response object."""
    def __init__(self, obs_id="OBS-test-001", observations=None):
        self.obs_id = obs_id
        self.observations = observations or []

    def get(self, key, default=None):
        if key == "obs_id":
            return self.obs_id
        if key == "results":
            return self.observations
        return default


class TestStateTransitions(unittest.TestCase):
    """Test basic state machine transitions."""

    @patch("coordination.tasks.tool_call")
    @patch("coordination.tasks._get_current_handle", return_value="shannon")
    def test_assign_claim_complete(self, mock_handle, mock_tool_call):
        """Test the happy-path: assign → claim → complete."""
        # Setup mock responses.
        def tool_call_side_effect(method, params):
            if method == "oracle_ingest":
                return {"obs_id": "OBS-assign-001", "id": "OBS-assign-001"}
            return {}

        mock_tool_call.side_effect = tool_call_side_effect

        # Assign a task.
        obs_id_assign, task_id = assign(
            "fix the bug",
            to="shannon",
            priority="p1",
            estimate=60,
        )
        self.assertEqual(task_id[:2], "T-")
        self.assertIsNotNone(obs_id_assign)

        # Mock the claim response.
        mock_tool_call.side_effect = lambda method, params: (
            {"obs_id": "OBS-claim-001"} if method == "oracle_ingest" else {}
        )

        # Claim the task.
        obs_id_claim = claim(task_id, rationale="I can do this")
        self.assertIsNotNone(obs_id_claim)

        # Mock the complete response.
        mock_tool_call.side_effect = lambda method, params: (
            {"obs_id": "OBS-complete-001"} if method == "oracle_ingest" else {}
        )

        # Complete the task.
        obs_id_complete = complete(task_id, result="shipped + tests passing")
        self.assertIsNotNone(obs_id_complete)

    @patch("coordination.tasks.tool_call")
    @patch("coordination.tasks._get_current_handle")
    def test_first_valid_write_conflict(self, mock_handle, mock_tool_call):
        """Test that first claim wins (first-valid-write semantics)."""
        mock_handle.return_value = "shannon"

        # Assign a task.
        mock_tool_call.return_value = {"obs_id": "OBS-assign-001"}
        obs_id_assign, task_id = assign("test task", to="all")

        # Simulate two concurrent claims: shannon and erlich, with shannon's arriving first.
        # In real Oracle, this would be detected at read time (created_at + id comparison).
        # For this test, we just verify the claim operations succeed.

        mock_handle.return_value = "shannon"
        mock_tool_call.return_value = {"obs_id": "OBS-claim-shannon-001"}
        obs_shannon = claim(task_id, rationale="first claim")
        self.assertIsNotNone(obs_shannon)

        # Erlich's claim would also succeed at write time (no server-side exclusion).
        # The conflict is resolved at read time by comparing created_at / id.
        mock_handle.return_value = "erlich"
        mock_tool_call.return_value = {"obs_id": "OBS-claim-erlich-001"}
        obs_erlich = claim(task_id, rationale="second claim")
        self.assertIsNotNone(obs_erlich)

        # In a real system, task_history would show both claims, but readers would
        # pick shannon's based on earlier created_at.


class TestReleaseReclaim(unittest.TestCase):
    """Test release and reclaim flow."""

    @patch("coordination.tasks.tool_call")
    @patch("coordination.tasks._get_current_handle", return_value="shannon")
    def test_release_then_reclaim(self, mock_handle, mock_tool_call):
        """Test: claim → release → claim (by different agent)."""
        mock_tool_call.return_value = {"obs_id": "OBS-test-001"}

        # Assign and claim.
        obs_assign, task_id = assign("task", to="all")
        obs_claim1 = claim(task_id)
        self.assertIsNotNone(obs_claim1)

        # Release.
        obs_release = release(task_id, rationale="can't do it right now")
        self.assertIsNotNone(obs_release)

        # Erlich claims it.
        mock_handle.return_value = "erlich"
        obs_claim2 = claim(task_id, rationale="I'll take it")
        self.assertIsNotNone(obs_claim2)


class TestAssignerOnlyCancel(unittest.TestCase):
    """Test assigner-only cancel operation."""

    @patch("coordination.tasks.tool_call")
    @patch("coordination.tasks._get_current_handle")
    def test_cancel_assigner_authorized(self, mock_handle, mock_tool_call):
        """Test: assigner can cancel."""
        mock_handle.return_value = "shannon"

        # Setup: assign creates an observation with assigner:shannon.
        mock_tool_call.return_value = {"obs_id": "OBS-assign-001"}
        obs_assign, task_id = assign("task", to="all")

        # Simulate task_history response.
        def tool_call_side_effect(method, params):
            if method == "oracle_ingest":
                return {"obs_id": "OBS-test-001"}
            elif method == "oracle_query":
                # Return mock history with shannon as assigner.
                return {
                    "results": [
                        {
                            "id": "OBS-assign-001",
                            "tags": ["type:task", "task:open", "assigner:shannon"],
                            "content": "task"
                        }
                    ]
                }
            return {}

        mock_tool_call.side_effect = tool_call_side_effect

        # Shannon cancels (authorized).
        mock_handle.return_value = "shannon"
        obs_cancel = cancel(task_id, rationale="scope change")
        self.assertIsNotNone(obs_cancel)

    @patch("coordination.tasks.tool_call")
    @patch("coordination.tasks._get_current_handle")
    def test_cancel_non_assigner_denied(self, mock_handle, mock_tool_call):
        """Test: non-assigner cannot cancel."""
        mock_handle.return_value = "shannon"

        # Assign (shannon).
        mock_tool_call.return_value = {"obs_id": "OBS-assign-001"}
        obs_assign, task_id = assign("task", to="all")

        # Simulate task_history showing shannon as assigner.
        def tool_call_side_effect(method, params):
            if method == "oracle_query":
                return {
                    "results": [
                        {
                            "id": "OBS-assign-001",
                            "tags": ["type:task", "task:open", "assigner:shannon"],
                            "content": "task"
                        }
                    ]
                }
            return {"obs_id": "OBS-test-001"}

        mock_tool_call.side_effect = tool_call_side_effect

        # Erlich tries to cancel (not authorized).
        mock_handle.return_value = "erlich"
        with self.assertRaises(ValueError) as ctx:
            cancel(task_id, rationale="I think so")
        self.assertIn("only the assigner", str(ctx.exception))


class TestBlockUnblock(unittest.TestCase):
    """Test block/unblock operations."""

    @patch("coordination.tasks.tool_call")
    @patch("coordination.tasks._get_current_handle", return_value="shannon")
    def test_block_then_unblock(self, mock_handle, mock_tool_call):
        """Test: claim → block → unblock."""
        mock_tool_call.return_value = {"obs_id": "OBS-test-001"}

        obs_assign, task_id = assign("task")
        obs_claim = claim(task_id)

        obs_block = block(task_id, on="waiting for API key")
        self.assertIsNotNone(obs_block)

        obs_unblock = unblock(task_id)
        self.assertIsNotNone(obs_unblock)


class TestQueries(unittest.TestCase):
    """Test query operations (open_tasks, my_tasks, task_history, mesh_status)."""

    @patch("coordination.tasks.tool_call")
    def test_open_tasks_empty(self, mock_tool_call):
        """Test open_tasks when no tasks exist."""
        mock_tool_call.return_value = {"results": []}
        tasks = open_tasks()
        self.assertEqual(len(tasks), 0)

    @patch("coordination.tasks.tool_call")
    def test_open_tasks_multiple(self, mock_tool_call):
        """Test open_tasks returns filtered and sorted results."""
        mock_tool_call.return_value = {
            "results": [
                {
                    "id": "OBS-001",
                    "content": "high priority task",
                    "tags": ["type:task", "task:open", "task_id:T-high-task", "assigner:shannon", "priority:p1", "to:all"],
                    "created_at": "2026-05-12T10:00:00Z",
                },
                {
                    "id": "OBS-002",
                    "content": "low priority task",
                    "tags": ["type:task", "task:open", "task_id:T-low-task", "assigner:shannon", "priority:p3", "to:all"],
                    "created_at": "2026-05-12T11:00:00Z",
                },
            ]
        }
        tasks = open_tasks()
        self.assertEqual(len(tasks), 2)
        # Should be sorted by priority (p1 before p3).
        self.assertEqual(tasks[0].priority, "p1")
        self.assertEqual(tasks[1].priority, "p3")

    @patch("coordination.tasks.tool_call")
    def test_my_tasks(self, mock_tool_call):
        """Test my_tasks returns only active claims."""
        mock_tool_call.return_value = {
            "results": [
                {
                    "id": "OBS-001",
                    "content": "claimed task",
                    "tags": ["type:task", "task:claimed", "task_id:T-task1", "assigner:shannon", "claimer:shannon"],
                    "created_at": "2026-05-12T10:00:00Z",
                },
                {
                    "id": "OBS-002",
                    "content": "done task",
                    "tags": ["type:task", "task:done", "task_id:T-task2", "assigner:shannon", "claimer:shannon"],
                    "created_at": "2026-05-12T11:00:00Z",
                },
            ]
        }
        tasks = my_tasks("shannon")
        # Should return only the claimed task, not the done one.
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].state, "task:claimed")

    @patch("coordination.tasks.tool_call")
    def test_task_history(self, mock_tool_call):
        """Test task_history returns observations in order."""
        mock_tool_call.return_value = {
            "results": [
                {
                    "id": "OBS-003",
                    "content": "complete",
                    "tags": ["type:task", "task:done"],
                    "created_at": "2026-05-12T12:00:00Z",
                },
                {
                    "id": "OBS-001",
                    "content": "assign",
                    "tags": ["type:task", "task:open"],
                    "created_at": "2026-05-12T10:00:00Z",
                },
                {
                    "id": "OBS-002",
                    "content": "claim",
                    "tags": ["type:task", "task:claimed"],
                    "created_at": "2026-05-12T11:00:00Z",
                },
            ]
        }
        obs = task_history("T-task")
        # Should be sorted by created_at (oldest first).
        self.assertEqual(len(obs), 3)
        self.assertEqual(obs[0]["id"], "OBS-001")
        self.assertEqual(obs[1]["id"], "OBS-002")
        self.assertEqual(obs[2]["id"], "OBS-003")

    @patch("coordination.tasks.tool_call")
    def test_mesh_status(self, mock_tool_call):
        """Test mesh_status counts by state."""
        mock_tool_call.return_value = {
            "results": [
                {"id": "OBS-001", "tags": ["type:task", "task:open"]},
                {"id": "OBS-002", "tags": ["type:task", "task:open"]},
                {"id": "OBS-003", "tags": ["type:task", "task:claimed"]},
                {"id": "OBS-004", "tags": ["type:task", "task:done"]},
            ]
        }
        counts = mesh_status()
        self.assertEqual(counts["open"], 2)
        self.assertEqual(counts["claimed"], 1)
        self.assertEqual(counts["done"], 1)


if __name__ == "__main__":
    unittest.main()
