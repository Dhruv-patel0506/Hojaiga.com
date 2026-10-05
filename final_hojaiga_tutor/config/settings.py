import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("TUTOR_MODEL", "gemini-2.5-flash")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
