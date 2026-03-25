from __future__ import annotations

from typing import Any, Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception


BASE_URL = "https://api.upstox.com"


def _is_rate_limit(exc: BaseException) -> bool:
    return isinstance(exc, UpstoxAPIError) and exc.status_code == 429


class UpstoxAPIError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__("Upstox API error %s (%s): %s" % (status_code, error_code, message))


class UpstoxClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer %s" % access_token,
            "Accept": "application/json",
        })

    @retry(
        retry=retry_if_exception(_is_rate_limit),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        url = BASE_URL + path
        response = self.session.get(url, params=params, timeout=30)
        if response.status_code != 200:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            raise UpstoxAPIError(
                status_code=response.status_code,
                error_code=body.get("errorCode", "UNKNOWN"),
                message=body.get("message", response.text[:200]),
            )
        return response.json()

    def post(self, path: str, data: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        url = BASE_URL + path
        response = self.session.post(url, data=data, headers=headers, timeout=30)
        if response.status_code != 200:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            raise UpstoxAPIError(
                status_code=response.status_code,
                error_code=body.get("errorCode", "UNKNOWN"),
                message=body.get("message", response.text[:200]),
            )
        return response.json()
