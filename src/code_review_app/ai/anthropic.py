from __future__ import annotations

import json
import logging
from typing import Any

from code_review_app.review.models import (
    CheckResult,
    Finding,
    Lead,
    ModelUsage,
    ReviewPipelineResult,
    Workspace,
)


logger = logging.getLogger(__name__)
MAX_MODEL_FINDINGS = 5
MIN_MODEL_CONFIDENCE = 0.8
DEFAULT_SUGGESTED_CONTEXT = "No suggested context provided by model."
DEFAULT_BEHAVIOR_AT_RISK = "The model did not provide behavior-at-risk details."
DEFAULT_SUGGESTED_ACTION = "Inspect the cited code and update if needed."

SYSTEM_PROMPT = """You are an AI code reviewer.
Return only JSON with this exact shape:
{
  "leads": [
    {
      "file_path": "path",
      "line": 1,
      "suspicion": "short suspicion",
      "related_rule_ids": ["rule"],
      "suggested_context": "evidence to inspect",
      "status": "verified"
    }
  ],
  "findings": [
    {
      "file_path": "path",
      "line": 1,
      "severity": "low|medium|high",
      "title": "concise issue title",
      "behavior_at_risk": "user-visible risk",
      "evidence": "specific evidence from diff or checks",
      "suggested_action": "specific fix",
      "confidence": 0.0
    }
  ]
}
Only report actionable findings with concrete evidence.
At most 5 findings.
Only include findings with confidence >= 0.80.
Prioritize correctness, security, data loss, privacy, API contract, and test regressions.
Do not restate raw check failures unless you can tie the failure to a specific changed line or behavior.
Do not invent shell commands."""


class AnthropicReviewGateway:
    def __init__(
        self,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "MiniMax-M2.7",
        max_tokens: int = 4000,
        input_price_per_million_tokens: float = 0.0,
        output_price_per_million_tokens: float = 0.0,
        provider: str = "anthropic-compatible",
    ) -> None:
        if client is None:
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key, base_url=base_url)
        self.client = client
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.input_price_per_million_tokens = input_price_per_million_tokens
        self.output_price_per_million_tokens = output_price_per_million_tokens
        self.provider = provider

    def review(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        user_prompt = self._build_user_prompt(workspace, checks)
        logger.info(
            "starting model review model=%s base_url=%s checks=%s prompt_chars=%s max_tokens=%s",
            self.model,
            self.base_url or "default",
            len(checks),
            len(user_prompt),
            self.max_tokens,
        )
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        logger.info("parsing model review response model=%s", self.model)
        payload = self._parse_json_payload(self._first_text_block(message))
        input_tokens, output_tokens = self._usage_tokens(message)
        estimated_cost_usd = self._estimated_cost_usd(input_tokens, output_tokens)
        result = ReviewPipelineResult(
            leads=self._parse_leads(payload),
            findings=self._parse_findings(payload),
            model_usage=ModelUsage(
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost_usd,
            ),
        )
        logger.info(
            "model review completed model=%s input_tokens=%s output_tokens=%s "
            "estimated_cost_usd=%.6f leads=%s findings=%s",
            self.model,
            input_tokens,
            output_tokens,
            estimated_cost_usd,
            len(result.leads),
            len(result.findings),
        )
        return result

    @classmethod
    def _parse_leads(cls, payload: dict[str, Any]) -> list[Lead]:
        leads: list[Lead] = []
        for item in cls._payload_items(payload, "leads"):
            leads.append(
                Lead(
                    file_path=cls._string_field(item, "file_path", "."),
                    line=cls._int_field(item, "line", 1),
                    suspicion=cls._string_field(item, "suspicion", "Potential issue"),
                    related_rule_ids=cls._string_list_field(item, "related_rule_ids"),
                    suggested_context=cls._string_field(
                        item, "suggested_context", DEFAULT_SUGGESTED_CONTEXT
                    ),
                    status=cls._string_field(item, "status", "verified"),
                )
            )
        return leads

    @classmethod
    def _parse_findings(cls, payload: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []
        for item in cls._payload_items(payload, "findings"):
            confidence = cls._confidence_field(item)
            if confidence < MIN_MODEL_CONFIDENCE:
                continue
            findings.append(
                Finding(
                    file_path=cls._string_field(item, "file_path", "."),
                    line=cls._int_field(item, "line", 1),
                    severity=cls._severity_field(item),
                    title=cls._string_field(item, "title", "Model review finding"),
                    behavior_at_risk=cls._string_field(
                        item, "behavior_at_risk", DEFAULT_BEHAVIOR_AT_RISK
                    ),
                    evidence=cls._string_field(item, "evidence", "No evidence provided by model."),
                    suggested_action=cls._string_field(
                        item, "suggested_action", DEFAULT_SUGGESTED_ACTION
                    ),
                    confidence=confidence,
                )
            )
        return findings[:MAX_MODEL_FINDINGS]

    def _build_user_prompt(self, workspace: Workspace, checks: list[CheckResult]) -> str:
        check_payload = [
            {
                "name": check.name,
                "kind": check.kind,
                "command": check.command,
                "exit_code": check.exit_code,
                "timed_out": check.timed_out,
                "output_excerpt": check.output_excerpt,
            }
            for check in checks
        ]
        return json.dumps(
            {
                "base_sha": workspace.base_sha,
                "head_sha": workspace.head_sha,
                "diff": workspace.diff,
                "checks": check_payload,
            }
        )

    @staticmethod
    def _first_text_block(message: Any) -> str:
        for block in message.content:
            if getattr(block, "type", None) == "text":
                return str(block.text)
        raise ValueError("Anthropic response did not contain a text block")

    @staticmethod
    def _parse_json_payload(text: str) -> dict[str, Any]:
        normalized = AnthropicReviewGateway._strip_markdown_fence(text)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            payload = AnthropicReviewGateway._parse_first_json_object(normalized)
        if not isinstance(payload, dict):
            raise ValueError("Anthropic response JSON payload must be an object")
        return payload

    @staticmethod
    def _payload_items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        raw_items = payload.get(key, [])
        if not isinstance(raw_items, list):
            logger.warning("model review response field was not a list field=%s", key)
            return []
        items: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if isinstance(item, dict):
                items.append(item)
            else:
                logger.warning(
                    "skipping non-object model review item field=%s index=%s", key, index
                )
        return items

    @staticmethod
    def _string_field(item: dict[str, Any], key: str, default: str) -> str:
        value = item.get(key)
        if value is None:
            return default
        text = str(value).strip()
        return text or default

    @staticmethod
    def _string_list_field(item: dict[str, Any], key: str) -> list[str]:
        value = item.get(key, [])
        if not isinstance(value, list):
            return []
        return [str(entry) for entry in value]

    @staticmethod
    def _int_field(item: dict[str, Any], key: str, default: int) -> int:
        value = item.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _severity_field(cls, item: dict[str, Any]) -> str:
        severity = cls._string_field(item, "severity", "medium").lower()
        if severity not in {"low", "medium", "high"}:
            return "medium"
        return severity

    @staticmethod
    def _confidence_field(item: dict[str, Any]) -> float:
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
        return min(max(confidence, 0.0), 1.0)

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped

        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return stripped

    @staticmethod
    def _parse_first_json_object(text: str) -> Any:
        start = text.find("{")
        if start == -1:
            logger.warning(
                "model review response did not contain a JSON object response_chars=%s",
                len(text),
            )
            raise ValueError("Anthropic response did not contain a JSON object")

        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            logger.warning(
                "model review response was not valid JSON response_chars=%s",
                len(text),
            )
            raise
        return payload

    @staticmethod
    def _usage_tokens(message: Any) -> tuple[int, int]:
        usage = getattr(message, "usage", None)
        if usage is None:
            return 0, 0
        input_tokens = getattr(usage, "input_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "prompt_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "completion_tokens", 0)
        return int(input_tokens or 0), int(output_tokens or 0)

    def _estimated_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1_000_000) * self.input_price_per_million_tokens
            + (output_tokens / 1_000_000) * self.output_price_per_million_tokens
        )
