from __future__ import annotations

import json
import logging
from pathlib import Path

from code_review_app.ai.anthropic import AnthropicReviewGateway
from code_review_app.review.models import CheckResult, Workspace
from code_review_app.review.pipeline import AnthropicReviewPipeline


class FakeMessages:
    def __init__(self, text: str, usage=None) -> None:
        self.text = text
        self.usage = usage
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = [type("TextBlock", (), {"type": "text", "text": self.text})()]
        return type("Message", (), {"content": content, "usage": self.usage})()


class FakeAnthropicClient:
    def __init__(self, text: str, usage=None) -> None:
        self.messages = FakeMessages(text, usage=usage)


def test_anthropic_gateway_requests_json_review_payload() -> None:
    client = FakeAnthropicClient(
        json.dumps(
            {
                "leads": [
                    {
                        "file_path": "app.py",
                        "line": 3,
                        "suspicion": "Possible bug",
                        "related_rule_ids": ["tests"],
                        "suggested_context": "diff",
                        "status": "verified",
                    }
                ],
                "findings": [
                    {
                        "file_path": "app.py",
                        "line": 3,
                        "severity": "medium",
                        "title": "Bug",
                        "behavior_at_risk": "Risk",
                        "evidence": "Evidence",
                        "suggested_action": "Fix",
                        "confidence": 0.88,
                    }
                ],
            }
        )
    )
    gateway = AnthropicReviewGateway(
        client=client,
        model="MiniMax-M2.7",
        max_tokens=500,
    )

    result = gateway.review(
        Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"),
        [
            CheckResult(
                name="unit",
                kind="tests",
                command="uv run pytest",
                exit_code=1,
                timed_out=False,
                duration_ms=20,
                output_excerpt="failed",
            )
        ],
    )

    call = client.messages.calls[0]
    assert call["model"] == "MiniMax-M2.7"
    assert call["temperature"] == 0
    assert "Return only JSON" in call["system"]
    assert result.findings[0].title == "Bug"
    assert result.leads[0].suspicion == "Possible bug"


def test_anthropic_gateway_logs_model_usage_and_estimated_cost(caplog) -> None:
    usage = type("Usage", (), {"input_tokens": 1000, "output_tokens": 500})()
    client = FakeAnthropicClient(json.dumps({"leads": [], "findings": []}), usage=usage)
    gateway = AnthropicReviewGateway(
        client=client,
        base_url="https://api.minimax.io/anthropic",
        model="MiniMax-M2.7",
        max_tokens=500,
        input_price_per_million_tokens=0.30,
        output_price_per_million_tokens=1.20,
    )

    with caplog.at_level(logging.INFO):
        gateway.review(Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"), [])

    assert "starting model review" in caplog.text
    assert "model review completed" in caplog.text
    assert "input_tokens=1000" in caplog.text
    assert "output_tokens=500" in caplog.text
    assert "estimated_cost_usd=0.000900" in caplog.text


def test_anthropic_gateway_accepts_fenced_json_response() -> None:
    client = FakeAnthropicClient(
        """
```json
{
  "leads": [],
  "findings": [
    {
      "file_path": "app.py",
      "line": 4,
      "severity": "high",
      "title": "Broken auth",
      "behavior_at_risk": "Users can access private data.",
      "evidence": "The diff bypasses the auth guard.",
      "suggested_action": "Restore the guard before returning data.",
      "confidence": 0.91
    }
  ]
}
```
"""
    )
    gateway = AnthropicReviewGateway(client=client)

    result = gateway.review(
        Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"), []
    )

    assert result.findings[0].title == "Broken auth"


def test_anthropic_pipeline_uses_gateway() -> None:
    class FakeGateway:
        def review(self, workspace, checks):
            return "result"

    assert AnthropicReviewPipeline(FakeGateway()).run("workspace", []) == "result"
