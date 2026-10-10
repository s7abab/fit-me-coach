import httpx

from app.config import settings


class VoyageError(Exception):
    pass


def post(path, payload):
    try:
        res = httpx.post(
            f"{settings.voyage_base_url}/{path}", timeout=30, json=payload,
            headers={"Authorization": f"Bearer {settings.voyage_api_key}"},
        )
    except httpx.HTTPError as e:
        raise VoyageError(f"{path}: {type(e).__name__}") from e
    if res.is_error:
        raise VoyageError(f"{path}: {res.status_code} {res.text[:200]}")
    return res.json()
