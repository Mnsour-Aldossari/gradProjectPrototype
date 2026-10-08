"""The backend's REST API, as the bridge and the comparison tool use it. Signs in again when the token expires."""

from __future__ import annotations

import os

import requests


class BackendError(RuntimeError):
    pass


def credentials(prefix: str = "UAV") -> tuple[str, str]:
    """UAV_USERNAME and UAV_PASSWORD: an account of the backend (the field operator's is enough to read).
    prefix "UAV_CONTROL": the supervisor's account that commands missions."""
    username, password = os.environ.get(f"{prefix}_USERNAME", ""), os.environ.get(f"{prefix}_PASSWORD", "")
    if not username or not password:
        raise BackendError(f"set {prefix}_USERNAME and {prefix}_PASSWORD to an account of the backend")
    return username, password


def detail(r: requests.Response) -> str:
    """The backend's reason (FastAPI's "detail"), as one line."""
    try:
        d = r.json().get("detail")
    except (ValueError, AttributeError):
        return r.text[:200]
    if isinstance(d, list):
        return "; ".join(str(e.get("msg", e)) for e in d)
    return str(d)


class Backend:
    def __init__(self, url: str, username: str, password: str, timeout_s: float = 10.0) -> None:
        self.url = url.rstrip("/")
        self._login = {"username": username, "password": password}
        self._timeout_s = timeout_s
        self._session = requests.Session()
        self._token: str | None = None

    def _sign_in(self) -> None:
        r = self._session.post(f"{self.url}/api/auth/login", json=self._login, timeout=self._timeout_s)
        if r.status_code != 200:
            raise BackendError(f"sign-in refused ({r.status_code}): check UAV_USERNAME and UAV_PASSWORD")
        self._token = r.json()["token"]

    def get(self, path: str, **params) -> object:
        for attempt in range(2):
            if self._token is None:
                self._sign_in()
            r = self._session.get(
                f"{self.url}{path}", params=params, headers={"Authorization": f"Bearer {self._token}"},
                timeout=self._timeout_s,
            )  # fmt: skip
            if r.status_code == 401 and attempt == 0:
                self._token = None  # expired: sign in once more
                continue
            if r.status_code != 200:
                raise BackendError(f"GET {path}: {r.status_code} {r.text[:200]}")
            return r.json()
        raise BackendError(f"GET {path}: not signed in")

    def post(self, path: str, body: dict | None = None, timeout_s: float | None = None) -> tuple[int, dict | str]:
        """(status code, the reply) for any answer the backend gives, the reason as text when refused; BackendError
        only when it cannot be reached or signed in to. timeout_s: longer for a start with PX4, which waits for PX4."""
        for attempt in range(2):
            if self._token is None:
                self._sign_in()
            r = self._session.post(
                f"{self.url}{path}", json=body, headers={"Authorization": f"Bearer {self._token}"},
                timeout=timeout_s or self._timeout_s,
            )  # fmt: skip
            if r.status_code == 401 and attempt == 0:
                self._token = None
                continue
            return r.status_code, (r.json() if r.ok else detail(r))
        raise BackendError(f"POST {path}: not signed in")

    def missions(self) -> list[dict]:
        return self.get("/api/missions")

    def mission(self, mission_id: int) -> dict:
        return self.get(f"/api/missions/{mission_id}")

    def readings(self, mission_id: int, after_id: int, limit: int) -> list[dict]:
        return self.get(f"/api/missions/{mission_id}/readings", after_id=after_id, limit=limit)

    def telemetry(self, mission_id: int, after_t: float, limit: int) -> list[dict]:
        return self.get(f"/api/missions/{mission_id}/telemetry", after_t=after_t, limit=limit)

    def detections(self, mission_id: int, method: str = "adaptive") -> list[dict]:
        return self.get(f"/api/missions/{mission_id}/detections", method=method)
