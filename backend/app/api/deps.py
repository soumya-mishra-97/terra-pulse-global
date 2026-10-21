"""FastAPI dependencies: DB session, container services, demo identity and rate limiting."""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

USER_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


def get_container(request: Request):
    return request.app.state.container


def get_session(container=Depends(get_container)) -> Iterator[Session]:
    session = container.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_user(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    """Demo identity. Production must replace this with verified OIDC/JWT claims (see docs/architecture.md)."""
    user = (x_user_id or "demo-user").strip()
    if not USER_RE.match(user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid X-User-Id header.")
    return user


class RateLimiter:
    """In-process sliding-window limiter. Replace with Redis/API-gateway limits when running >1 replica."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_seconds - (now - q[0])) + 1
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded. Please wait and retry.",
                                    headers={"Retry-After": str(retry)})
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
