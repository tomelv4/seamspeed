import os
from pathlib import Path

import requests

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "pacesensei"
CACHE_DIR = Path("/tmp/pacesensei_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_storage_key = None


def init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _request(method: str, path: str, **kw):
    global _storage_key
    for attempt in range(2):
        key = init_storage()
        headers = {"X-Storage-Key": key, **kw.pop("headers", {})}
        resp = requests.request(method, f"{STORAGE_URL}/objects/{path}", headers=headers, **kw)
        if resp.status_code == 503 and attempt == 0:
            _storage_key = None
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("storage unavailable")


def put_object(path: str, data: bytes, content_type: str) -> dict:
    return _request("PUT", path, headers={"Content-Type": content_type}, data=data, timeout=180).json()


def get_object(path: str) -> bytes:
    return _request("GET", path, timeout=120).content


def cache_path(path: str) -> Path:
    return CACHE_DIR / path.replace("/", "_")


def cached_file(path: str) -> Path:
    local = cache_path(path)
    if not local.exists():
        local.write_bytes(get_object(path))
    return local
