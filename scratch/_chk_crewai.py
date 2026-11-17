import importlib
try:
    import crewai
    print("crewai", getattr(crewai, "__version__", "?"))
except Exception as e:
    print("crewai import FAILED:", type(e).__name__, str(e)[:200])
try:
    import pydantic
    print("pydantic", pydantic.VERSION)
except Exception as e:
    print("pydantic FAILED:", e)
