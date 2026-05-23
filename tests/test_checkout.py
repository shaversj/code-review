from pathlib import Path

from code_review_app.sandbox.checkout import CheckoutManager


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        self.commands.append(command)
        if command[:2] == ["git", "diff"]:
            return "diff --git a/app.py b/app.py\n+print('hello')\n"
        return ""


def test_checkout_manager_runs_expected_git_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    manager = CheckoutManager(tmp_path, runner)

    workspace = manager.prepare(
        repo_url="https://x-access-token:TOKEN@github.com/owner/repo.git",
        review_run_id=5,
        base_sha="base",
        head_sha="head",
    )

    assert workspace.path == tmp_path / "run-5"
    assert "print('hello')" in workspace.diff
    assert runner.commands[0][:2] == ["git", "clone"]
    assert ["git", "checkout", "head"] in runner.commands
