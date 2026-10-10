"""A small client for the Google Health API (https://developers.google.com/health)."""
from datetime import timedelta

import httpx
from cryptography.fernet import Fernet

from app.config import settings

API_URL = "https://health.googleapis.com/v4/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_PAGES = 40   # safety limit: never follow "next page" forever

SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth."
SCOPE_ACTIVITY = SCOPE_PREFIX + "activity_and_fitness.readonly"            # steps, workouts
SCOPE_METRICS = SCOPE_PREFIX + "health_metrics_and_measurements.readonly"  # resting HR, HRV
SCOPE_SLEEP = SCOPE_PREFIX + "sleep.readonly"


class GoogleHealthError(Exception):
    """A Google Health request failed."""


class AuthorizationExpired(GoogleHealthError):
    """The refresh token no longer works: the user removed access, or it expired. They must sign in again."""


# ---------- Refresh tokens: encrypted before they touch the database ----------

def encrypt_token(token):
    return Fernet(settings.token_encryption_key).encrypt(token.encode()).decode()


def decrypt_token(encrypted):
    return Fernet(settings.token_encryption_key).decrypt(encrypted.encode()).decode()


def get_access_token(refresh_token):
    """Trade the long-lived refresh token for an access token that works for about an hour."""
    res = httpx.post(TOKEN_URL, timeout=15, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
    })
    if res.status_code in (400, 401):
        raise AuthorizationExpired("Google no longer accepts this refresh token")
    if res.is_error:
        raise GoogleHealthError(f"Google token endpoint returned {res.status_code}")
    return res.json()["access_token"]


# ---------- The API ----------

def _civil(day):
    return {"date": {"year": day.year, "month": day.month, "day": day.day}}


class HealthClient:
    def __init__(self, access_token):
        self.http = httpx.Client(base_url=API_URL, timeout=20, headers={"Authorization": f"Bearer {access_token}"})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.http.close()

    def _request(self, method, path, **kwargs):
        try:
            res = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise GoogleHealthError(f"{path}: {type(e).__name__}") from e
        if res.status_code == 401:
            raise AuthorizationExpired("Google rejected the access token")
        if res.is_error:
            # Google's error message says what was wrong with the request. It holds no health data.
            try:
                message = res.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = ""
            raise GoogleHealthError(f"{path}: HTTP {res.status_code} {message}".strip())
        return res.json()

    def list_points(self, data_type, filter=None, page_size=None):
        """All data points of one type, newest first. `filter` narrows the time range."""
        points, page_token = [], None
        for _ in range(MAX_PAGES):
            params = {"filter": filter, "pageSize": page_size, "pageToken": page_token}
            body = self._request("GET", f"/dataTypes/{data_type}/dataPoints",
                                 params={k: v for k, v in params.items() if v is not None})
            points += body.get("dataPoints", [])
            page_token = body.get("nextPageToken")
            if not page_token:
                break
        return points

    def daily_rollup(self, data_type, start, end, max_days=90):
        """One total per calendar day (in the user's own timezone), for days from `start` up to but not
        including `end`. Google limits how many days one request may cover, so longer ranges are split."""
        rollups = []
        while start < end:
            chunk_end = min(start + timedelta(days=max_days), end)
            page_token = None
            for _ in range(MAX_PAGES):
                payload = {"range": {"start": _civil(start), "end": _civil(chunk_end)}, "windowSizeDays": 1}
                if page_token:
                    payload["pageToken"] = page_token
                body = self._request("POST", f"/dataTypes/{data_type}/dataPoints:dailyRollUp", json=payload)
                rollups += body.get("rollupDataPoints", [])
                page_token = body.get("nextPageToken")
                if not page_token:
                    break
            start = chunk_end
        return rollups
