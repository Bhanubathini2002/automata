"""Simple live job status (no screenshots)."""
from __future__ import annotations
import json, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE_DIR = ROOT / "data" / "applications" / "live"
STATUS_PATH = LIVE_DIR / "status.json"

def _ensure():
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

def update(**fields):
    _ensure()
    cur = {}
    if STATUS_PATH.is_file():
        try:
            cur = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    for k in ("screenshot", "screenshot_label", "screenshot_error"):
        cur.pop(k, None)
        fields.pop(k, None)
    cur.update(fields)
    cur["updated_at"] = datetime.now().isoformat(timespec="seconds")
    cur["updated_ts"] = time.time()
    STATUS_PATH.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return cur

def snapshot(page, label: str = "step"):
    return None

def read() -> dict:
    _ensure()
    if not STATUS_PATH.is_file():
        return {"state": "idle", "message": "No apply run yet"}
    try:
        d = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        for k in ("screenshot", "screenshot_label", "screenshot_error"):
            d.pop(k, None)
        return d
    except Exception:
        return {"state": "error", "message": "status.json unreadable"}
