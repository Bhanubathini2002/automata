"""
Environment doctor - preflight checks for Automata production runs.

  python -m pipeline.run doctor
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Keys that must appear in .env (presence only - values never printed)
REQUIRED_ENV_KEYS = (
    "LLM_API_KEY",
)
OPTIONAL_ENV_KEYS = (
    "LLM_BASE_URL",
    "LLM_MODEL",
    "CAPSOLVER_API_KEY",
    "APPLY_EMAIL",
    "APPLY_PASSWORD",
    "GMAIL_ADDRESS",
    "GMAIL_PASSWORD",
    "CHROME_USER_DATA_DIR",
    "XELATEX",
    "PDFLATEX",
)

PYTHON_IMPORTS = (
    "openpyxl",
    "pypdf",
    "yaml",
    "playwright",
    "streamlit",
    "requests",
)


def _check_imports() -> list[dict[str, Any]]:
    rows = []
    for name in PYTHON_IMPORTS:
        try:
            importlib.import_module(name)
            rows.append({"check": f"import:{name}", "ok": True, "detail": "ok"})
        except ImportError as e:
            rows.append({"check": f"import:{name}", "ok": False, "detail": str(e)})
    return rows


def _check_playwright() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as e:
        return {
            "check": "playwright",
            "ok": False,
            "detail": f"not installed: {e} - pip install playwright && playwright install chromium",
        }
    # Probe whether chromium binary is available (best-effort)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return {"check": "playwright_chromium", "ok": True, "detail": "chromium launches"}
    except Exception as e:
        return {
            "check": "playwright_chromium",
            "ok": False,
            "detail": f"{type(e).__name__}: {e} - run: playwright install chromium",
        }


def _check_latex() -> list[dict[str, Any]]:
    from pipeline.resume_engine.render import latex_status

    st = latex_status()
    rows = [
        {
            "check": "xelatex",
            "ok": st["xelatex_ok"],
            "detail": st["xelatex"] or (
                f"MISSING - install MiKTeX ({st['install_windows']}) "
                f"or TeX Live ({st['install_linux']}) or set XELATEX"
            ),
        },
        {
            "check": "pdflatex",
            "ok": st["pdflatex_ok"],
            "detail": st["pdflatex"] or (
                f"MISSING - install MiKTeX ({st['install_windows']}) "
                f"or TeX Live ({st['install_linux']}) or set PDFLATEX"
            ),
        },
    ]
    return rows


def _env_keys_present() -> dict[str, bool]:
    """Return which expected keys are present in .env / os.environ (not values)."""
    from pipeline.config_io import load_dotenv, ENV_PATH

    file_keys: set[str] = set()
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() and v.strip().strip('"').strip("'"):
                file_keys.add(k.strip())
    load_dotenv()
    present: dict[str, bool] = {}
    for k in REQUIRED_ENV_KEYS + OPTIONAL_ENV_KEYS:
        present[k] = bool(os.environ.get(k) or k in file_keys)
    return present


def _check_env() -> list[dict[str, Any]]:
    present = _env_keys_present()
    rows = []
    for k in REQUIRED_ENV_KEYS:
        ok = present.get(k, False)
        rows.append({
            "check": f"env:{k}",
            "ok": ok,
            "detail": "present" if ok else "MISSING (required for resume LLM)",
            "required": True,
        })
    for k in OPTIONAL_ENV_KEYS:
        ok = present.get(k, False)
        rows.append({
            "check": f"env:{k}",
            "ok": True,  # optional - never fail doctor hard
            "detail": "present" if ok else "absent (optional)",
            "required": False,
            "present": ok,
        })
    return rows


def _check_browser_state() -> dict[str, Any]:
    from pipeline.config_io import default_chrome_user_data_dir, load_config

    cfg = load_config()
    path = (
        cfg.get("chrome_profile_path")
        or os.environ.get("CHROME_USER_DATA_DIR")
        or str(default_chrome_user_data_dir())
    )
    p = Path(path)
    exists = p.is_dir()
    return {
        "check": "browser_state",
        "ok": True,
        "detail": f"{path} ({'exists' if exists else 'will be created on first apply'})",
        "path": str(p),
    }


def run_doctor(*, probe_playwright: bool = True) -> dict[str, Any]:
    """Run all checks. ok=False if any required check fails."""
    checks: list[dict[str, Any]] = []
    checks.extend(_check_imports())
    if probe_playwright:
        checks.append(_check_playwright())
    else:
        try:
            importlib.import_module("playwright")
            checks.append({"check": "playwright", "ok": True, "detail": "import ok (chromium probe skipped)"})
        except ImportError as e:
            checks.append({"check": "playwright", "ok": False, "detail": str(e)})
    checks.extend(_check_latex())
    checks.extend(_check_env())
    checks.append(_check_browser_state())

    # Required failures: imports, latex engines, required env keys, playwright
    hard = []
    for c in checks:
        name = c["check"]
        if not c.get("ok"):
            if name.startswith("env:") and not c.get("required", True):
                continue
            if name == "browser_state":
                continue
            hard.append(name)

    return {
        "ok": len(hard) == 0,
        "failed": hard,
        "checks": checks,
        "product": "Automata",
        "hints": {
            "miktex": "https://miktex.org/",
            "texlive": "https://www.tug.org/texlive/",
            "playwright": "pip install playwright && playwright install chromium",
            "env": "cp config/example.env .env  then fill LLM_API_KEY etc.",
        },
    }


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Automata environment doctor")
    ap.add_argument("--json", action="store_true", help="Print full JSON report")
    ap.add_argument("--skip-playwright-probe", action="store_true")
    args = ap.parse_args(argv)
    report = run_doctor(probe_playwright=not args.skip_playwright_probe)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for c in report["checks"]:
            mark = "OK " if c.get("ok") else "FAIL"
            print(f"  [{mark}] {c['check']}: {c.get('detail', '')}")
        print()
        if report["ok"]:
            print("Doctor: all required checks passed.")
        else:
            print("Doctor: FAILED ->", ", ".join(report["failed"]))
            print("Install LaTeX (MiKTeX/TeX Live) before generate-resumes.")
            print("Hints:", json.dumps(report["hints"], indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
