"""Bridge between EvoScientist intent clarification and LOGOS.

LOGOS does not implement a second conversational UI.  EvoScientist should use
its ``ask_user`` mechanism to clarify the request, then return one strict
``ResearchRequest`` JSON object for LOGOS to parse.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ..schemas import ResearchRequest


@dataclass
class IntentBridgeResult:
    """Parsed result from EvoScientist intent clarification."""

    request: ResearchRequest | None
    raw_response: str
    success: bool
    error: str | None = None


class IntentBridge:
    """Generate prompts and parse EvoScientist's final ResearchRequest JSON."""

    def build_prompt(self, user_input: str) -> str:
        """Build the structured prompt sent to EvoScientist."""
        schema = ResearchRequest.model_json_schema()
        return (
            "You are collecting a LOGOS ResearchRequest.\n\n"
            "Rules:\n"
            "- Use ask_user if required fields are missing or ambiguous.\n"
            "- Do not start paper discovery.\n"
            "- Do not install or invoke skills.\n"
            "- Confirm the clarified request with the user.\n"
            "- After confirmation, return only one JSON object matching the schema.\n\n"
            f"User input:\n{user_input}\n\n"
            "ResearchRequest JSON schema:\n"
            f"{json.dumps(schema, indent=2, ensure_ascii=False)}"
        )

    def parse_response(self, raw_response: str) -> IntentBridgeResult:
        """Parse EvoScientist's final JSON into a ResearchRequest."""
        try:
            payload = self._extract_json_object(raw_response)
            request = ResearchRequest(**payload)
            return IntentBridgeResult(
                request=request,
                raw_response=raw_response,
                success=True,
            )
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            return IntentBridgeResult(
                request=None,
                raw_response=raw_response,
                success=False,
                error=str(exc),
            )

    def _extract_json_object(self, raw_response: str) -> dict[str, Any]:
        stripped = raw_response.strip()
        if stripped.startswith("```"):
            stripped = self._strip_fenced_block(stripped)

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            data = json.loads(stripped[start : end + 1])

        if not isinstance(data, dict):
            raise ValueError("EvoScientist response must be a JSON object")
        return data

    def _strip_fenced_block(self, text: str) -> str:
        lines = text.splitlines()
        if not lines:
            return text
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
