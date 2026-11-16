"""
Unit tests for Day 6 Solution Pydantic schemas:
- SolutionFile
- SolutionResponse
- SolutionRequest
"""

import unittest
from pydantic import ValidationError

from app.schemas.solution import SolutionFile, SolutionRequest, SolutionResponse
from app.schemas.task import TaskResponse


def _make_sample_task() -> TaskResponse:
    return TaskResponse(
        id="123e4567-e89b-12d3-a456-426614174000",
        topic="Redis Caching",
        difficulty="medium",
        language="python",
        category="backend",
        title="Add Redis Cache Middleware",
        description="Implement caching for task API endpoints.",
        requirements=["Add redis to requirements", "Create cache utility"],
        acceptance_criteria=["Given cache miss, queries DB and stores key"],
        generated_at="2026-11-16T12:00:00+00:00",
        project_name="task-factory",
        relevant_files=["app/cache.py (new)"],
    )


class TestSolutionSchemas(unittest.TestCase):
    def test_solution_file_valid_defaults(self):
        """SolutionFile assigns default status='create' and language='python'."""
        f = SolutionFile(
            path="app/core/cache.py",
            code="import redis\ndef get_redis(): pass",
            explanation="Creates Redis connection utility.",
        )
        self.assertEqual(f.path, "app/core/cache.py")
        self.assertEqual(f.status, "create")
        self.assertEqual(f.language, "python")
        self.assertEqual(f.explanation, "Creates Redis connection utility.")

    def test_solution_file_status_literal(self):
        """status accepts 'create' and 'modify', rejects other values."""
        f_mod = SolutionFile(
            path="app/main.py",
            status="modify",
            language="python",
            code="# modified main.py",
            explanation="Mount cache middleware.",
        )
        self.assertEqual(f_mod.status, "modify")

        with self.assertRaises(ValidationError):
            SolutionFile(
                path="app/main.py",
                status="delete",  # Invalid
                code="# code",
                explanation="# exp",
            )

    def test_solution_response_creation(self):
        """SolutionResponse correctly validates all fields."""
        f1 = SolutionFile(
            path="app/cache.py",
            status="create",
            language="python",
            code="redis_client = None",
            explanation="Initial client stub.",
        )
        resp = SolutionResponse(
            id="a0000000-0000-0000-0000-000000000001",
            task_id="123e4567-e89b-12d3-a456-426614174000",
            task_title="Add Redis Cache Middleware",
            architecture_notes="High-level notes explaining Redis layer.",
            files=[f1],
            testing_guide="Run pytest tests/test_cache.py",
            verification_steps=["Start Redis", "Send GET request twice"],
            generated_at="2026-11-16T12:05:00+00:00",
        )
        self.assertEqual(resp.task_id, "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(len(resp.files), 1)
        self.assertEqual(len(resp.verification_steps), 2)

    def test_solution_response_defaults(self):
        """files and verification_steps default to empty lists."""
        resp = SolutionResponse(
            id="a0000000-0000-0000-0000-000000000001",
            task_id="123e4567-e89b-12d3-a456-426614174000",
            task_title="Add Redis Cache Middleware",
            architecture_notes="High-level notes",
            testing_guide="Testing instructions",
            generated_at="2026-11-16T12:05:00+00:00",
        )
        self.assertEqual(resp.files, [])
        self.assertEqual(resp.verification_steps, [])

    def test_solution_request_valid(self):
        """SolutionRequest wraps a valid TaskResponse."""
        task = _make_sample_task()
        req = SolutionRequest(task=task)
        self.assertEqual(req.task.id, task.id)
        self.assertEqual(req.task.title, task.title)

    def test_solution_request_missing_task(self):
        """SolutionRequest requires task to be provided."""
        with self.assertRaises(ValidationError):
            SolutionRequest()


if __name__ == "__main__":
    unittest.main(verbosity=2)
