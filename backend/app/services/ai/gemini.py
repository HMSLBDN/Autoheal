"""
AutoHeal DevOps — Google Gemini AI Diagnosis Provider
Integrates Google Gemini API with strict prompt sanitization,
JSON schema validation, and recovery action allowlist enforcement.
"""

import json
import logging
import re
from typing import Any, Dict, Optional
import httpx

from app.config import get_settings
from app.services.ai.base import (
    APPROVED_RECOVERY_ACTIONS,
    AIDiagnosisResult,
    AIProvider,
)
from app.services.ai.heuristic import HeuristicDiagnosisProvider

logger = logging.getLogger(__name__)
settings = get_settings()

PROMPT_INJECTION_PATTERN = re.compile(
    r"(ignore\s+all\s+previous|system\s*:|assistant\s*:|disregard\s+|you\s+are\s+now|override\s+rules)",
    re.IGNORECASE,
)


def sanitize_input(value: Any) -> str:
    """Sanitizes untrusted input from alert labels, metrics, or logs."""
    text = str(value)
    # Strip dangerous prompt injection phrases
    sanitized = PROMPT_INJECTION_PATTERN.sub("[FILTERED]", text)
    # Truncate overly long strings to prevent token exhaustion
    return sanitized[:500]


class GeminiProvider(AIProvider):
    """
    Google Gemini adapter connecting to generativelanguage.googleapis.com.
    Enforces structured JSON response schemas and recovery allowlist validation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL or "gemini-1.5-pro"
        self.timeout = timeout_seconds or settings.AI_TIMEOUT_SECONDS
        self._fallback = HeuristicDiagnosisProvider()

    @property
    def name(self) -> str:
        return f"gemini ({self.model})"

    async def diagnose(self, incident_context: Dict[str, Any]) -> AIDiagnosisResult:
        """
        Executes Gemini diagnosis. If unconfigured or encounters an error,
        transparently falls back to deterministic heuristic diagnosis.
        """
        if not self.api_key:
            logger.info("Gemini API key is not configured; utilizing heuristic diagnosis engine.")
            return await self._fallback.diagnose(incident_context)

        # Sanitize all context inputs before prompt construction
        clean_context = {
            "service_name": sanitize_input(incident_context.get("service_name")),
            "alert_name": sanitize_input(incident_context.get("alert_name")),
            "severity": sanitize_input(incident_context.get("severity")),
            "error_rate": float(incident_context.get("error_rate", 0.0)),
            "latency_ms": int(incident_context.get("latency_ms", 0)),
            "description": sanitize_input(incident_context.get("description", "")),
            "probable_cause": sanitize_input(incident_context.get("probable_cause", "")),
        }

        system_prompt = (
            "You are an expert site reliability engineering (SRE) diagnostic AI for AutoHeal DevOps. "
            "Analyze the following incident telemetry and return a structured JSON assessment. "
            "IMPORTANT: Your recommended_action MUST be exactly one of the following approved allowlist actions: "
            f"{', '.join(sorted(APPROVED_RECOVERY_ACTIONS))}. "
            "Do NOT recommend any shell commands or unapproved actions.\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "summary": "Concise summary",\n'
            '  "probable_root_cause": "Probable root cause",\n'
            '  "severity": "critical"|"high"|"medium"|"low",\n'
            '  "supporting_evidence": ["Evidence point 1", "Evidence point 2"],\n'
            f'  "recommended_action": "one of {list(APPROVED_RECOVERY_ACTIONS)}",\n'
            '  "risk_level": "low"|"medium"|"high",\n'
            '  "confidence_score": 0.85,\n'
            '  "expected_outcome": "Expected outcome post-recovery"\n'
            "}"
        )

        user_prompt = f"Incident Telemetry:\n{json.dumps(clean_context, indent=2)}"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        request_body = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=request_body)

                if res.status_code != 200:
                    logger.warning("Gemini API returned status %s: %s. Using heuristic fallback.", res.status_code, res.text[:200])
                    return await self._fallback.diagnose(incident_context)

                data = res.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed_json = json.loads(raw_text)

                # Validate using Pydantic
                result = AIDiagnosisResult.model_validate(parsed_json)

                # Security check: verify recommended_action is in approved allowlist
                if result.recommended_action not in APPROVED_RECOVERY_ACTIONS:
                    logger.warning(
                        "AI recommended unapproved action '%s'; substituting safe allowlist default.",
                        result.recommended_action,
                    )
                    result.recommended_action = "restart_service"

                return result

        except Exception as e:
            logger.warning("Gemini diagnosis failed with error: %s. Invoking heuristic fallback.", e)
            return await self._fallback.diagnose(incident_context)
