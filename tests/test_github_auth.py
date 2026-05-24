from __future__ import annotations

import time
from pathlib import Path

import jwt
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response

from code_review_app.github.auth import GitHubAppAuth


def write_private_key(path: Path) -> bytes:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_create_jwt_uses_rs256_app_id_and_short_lifetime(tmp_path: Path) -> None:
    public_key = write_private_key(tmp_path / "app.pem")
    auth = GitHubAppAuth(app_id=123, private_key_path=tmp_path / "app.pem")
    now = int(time.time())

    token = auth.create_jwt(now=now)

    payload = jwt.decode(token, public_key, algorithms=["RS256"])
    assert payload["iss"] == "123"
    assert payload["iat"] == now - 60
    assert payload["exp"] == now + 540


@respx.mock
def test_create_installation_token_exchanges_jwt_for_token(tmp_path: Path) -> None:
    write_private_key(tmp_path / "app.pem")
    route = respx.post("https://api.github.com/app/installations/42/access_tokens").mock(
        return_value=Response(
            201, json={"token": "ghs_123", "expires_at": "2026-05-24T12:00:00Z"}
        )
    )
    auth = GitHubAppAuth(app_id=123, private_key_path=tmp_path / "app.pem")

    token = auth.create_installation_token(installation_id=42)

    assert token.token == "ghs_123"
    assert token.expires_at == "2026-05-24T12:00:00Z"
    assert route.calls[0].request.headers["authorization"].startswith("Bearer ")
    assert route.calls[0].request.headers["x-github-api-version"] == "2022-11-28"


def test_authenticated_clone_url_uses_installation_token(tmp_path: Path) -> None:
    write_private_key(tmp_path / "app.pem")
    auth = GitHubAppAuth(app_id=123, private_key_path=tmp_path / "app.pem")

    assert (
        auth.authenticated_clone_url("owner/repo", "ghs_123")
        == "https://x-access-token:ghs_123@github.com/owner/repo.git"
    )
