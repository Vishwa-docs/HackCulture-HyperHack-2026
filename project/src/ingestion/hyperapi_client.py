"""HyperAPI client wrapper with retries, caching, and backoff."""
import json
import os
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..core.logging import get_logger
from ..core import paths
from ..core.utils import cache_key, load_json_cache, save_json_cache

log = get_logger(__name__)

CACHE_DIR = paths.CACHE / "hyperapi"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class HyperAPIAdapter:
    """Thin adapter around HyperAPI with retries, caching, and logging."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.environ.get("HYPERAPI_KEY", "")
        self.base_url = (base_url or os.environ.get("HYPERAPI_URL", "")).rstrip("/")
        self._client = httpx.Client(timeout=180.0)
        log.info(f"HyperAPI adapter initialized, base_url={self.base_url}")

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
    )
    def parse_page(self, image_path: Path) -> dict:
        """Parse a single page image via HyperAPI /parse endpoint."""
        ck = cache_key("parse", str(image_path))
        cached = load_json_cache(CACHE_DIR / f"parse_{ck}.json")
        if cached:
            return cached

        suffix = image_path.suffix.lower()
        ct_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        ct = ct_map.get(suffix, "application/octet-stream")

        with open(image_path, "rb") as f:
            files = {"file": (image_path.name, f, ct)}
            resp = self._client.post(
                f"{self.base_url}/parse",
                files=files,
                headers=self._headers(),
            )

        if resp.status_code == 401:
            raise PermissionError("HyperAPI: Invalid API key")
        resp.raise_for_status()
        result = resp.json()
        save_json_cache(CACHE_DIR / f"parse_{ck}.json", result)
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
    )
    def extract_fields(self, ocr_text: str) -> dict:
        """Extract structured fields from OCR text."""
        ck = cache_key("extract", ocr_text[:200])
        cached = load_json_cache(CACHE_DIR / f"extract_{ck}.json")
        if cached:
            return cached

        resp = self._client.post(
            f"{self.base_url}/extract",
            data={"ocr_text": ocr_text},
            headers=self._headers(),
            timeout=600.0,
        )
        resp.raise_for_status()
        result = resp.json()
        save_json_cache(CACHE_DIR / f"extract_{ck}.json", result)
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
    )
    def extract_lineitems(self, ocr_text: str) -> dict:
        """Extract validated line items."""
        ck = cache_key("lineitems", ocr_text[:200])
        cached = load_json_cache(CACHE_DIR / f"lineitems_{ck}.json")
        if cached:
            return cached

        resp = self._client.post(
            f"{self.base_url}/extract-lineitems",
            data={"ocr_text": ocr_text},
            headers=self._headers(),
            timeout=600.0,
        )
        resp.raise_for_status()
        result = resp.json()
        save_json_cache(CACHE_DIR / f"lineitems_{ck}.json", result)
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
    )
    def extract_entities(self, ocr_text: str) -> dict:
        """Extract entities with few-shot learning."""
        ck = cache_key("entities", ocr_text[:200])
        cached = load_json_cache(CACHE_DIR / f"entities_{ck}.json")
        if cached:
            return cached

        resp = self._client.post(
            f"{self.base_url}/extract-entities",
            data={"ocr_text": ocr_text},
            headers=self._headers(),
            timeout=600.0,
        )
        resp.raise_for_status()
        result = resp.json()
        save_json_cache(CACHE_DIR / f"entities_{ck}.json", result)
        return result

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
