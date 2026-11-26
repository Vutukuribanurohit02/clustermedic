"""Shared read-only HTTP helper: GET only, timeouts, clean errors."""
import requests

from ._exec import ToolError

TIMEOUT_S = 10


def get_json(url: str, params: dict | None = None) -> dict:
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise ToolError(f"GET {url} failed: {e}") from e
    if r.status_code != 200:
        raise ToolError(f"GET {url} returned HTTP {r.status_code}")
    return r.json()
