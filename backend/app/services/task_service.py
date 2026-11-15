"""
Task generation service — Day 3 implementation.

Calls the Gemini API to produce realistic software engineering tasks.
The API key is read from config and never logged or returned.
"""
import json
import uuid
from datetime import datetime, timezone

from google import genai
from google.genai import types

from app.core.config import GEMINI_API_KEY
from app.schemas.task import TaskRequest, TaskResponse

# ── Model ──────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-3.8-flash"

# ── Prompt template ────────────────────────────────────────────────
_PROMPT = """\
You are a senior software engineering task designer for a professional coding education platform.

Generate a realistic software engineering task based on the following inputs:
  Topic      : {topic}
  Difficulty : {difficulty}  (easy = ~1-2 hrs | medium = ~half day | hard = full day+)
  Language   : {language}
  Category   : {category}   (backend | frontend | fullstack | devops | data)

Rules:
- Write this like a real Jira or GitHub issue — grounded in a believable product context.
- Do NOT write a textbook algorithm question.
- Requirements must be specific, actionable engineering tasks.
- Acceptance criteria must be concrete and testable (think: "Given X, when Y, then Z").
- Match the difficulty: easy tasks are self-contained; hard tasks involve multiple systems.

Return ONLY valid JSON — no markdown fences, no commentary, no extra keys:
{{
  "title": "<short, specific task title>",
  "description": "<2-3 paragraphs: problem context, why it matters, what success looks like>",
  "requirements": [
    "<specific functional requirement>",
    "<specific functional requirement>",
    "<specific functional requirement>",
    "<specific functional requirement>"
  ],
  "acceptance_criteria": [
    "<testable criterion — use Given/When/Then or plain statement>",
    "<testable criterion>",
    "<testable criterion>"
  ]
}}
"""


def generate_task(request: TaskRequest) -> TaskResponse:
    """
    Call Gemini to generate a structured software engineering task.

    Raises:
        ValueError:   GEMINI_API_KEY is missing.
        RuntimeError: Gemini API call failed or returned unexpected output.
    """
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to backend/.env and restart the server."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = _PROMPT.format(
        topic=request.topic,
        difficulty=request.difficulty,
        language=request.language,
        category=request.category,
    )

    # ── Call Gemini ────────────────────────────────────────────────
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc

    # ── Parse JSON ─────────────────────────────────────────────────
    try:
        raw: dict = json.loads(response.text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"Gemini returned content that is not valid JSON: {exc}"
        ) from exc

    # ── Validate required fields ───────────────────────────────────
    required = {"title", "description", "requirements", "acceptance_criteria"}
    missing = required - raw.keys()
    if missing:
        raise RuntimeError(
            f"Gemini response is missing expected fields: {missing}"
        )

    # ── Build validated response ───────────────────────────────────
    return TaskResponse(
        id=str(uuid.uuid4()),
        topic=request.topic,
        difficulty=request.difficulty,
        language=request.language,
        category=request.category,
        generated_at=datetime.now(timezone.utc).isoformat(),
        title=raw["title"],
        description=raw["description"],
        requirements=raw["requirements"],
        acceptance_criteria=raw["acceptance_criteria"],
    )
