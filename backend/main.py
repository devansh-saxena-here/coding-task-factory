# Entry point — imports the app object from the app package.
# Run with: uvicorn main:app --reload  (from the backend/ directory)
from app.main import app  # noqa: F401
