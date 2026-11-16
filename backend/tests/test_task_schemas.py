"""
Unit tests for Task and RepoTask Pydantic schemas.

Validates:
- RepoTaskRequest defaults and allowed Literal values for difficulty
- Rejection of invalid difficulty values in RepoTaskRequest
- Backward compatibility of TaskResponse (defaults for project_name and relevant_files)
- Preservation of original TaskRequest
"""

import unittest
from pydantic import ValidationError

from app.schemas.task import RepoTaskRequest, TaskRequest, TaskResponse


class TestTaskSchemas(unittest.TestCase):
    def test_repo_task_request_defaults(self):
        """Default values for RepoTaskRequest must be medium, None, None."""
        req = RepoTaskRequest()
        self.assertEqual(req.difficulty, "medium")
        self.assertIsNone(req.focus_area)
        self.assertIsNone(req.category)

    def test_repo_task_request_valid_difficulties(self):
        """easy, medium, and hard are accepted."""
        for diff in ["easy", "medium", "hard"]:
            req = RepoTaskRequest(difficulty=diff, focus_area="caching", category="backend")
            self.assertEqual(req.difficulty, diff)
            self.assertEqual(req.focus_area, "caching")
            self.assertEqual(req.category, "backend")

    def test_repo_task_request_invalid_difficulty(self):
        """Values other than easy, medium, hard raise ValidationError."""
        for bad_diff in ["expert", "extreme", "simple", ""]:
            with self.assertRaises(ValidationError):
                RepoTaskRequest(difficulty=bad_diff)

    def test_task_response_backward_compatibility(self):
        """TaskResponse instantiated without project_name or relevant_files succeeds."""
        resp = TaskResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            topic="algorithms",
            difficulty="medium",
            language="python",
            category="backend",
            title="Sample Task",
            description="Sample Description",
            requirements=["Req 1"],
            acceptance_criteria=["Crit 1"],
            generated_at="2026-11-15T12:00:00+00:00",
        )
        self.assertIsNone(resp.project_name)
        self.assertEqual(resp.relevant_files, [])

    def test_task_response_with_repo_fields(self):
        """TaskResponse with project_name and relevant_files populated correctly."""
        resp = TaskResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            topic="Repository Context",
            difficulty="hard",
            language="python",
            category="backend",
            title="Add Caching",
            description="Implement Redis caching",
            requirements=["Req 1"],
            acceptance_criteria=["Crit 1"],
            generated_at="2026-11-15T12:00:00+00:00",
            project_name="my_repo",
            relevant_files=["app/cache.py", "app/main.py"],
        )
        self.assertEqual(resp.project_name, "my_repo")
        self.assertEqual(resp.relevant_files, ["app/cache.py", "app/main.py"])

    def test_task_request_preserves_existing_behavior(self):
        """TaskRequest requires topic and assigns default difficulty, language, and category."""
        req = TaskRequest(topic="REST APIs")
        self.assertEqual(req.topic, "REST APIs")
        self.assertEqual(req.difficulty, "medium")
        self.assertEqual(req.language, "python")
        self.assertEqual(req.category, "backend")


if __name__ == "__main__":
    unittest.main(verbosity=2)
