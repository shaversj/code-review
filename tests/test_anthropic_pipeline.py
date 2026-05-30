from __future__ import annotations

import json
import logging
from pathlib import Path

from code_review_app.ai.anthropic import MAX_MODEL_FINDINGS, SYSTEM_PROMPT, AnthropicReviewGateway
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
    assert result.model_usage is not None
    assert result.model_usage.model == "MiniMax-M2.7"
    assert result.model_usage.input_tokens == 0


def test_anthropic_prompt_asks_for_fewer_high_confidence_findings() -> None:
    assert f"At most {MAX_MODEL_FINDINGS} findings" in SYSTEM_PROMPT
    assert "confidence >= 0.80" in SYSTEM_PROMPT
    assert "Do not restate raw check failures" in SYSTEM_PROMPT


def test_anthropic_prompt_uses_structured_review_contract() -> None:
    for section in [
        "## Mission",
        "## Input",
        "## Output",
        "## Review Workflow",
        "## Severity Rubric",
        "## In Scope",
        "## Out Of Scope",
        "## Before Returning",
    ]:
        assert section in SYSTEM_PROMPT

    assert "A lead is for discovery" in SYSTEM_PROMPT
    assert "A finding is for a verified issue" in SYSTEM_PROMPT
    assert "up to 12 diverse leads" in SYSTEM_PROMPT
    assert "Use only these related_rule_ids" in SYSTEM_PROMPT
    assert "SECURITY" in SYSTEM_PROMPT
    assert "API_CONTRACT" in SYSTEM_PROMPT
    assert "security/privacy/data-loss" in SYSTEM_PROMPT
    assert "Redact secrets" in SYSTEM_PROMPT
    assert "Return valid JSON only" in SYSTEM_PROMPT


def test_anthropic_prompt_requires_review_categories() -> None:
    assert '"category": "significant_concerns|correctness|security|performance|maintainability"' in SYSTEM_PROMPT
    assert "Use significant_concerns only for merge-blocking" in SYSTEM_PROMPT


def test_anthropic_gateway_parses_and_normalizes_finding_category() -> None:
    client = FakeAnthropicClient(
        json.dumps(
            {
                "leads": [],
                "findings": [
                    {
                        "file_path": "app.py",
                        "line": 3,
                        "category": "API_CONTRACT",
                        "severity": "high",
                        "title": "Contract changed",
                        "behavior_at_risk": "Callers can break.",
                        "evidence": "The response shape changed.",
                        "suggested_action": "Update callers or preserve compatibility.",
                        "confidence": 0.91,
                    },
                    {
                        "file_path": "auth.py",
                        "line": 4,
                        "category": "privacy",
                        "severity": "high",
                        "title": "Private data exposed",
                        "behavior_at_risk": "Private user data can leak.",
                        "evidence": "The auth guard was removed.",
                        "suggested_action": "Restore the guard.",
                        "confidence": 0.92,
                    },
                    {
                        "file_path": "style.py",
                        "line": 5,
                        "category": "made_up",
                        "severity": "medium",
                        "title": "Unknown category",
                        "behavior_at_risk": "Behavior can regress.",
                        "evidence": "The model returned an unknown category.",
                        "suggested_action": "Use the default category.",
                        "confidence": 0.93,
                    },
                ],
            }
        )
    )

    result = AnthropicReviewGateway(client=client).review(
        Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"), []
    )

    assert [finding.category for finding in result.findings] == [
        "correctness",
        "security",
        "correctness",
    ]


def test_anthropic_gateway_filters_and_caps_model_findings() -> None:
    findings = []
    for index in range(MAX_MODEL_FINDINGS + 2):
        findings.append(
            {
                "file_path": "app.py",
                "line": index + 1,
                "severity": "medium",
                "title": f"Issue {index}",
                "behavior_at_risk": "Risk",
                "evidence": "Evidence",
                "suggested_action": "Fix",
                "confidence": 0.9,
            }
        )
    findings.append(
        {
            "file_path": "app.py",
            "line": 99,
            "severity": "medium",
            "title": "Weak issue",
            "behavior_at_risk": "Risk",
            "evidence": "Evidence",
            "suggested_action": "Fix",
            "confidence": 0.2,
        }
    )
    client = FakeAnthropicClient(json.dumps({"leads": [], "findings": findings}))

    result = AnthropicReviewGateway(client=client).review(
        Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"), []
    )

    assert len(result.findings) == MAX_MODEL_FINDINGS
    assert "Weak issue" not in {finding.title for finding in result.findings}


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
    result = gateway.review(
        Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"), []
    )
    assert result.model_usage is not None
    assert result.model_usage.provider == "anthropic-compatible"
    assert result.model_usage.model == "MiniMax-M2.7"
    assert result.model_usage.input_tokens == 1000
    assert result.model_usage.output_tokens == 500
    assert result.model_usage.estimated_cost_usd == 0.0009


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


def test_anthropic_gateway_normalizes_partial_model_items() -> None:
    client = FakeAnthropicClient(
        json.dumps(
            {
                "leads": [
                    {
                        "file_path": "app.py",
                        "line": "7",
                        "suspicion": "Check this",
                    }
                ],
                "findings": [
                    {
                        "file_path": "app.py",
                        "line": "7",
                        "severity": "medium",
                        "title": "Partial issue",
                        "evidence": "The model returned partial data.",
                        "confidence": "0.82",
                    }
                ],
            }
        )
    )
    gateway = AnthropicReviewGateway(client=client)

    result = gateway.review(
        Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+bug"), []
    )

    assert result.leads[0].line == 7
    assert result.leads[0].suggested_context == "No suggested context provided by model."
    assert result.findings[0].line == 7
    assert result.findings[0].behavior_at_risk == (
        "The model did not provide behavior-at-risk details."
    )
    assert result.findings[0].suggested_action == "Inspect the cited code and update if needed."
    assert result.findings[0].confidence == 0.82


def test_anthropic_pipeline_uses_gateway() -> None:
    class FakeGateway:
        def review(self, workspace, checks):
            return "result"

    assert AnthropicReviewPipeline(FakeGateway()).run("workspace", []) == "result"
