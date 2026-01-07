from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class LogCenterHttpClient:
    def __init__(self, base_url: str, api_key: Optional[str], timeout_s: float, follow_redirects: bool):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_s, connect=timeout_s)
        self.follow_redirects = follow_redirects

    def headers(self) -> Dict[str, str]:
        h = {
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            h["x_api_key"] = self.api_key
        return h

    async def post_log(self, payload: Dict[str, Any]) -> httpx.Response:
        url = f"{self.base_url}/logs/"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=self.follow_redirects) as client:
            return await client.post(url, headers=self.headers(), json=payload)
