from __future__ import annotations

import json
from pathlib import Path

from code_review_app.ai.anthropic import AnthropicReviewGateway
from code_review_app.review.models import CheckResult, Workspace
from code_review_app.review.pipeline import AnthropicReviewPipeline


class FakeMessages:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = [type("TextBlock", (), {"type": "text", "text": self.text})()]
        return type("Message", (), {"content": content})()


class FakeAnthropicClient:
    def __init__(self, text: str) -> None:
        self.messages = FakeMessages(text)


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


def test_anthropic_pipeline_uses_gateway() -> None:
    class FakeGateway:
        def review(self, workspace, checks):
            return "result"

    assert AnthropicReviewPipeline(FakeGateway()).run("workspace", []) == "result"
