from __future__ import annotations

import json
from typing import Any

from code_review_app.review.models import CheckResult, Finding, Lead, ReviewPipelineResult, Workspace


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
Only report actionable findings with concrete evidence. Do not invent shell commands."""


class AnthropicReviewGateway:
    def __init__(
        self,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 4000,
    ) -> None:
        if client is None:
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key, base_url=base_url)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def review(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_user_prompt(workspace, checks)}],
        )
        payload = json.loads(self._first_text_block(message))
        return ReviewPipelineResult(
            leads=[
                Lead(
                    file_path=str(item["file_path"]),
                    line=int(item["line"]),
                    suspicion=str(item["suspicion"]),
                    related_rule_ids=[str(rule) for rule in item.get("related_rule_ids", [])],
                    suggested_context=str(item["suggested_context"]),
                    status=str(item.get("status", "verified")),
                )
                for item in payload.get("leads", [])
            ],
            findings=[
                Finding(
                    file_path=str(item["file_path"]),
                    line=int(item["line"]),
                    severity=str(item["severity"]),
                    title=str(item["title"]),
                    behavior_at_risk=str(item["behavior_at_risk"]),
                    evidence=str(item["evidence"]),
                    suggested_action=str(item["suggested_action"]),
                    confidence=float(item["confidence"]),
                )
                for item in payload.get("findings", [])
            ],
        )

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
