import os
from dotenv import load_dotenv

# Load variables from backend/.env into the environment.
# The .env file is excluded from Git — secrets stay local.
load_dotenv()

APP_NAME: str = os.getenv("APP_NAME", "Coding Task Factory API")
ENV: str = os.getenv("ENV", "development")
DEBUG: bool = ENV == "development"

# Gemini API key — read from .env, never hard-coded here.
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
