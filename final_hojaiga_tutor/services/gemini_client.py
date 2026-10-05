from google import genai

from config.settings import GEMINI_API_KEY, MODEL


def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)
