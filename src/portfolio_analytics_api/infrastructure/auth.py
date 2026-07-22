from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from portfolio_analytics_api.application import InvalidAccessTokenError

_JWT_ALGORITHM = "HS256"
_JWT_ISSUER = "portfolio-analytics-api"
_JWT_AUDIENCE = "portfolio-analytics-api"


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._password_hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._password_hash.verify(password, password_hash)
        except UnknownHashError:
            return False


class JwtAccessTokenService:
    def __init__(
        self,
        secret_key: str,
        expire_minutes: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if len(secret_key) < 32:
            raise ValueError("JWT secret key must contain at least 32 characters")
        if expire_minutes <= 0:
            raise ValueError("access token lifetime must be positive")
        self._secret_key = secret_key
        self._expire_minutes = expire_minutes
        self._clock = clock

    @property
    def expires_in_seconds(self) -> int:
        return self._expire_minutes * 60

    def issue(self, user_id: UUID) -> str:
        issued_at = self._clock()
        return jwt.encode(
            {
                "sub": str(user_id),
                "iat": issued_at,
                "exp": issued_at + timedelta(minutes=self._expire_minutes),
                "iss": _JWT_ISSUER,
                "aud": _JWT_AUDIENCE,
                "type": "access",
            },
            self._secret_key,
            algorithm=_JWT_ALGORITHM,
        )

    def verify(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[_JWT_ALGORITHM],
                audience=_JWT_AUDIENCE,
                issuer=_JWT_ISSUER,
                options={"require": ["sub", "iat", "exp", "iss", "aud", "type"]},
            )
            if payload["type"] != "access":
                raise InvalidAccessTokenError()
            return UUID(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError() from error
