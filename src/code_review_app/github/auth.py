from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt


GITHUB_API_VERSION = "2022-11-28"


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: str


class GitHubAppAuth:
    def __init__(
        self,
        app_id: int,
        private_key_path: Path,
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.app_id = app_id
        self.private_key_path = private_key_path
        self.api_base_url = api_base_url.rstrip("/")

    def create_jwt(self, now: int | None = None) -> str:
        issued_at = int(time.time()) if now is None else now
        payload = {
            "iat": issued_at - 60,
            "exp": issued_at + 540,
            "iss": str(self.app_id),
        }
        private_key = self.private_key_path.read_bytes()
        return jwt.encode(payload, private_key, algorithm="RS256")

    def create_installation_token(self, installation_id: int) -> InstallationToken:
        response = httpx.post(
            f"{self.api_base_url}/app/installations/{installation_id}/access_tokens",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.create_jwt()}",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        return InstallationToken(token=body["token"], expires_at=body["expires_at"])

    def authenticated_clone_url(self, repo_full_name: str, token: str) -> str:
        return f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
