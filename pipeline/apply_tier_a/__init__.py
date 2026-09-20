"""Tier A Playwright auto-apply: sequential, CapSolver, Gmail OTP, hard safety rules."""

from .apply import apply_to, run_excel_batch
from .fieldmap import resolve, fuzzy_option, same_answer, polarity_safe, ABORT, PREFER_NOT
from .capsolver import CapSolverClient
from .gmail_otp import GmailOTPHelper

__all__ = [
    "apply_to", "run_excel_batch",
    "resolve", "fuzzy_option", "same_answer", "polarity_safe", "ABORT", "PREFER_NOT",
    "CapSolverClient", "GmailOTPHelper",
]
