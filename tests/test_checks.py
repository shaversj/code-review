from pathlib import Path

from code_review_app.sandbox.checks import CheckRunner, load_review_config


class FakeRunner:
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        assert command == ["uv", "run", "pytest"]
        return "1 passed"


def test_load_review_config_reads_checks(tmp_path: Path) -> None:
    config_path = tmp_path / ".code-review.yml"
    config_path.write_text(
        """
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 120
""",
        encoding="utf-8",
    )

    config = load_review_config(tmp_path)

    assert config.checks[0].name == "unit"
    assert config.checks[0].command == ["uv", "run", "pytest"]


def test_check_runner_returns_result(tmp_path: Path) -> None:
    config_path = tmp_path / ".code-review.yml"
    config_path.write_text(
        """
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 120
""",
        encoding="utf-8",
    )
    config = load_review_config(tmp_path)

    results = CheckRunner(FakeRunner()).run_checks(tmp_path, config)

    assert results[0].name == "unit"
    assert results[0].exit_code == 0
    assert results[0].output_excerpt == "1 passed"


class MissingCommandRunner:
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        raise FileNotFoundError("npm")


def test_check_runner_records_missing_command_as_failed_check(tmp_path: Path) -> None:
    config_path = tmp_path / ".code-review.yml"
    config_path.write_text(
        """
review:
  checks:
    tests:
      - name: npm test
        command: npm test
        timeout_seconds: 120
""",
        encoding="utf-8",
    )
    config = load_review_config(tmp_path)

    results = CheckRunner(MissingCommandRunner()).run_checks(tmp_path, config)

    assert results[0].exit_code == 127
    assert "Command not found" in results[0].output_excerpt
