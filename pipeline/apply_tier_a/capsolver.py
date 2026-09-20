"""CapSolver client - reCaptchaV2 / V3 / Cloudflare Turnstile only (no hCaptcha)."""
from __future__ import annotations

import os
import time
from typing import Any

import requests

API = "https://api.capsolver.com"


class CapSolverClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("CAPSOLVER_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("CAPSOLVER_API_KEY not set")
        r = requests.post(f"{API}{path}", json={"clientKey": self.api_key, **payload}, timeout=60)
        r.raise_for_status()
        return r.json()

    def create_task(self, task: dict) -> str:
        data = self._post("/createTask", {"task": task})
        if data.get("errorId"):
            raise RuntimeError(f"CapSolver createTask: {data.get('errorDescription')}")
        return data["taskId"]

    def get_result(self, task_id: str, poll_s: float = 3.0, timeout_s: float = 120.0) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            data = self._post("/getTaskResult", {"taskId": task_id})
            if data.get("status") == "ready":
                return data.get("solution") or {}
            if data.get("errorId"):
                raise RuntimeError(f"CapSolver result: {data.get('errorDescription')}")
            time.sleep(poll_s)
        raise TimeoutError(f"CapSolver task {task_id} timed out")

    def solve_recaptcha_v2(self, website_url: str, website_key: str,
                           is_invisible: bool = False) -> str:
        task = {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": website_key,
            "isInvisible": is_invisible,
        }
        tid = self.create_task(task)
        sol = self.get_result(tid)
        return sol.get("gRecaptchaResponse") or sol.get("token") or ""

    def solve_recaptcha_v3(self, website_url: str, website_key: str,
                           page_action: str = "submit", min_score: float = 0.7) -> str:
        task = {
            "type": "ReCaptchaV3TaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": website_key,
            "pageAction": page_action,
            "minScore": min_score,
        }
        tid = self.create_task(task)
        sol = self.get_result(tid)
        return sol.get("gRecaptchaResponse") or sol.get("token") or ""

    def solve_turnstile(self, website_url: str, website_key: str) -> str:
        task = {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }
        tid = self.create_task(task)
        sol = self.get_result(tid)
        return sol.get("token") or ""

    def balance(self) -> Any:
        if not self.api_key:
            return None
        data = self._post("/getBalance", {})
        return data.get("balance")
