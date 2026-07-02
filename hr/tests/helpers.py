"""Test helpers: mint RS256 tokens exactly like smarthr360-auth would."""

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PRIVATE_PEM = _key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

PUBLIC_PEM = (
    _key.public_key()
    .public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)


def mint_token(user_id: int, role: str = "EMPLOYEE", email: str | None = None,
               groups: list | None = None, **extra) -> str:
    payload = {
        "token_type": "access",
        "user_id": user_id,
        "email": email or f"user{user_id}@corp.com",
        "role": role,
        "groups": groups or [],
        "is_superuser": role == "ADMIN",
        "iss": "smarthr360",
        "exp": int(time.time()) + 300,
        **extra,
    }
    return jwt.encode(payload, PRIVATE_PEM, algorithm="RS256")


def auth_header(user_id: int, role: str = "EMPLOYEE", **kw) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {mint_token(user_id, role, **kw)}"}
