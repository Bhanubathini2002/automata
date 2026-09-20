"""
Gmail OTP helper — real enough to run.

Primary path: IMAP search for a recent 6-digit code (app password / account password
from env). Fallback stub returns None so apply can mark needs_human instead of crashing.
Browser-based mail.google.com/u/N/ scraping is left as an optional Playwright hook.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
import time
from typing import Optional


OTP_RX = re.compile(r"\b(\d{6})\b")


class GmailOTPHelper:
    def __init__(
        self,
        address: str | None = None,
        password: str | None = None,
        imap_host: str = "imap.gmail.com",
    ):
        self.address = address or os.environ.get("GMAIL_ADDRESS") or os.environ.get("APPLY_EMAIL", "")
        self.password = password or os.environ.get("GMAIL_PASSWORD") or os.environ.get("APPLY_PASSWORD", "")
        self.imap_host = imap_host

    @property
    def configured(self) -> bool:
        return bool(self.address and self.password)

    def fetch_otp(
        self,
        sender_contains: str = "",
        subject_contains: str = "",
        wait_s: float = 60.0,
        poll_s: float = 5.0,
        newer_than_minutes: int = 10,
    ) -> Optional[str]:
        """
        Poll IMAP INBOX for a 6-digit OTP. Returns the code or None.
        Never raises on auth/network failure — returns None so the apply loop can skip.
        """
        if not self.configured:
            return None
        deadline = time.time() + wait_s
        while time.time() < deadline:
            try:
                code = self._imap_once(sender_contains, subject_contains, newer_than_minutes)
                if code:
                    return code
            except Exception:
                pass
            time.sleep(poll_s)
        return None

    def _imap_once(self, sender_contains: str, subject_contains: str,
                   newer_than_minutes: int) -> Optional[str]:
        M = imaplib.IMAP4_SSL(self.imap_host)
        try:
            M.login(self.address, self.password)
            M.select("INBOX")
            criteria = [f'(SINCE "{self._imap_date(newer_than_minutes)}")']
            # Broad search then filter in Python (IMAP FROM/SUBJECT are brittle)
            typ, data = M.search(None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return None
            ids = data[0].split()
            # newest first
            for uid in reversed(ids[-40:]):
                typ, msg_data = M.fetch(uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                frm = msg.get("From", "")
                subj = msg.get("Subject", "")
                if sender_contains and sender_contains.lower() not in frm.lower():
                    continue
                if subject_contains and subject_contains.lower() not in subj.lower():
                    continue
                body = self._body(msg)
                # Prefer codes near "code" / "verification" / "otp"
                for m in OTP_RX.finditer(body):
                    ctx = body[max(0, m.start() - 40): m.end() + 40].lower()
                    if any(k in ctx for k in ("code", "otp", "verif", "passcode", "security")):
                        return m.group(1)
                # fallback: first 6-digit in recent mail matching filters
                m = OTP_RX.search(body)
                if m and (sender_contains or subject_contains):
                    return m.group(1)
            return None
        finally:
            try:
                M.logout()
            except Exception:
                pass

    @staticmethod
    def _imap_date(newer_than_minutes: int) -> str:
        import datetime
        d = datetime.datetime.utcnow() - datetime.timedelta(minutes=max(newer_than_minutes, 1))
        return d.strftime("%d-%b-%Y")

    @staticmethod
    def _body(msg) -> str:
        parts = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ("text/plain", "text/html"):
                    try:
                        parts.append(part.get_payload(decode=True).decode(errors="replace"))
                    except Exception:
                        pass
        else:
            try:
                parts.append(msg.get_payload(decode=True).decode(errors="replace"))
            except Exception:
                parts.append(str(msg.get_payload()))
        return "\n".join(parts)

    def fetch_otp_via_playwright(self, page, expected_account: str | None = None) -> Optional[str]:
        """
        Optional: read OTP from an already-open Gmail tab (mail.google.com/mail/u/N/).
        Tries u/0..u/2 until page title matches expected_account.
        Does not click mail rows — reads tr.zA preview text (COMPLETE_WORKFLOW §10).
        """
        expected = (expected_account or self.address or "").lower()
        try:
            for idx in range(3):
                page.goto(f"https://mail.google.com/mail/u/{idx}/#inbox", wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                title = (page.title() or "").lower()
                if expected and expected.split("@")[0] not in title and expected not in title:
                    continue
                text = page.evaluate(
                    """() => [...document.querySelectorAll('tr.zA')]
                        .slice(0, 15)
                        .map(r => r.innerText)
                        .join('\\n')"""
                )
                for m in OTP_RX.finditer(text or ""):
                    ctx = (text or "")[max(0, m.start() - 40): m.end() + 40].lower()
                    if any(k in ctx for k in ("code", "otp", "verif", "passcode")):
                        return m.group(1)
            return None
        except Exception:
            return None
