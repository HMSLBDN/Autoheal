"""
AutoHeal DevOps — AI Provider Factory
"""

from functools import lru_cache
from app.config import get_settings
from app.services.ai.base import AIProvider
from app.services.ai.gemini import GeminiProvider
from app.services.ai.heuristic import HeuristicDiagnosisProvider

settings = get_settings()


@lru_cache()
def get_ai_provider() -> AIProvider:
    """
    Returns configured AI provider instance.
    Defaults to Gemini if configured with an API key, otherwise Heuristic engine.
    """
    if settings.AI_PROVIDER == "gemini" and settings.AI_API_KEY:
        return GeminiProvider(
            api_key=settings.AI_API_KEY,
            model=settings.AI_MODEL,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        )
    return HeuristicDiagnosisProvider()
