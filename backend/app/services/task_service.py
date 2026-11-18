"""
Task generation service — Day 3 & Day 5 implementation.

Calls the Gemini API to produce:
1. Topic-based software engineering tasks (generate_task).
2. Repository-grounded contextual tasks (generate_task_from_repo).

The API key is read from config and never logged or returned.
"""
import json
import uuid
from datetime import datetime, timezone

from google import genai
from google.genai import types

from app.core.config import GEMINI_API_KEY
from app.schemas.repo import RepoAnalysisResponse
from app.schemas.task import RepoTaskRequest, TaskRequest, TaskResponse

# ── Model ──────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-3.8-flash"

# ── In-Memory Task Registry ─────────────────────────────────────────

_TASK_REGISTRY: dict[str, TaskResponse] = {}


def save_task(task: TaskResponse) -> TaskResponse:
    """Stores a generated task in the in-memory registry."""
    _TASK_REGISTRY[task.id] = task
    return task


def get_task(task_id: str) -> TaskResponse | None:
    """Retrieves a task by UUID from the in-memory registry."""
    return _TASK_REGISTRY.get(task_id)


def list_tasks() -> list[TaskResponse]:
    """Lists all stored tasks."""
    return list(_TASK_REGISTRY.values())


def clear_tasks() -> None:
    """Clears the in-memory task registry (for test isolation)."""
    _TASK_REGISTRY.clear()


# ── Prompt templates ───────────────────────────────────────────────
_TOPIC_PROMPT = """\
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

_REPO_PROMPT = """\
You are a Principal Software Architect assigning a real-world engineering task for an existing codebase.

Codebase Summary:
  Project Name        : {project_name}
  Detected Languages  : {detected_languages}
  Detected Frameworks : {detected_frameworks}
  Folder Hierarchy    :
{folder_structure}
  README Overview     :
{readme_summary}

Task Parameters:
  Target Difficulty   : {difficulty}  (easy = self-contained bug fix/minor feature | medium = component enhancement | hard = architectural feature)
  Focus Area          : {focus_area}
  Target Category     : {category}

Rules:
1. The task MUST be directly grounded in the specific codebase described above.
2. Respect existing architecture, conventions, and frameworks.
3. Suggest a realistic feature, improvement, integration, or refactoring that naturally fits this repository.
4. Do NOT propose generic LeetCode/algorithm puzzles.
5. In "relevant_files", provide 2 to 5 plausible file paths grounded in the supplied folder hierarchy.
   - For existing files to modify, use the directory conventions shown above.
   - For proposed new files, clearly indicate with (new), e.g. "app/services/cache.py (new)".

Return ONLY valid JSON — no markdown fences, no commentary, no extra keys:
{{
  "title": "<concise, professional Jira/GitHub task title>",
  "description": "<2-3 paragraphs explaining the context in this codebase, business motivation, and architecture approach>",
  "requirements": [
    "<actionable requirement 1>",
    "<actionable requirement 2>",
    "<actionable requirement 3>",
    "<actionable requirement 4>"
  ],
  "acceptance_criteria": [
    "<testable criterion 1>",
    "<testable criterion 2>",
    "<testable criterion 3>"
  ],
  "relevant_files": [
    "<file_path_1>",
    "<file_path_2>"
  ]
}}
"""


def _get_gemini_client() -> genai.Client:
    """Initialize and return Gemini client, checking for API key."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to backend/.env and restart the server."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def generate_task(request: TaskRequest) -> TaskResponse:
    """
    Call Gemini to generate a structured software engineering task based on a topic.

    Raises:
        ValueError:   GEMINI_API_KEY is missing.
        RuntimeError: Gemini API call failed or returned unexpected output.
    """
    client = _get_gemini_client()

    prompt = _TOPIC_PROMPT.format(
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
    return save_task(
        TaskResponse(
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
    )


def generate_task_from_repo(
    repo_analysis: RepoAnalysisResponse,
    options: RepoTaskRequest | None = None,
) -> TaskResponse:
    """
    Call Gemini to generate a contextual task grounded in actual repository analysis.

    Raises:
        ValueError:   GEMINI_API_KEY is missing.
        RuntimeError: Gemini API call failed or returned unexpected output.
    """
    client = _get_gemini_client()
    opts = options or RepoTaskRequest()

    # Determine primary language & category fallback from repo analysis
    primary_lang = (
        repo_analysis.detected_languages[0]
        if repo_analysis.detected_languages
        else "Unknown"
    )
    category = opts.category or (
        "frontend" if "React" in repo_analysis.detected_frameworks or "Next.js" in repo_analysis.detected_frameworks
        else "backend"
    )
    focus_area = opts.focus_area or "General enhancement or feature addition"

    # Truncate folder structure (max 25 entries)
    top_folders = repo_analysis.folder_structure[:25]
    folder_str = "\n".join(f"    - {f}" for f in top_folders) if top_folders else "    - (flat directory structure)"

    # Truncate README summary (max 2000 chars)
    readme_text = (repo_analysis.readme_summary or "No README provided.")[:2000]

    prompt = _REPO_PROMPT.format(
        project_name=repo_analysis.project_name,
        detected_languages=", ".join(repo_analysis.detected_languages) or "None detected",
        detected_frameworks=", ".join(repo_analysis.detected_frameworks) or "None detected",
        folder_structure=folder_str,
        readme_summary=readme_text,
        difficulty=opts.difficulty,
        focus_area=focus_area,
        category=category,
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

    relevant_files = raw.get("relevant_files", [])
    if not isinstance(relevant_files, list):
        relevant_files = []

    # ── Build validated response ───────────────────────────────────
    topic_summary = f"Codebase: {repo_analysis.project_name}"
    if opts.focus_area:
        topic_summary += f" ({opts.focus_area})"

    return save_task(
        TaskResponse(
            id=str(uuid.uuid4()),
            topic=topic_summary,
            difficulty=opts.difficulty,
            language=primary_lang,
            category=category,
            generated_at=datetime.now(timezone.utc).isoformat(),
            title=raw["title"],
            description=raw["description"],
            requirements=raw["requirements"],
            acceptance_criteria=raw["acceptance_criteria"],
            project_name=repo_analysis.project_name,
            relevant_files=relevant_files,
            starting_commit_sha=repo_analysis.commit_sha,
        )
    )
