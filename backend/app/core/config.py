import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME: str = os.getenv("APP_NAME", "Coding Task Factory API")
ENV: str = os.getenv("ENV", "development")
DEBUG: bool = ENV == "development"
