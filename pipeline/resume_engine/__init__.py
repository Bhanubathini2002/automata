"""LaTeX resume + cover letter tailor engine (LLM JSON → validate → compile hooks)."""

from .prompts import SYSTEM_RESUME, SYSTEM_CL, build_messages, build_cl_messages, repair_messages
from .tailor import tailor_job, run_batch
from .render import esc, find_fabrications, normalize, validate, BLOCKLIST

__all__ = [
    "SYSTEM_RESUME", "SYSTEM_CL", "build_messages", "build_cl_messages", "repair_messages",
    "tailor_job", "run_batch", "esc", "find_fabrications", "normalize", "validate", "BLOCKLIST",
]
