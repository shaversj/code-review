from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_path: Path = Path("code-review.db")
    github_app_id: int
    github_private_key_path: Path
    github_webhook_secret: str
    github_allowed_repos: str
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    sqs_queue_url: str
    sqs_visibility_timeout_seconds: int = Field(default=900, ge=30)
    sandbox_root: Path = Path(".sandboxes")
    stale_run_after_minutes: int = Field(default=60, ge=0)
    review_pipeline_provider: str = "deterministic"
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_max_tokens: int = Field(default=4000, ge=256)

    @property
    def allowed_repo_set(self) -> set[str]:
        return {item.strip() for item in self.github_allowed_repos.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
