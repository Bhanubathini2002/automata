"""Load/save non-secret config (YAML) and secrets (.env)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG_YAML = DATA / "config.yaml"
ENV_PATH = ROOT / ".env"


def default_chrome_user_data_dir() -> Path:
    """Durable Playwright/Chrome profile - one-time Gmail login persists here."""
    return DATA / "browser_state"


DEFAULT_CONFIG: dict[str, Any] = {
    "jobs_excel": "",
    "addresses_excel": "",
    "base_resume_tex": "",
    "base_cover_tex": "",
    "ats_prompt": "",
    "llm_base_url": "https://api.deepseek.com/v1",
    "llm_model": "deepseek-chat",
    "chrome_profile_path": str(DATA / "browser_state"),
    "xelatex_path": "",
    "pdflatex_path": "",
    "output_root": str(DATA),
    "max_experience_years": 5,
    "default_city_st": "Houston, TX",
}


def ensure_data_dirs() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for sub in ("Input", "Output", "Resume/output", "applications", "browser_state", "staging"):
        (DATA / sub).mkdir(parents=True, exist_ok=True)


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Parse .env into a dict and inject into os.environ (without overwriting set vars)."""
    path = path or ENV_PATH
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        out[k] = v
        os.environ.setdefault(k, v)
    return out


def save_dotenv(secrets: dict[str, str], path: Path | None = None) -> None:
    """Write secrets to .env. Empty values keep prior entries unless explicitly cleared."""
    path = path or ENV_PATH
    existing = load_dotenv(path) if path.is_file() else {}
    existing.update({k: v for k, v in secrets.items() if v is not None})
    lines = ["# Auto-written by Automata UI - do not commit\n"]
    for k in sorted(existing):
        if existing[k] == "":
            continue
        lines.append(f"{k}={existing[k]}\n")
    path.write_text("".join(lines), encoding="utf-8")
    for k, v in existing.items():
        if v:
            os.environ[k] = v


def load_config() -> dict[str, Any]:
    """Reload config.yaml + .env; returns last saved values merged with defaults."""
    ensure_data_dirs()
    load_dotenv()
    cfg = dict(DEFAULT_CONFIG)
    cfg["chrome_profile_path"] = str(default_chrome_user_data_dir())
    if CONFIG_YAML.is_file():
        try:
            import yaml
            data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    # env overrides
    cfg["llm_base_url"] = os.environ.get("LLM_BASE_URL", cfg["llm_base_url"])
    cfg["llm_model"] = os.environ.get("LLM_MODEL", cfg["llm_model"])
    chrome = os.environ.get("CHROME_USER_DATA_DIR") or cfg.get("chrome_profile_path") or ""
    if not chrome:
        chrome = str(default_chrome_user_data_dir())
    cfg["chrome_profile_path"] = chrome
    if os.environ.get("XELATEX"):
        cfg["xelatex_path"] = os.environ["XELATEX"]
    if os.environ.get("PDFLATEX"):
        cfg["pdflatex_path"] = os.environ["PDFLATEX"]
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    ensure_data_dirs()
    try:
        import yaml
        CONFIG_YAML.write_text(
            yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except ImportError:
        import json
        CONFIG_YAML.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def secret(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default)


def apply_latex_env_from_config(cfg: dict[str, Any] | None = None) -> None:
    """Push configured XELATEX/PDFLATEX into os.environ if set in config/.env."""
    cfg = cfg or load_config()
    for key, env_key in (("xelatex_path", "XELATEX"), ("pdflatex_path", "PDFLATEX")):
        val = (cfg.get(key) or os.environ.get(env_key) or "").strip()
        if val:
            os.environ[env_key] = val
