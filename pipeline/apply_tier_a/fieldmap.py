"""Deterministic label -> answer. Legal attestations -> ABORT. Never invent answers."""
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ABORT = "__ABORT__"
PREFER_NOT = "__PREFER_NOT__"


def _load_profile() -> dict:
    for p in (
        ROOT / "data" / "profile.json",
        ROOT / "config" / "profile.example.json",
    ):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {
        "identity": {},
        "work_auth": {
            "authorized_to_work_us": "Yes",
            "requires_sponsorship_now_or_future": "No",
        },
        "eeo": {},
        "education": {},
        "employment": {},
        "compensation": {},
        "standard_answers": {"start_date_offset_days": 14, "na_text": "N/A"},
        "essays": {},
    }


P = _load_profile()


def _start_date():
    d = datetime.date.today() + datetime.timedelta(
        days=int(P.get("standard_answers", {}).get("start_date_offset_days", 14))
    )
    return d


def _g(*keys, default=""):
    cur = P
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur if cur is not None else default


RULES = [
    (r"unrestricted work authorization|authorized to work (in the )?(united states|u\.?s\.?)",
     _g("work_auth", "authorized_to_work_us", default="Yes")),
    (r"require (employment-based )?visa sponsorship|require sponsorship|need sponsorship",
     _g("work_auth", "requires_sponsorship_now_or_future", default="No")),

    (r"security clearance|clearance level|ts/sci|top secret|polygraph", ABORT),
    (r"are you a (u\.?s\.?|united states) citizen|citizenship status|permanent resident|green card", ABORT),
    (r"\bssn\b|social security|date of birth|\bdob\b", ABORT),
    (r"sponsor|sponsorship|visa (support|sponsor)|h-?1b",
     _g("work_auth", "requires_sponsorship_now_or_future", default="No")),
    (r"legally (authori[sz]ed|eligible) to work|authori[sz]ed to work|right to work|work authori",
     _g("work_auth", "authorized_to_work_us", default="Yes")),
    (r"age range|age band|what is your age|birth year", PREFER_NOT),
    (r"sexual orientation|lgbt|transgender|gender identity", PREFER_NOT),
    (r"hispanic|latino", _g("eeo", "hispanic_or_latino")),
    (r"\brace\b|ethnic", _g("eeo", "race")),
    (r"veteran", _g("eeo", "veteran_status")),
    (r"disability|disabled", _g("eeo", "disability_status")),
    (r"^gender$|gender:|your gender", _g("eeo", "gender")),
    (r"preferred (first )?name", _g("identity", "preferred_first_name")),
    (r"legal first name|first name|given name|^fname", _g("identity", "first_name")),
    (r"legal last name|last name|surname|family name|^lname", _g("identity", "last_name")),
    (r"middle name|middle initial", ""),
    (r"full name|^name$|your name|signature|electronic signature", _g("identity", "full_name")),
    (r"confirm email|retype email|verify email", _g("identity", "email")),
    (r"e-?mail", _g("identity", "email")),
    (r"mobile (phone|number)|cell phone|primary (contact )?(phone|number)|phone number|^phone",
     _g("identity", "phone_digits")),
    (r"linked-?in", _g("identity", "linkedin")),
    (r"address line 2|apt|suite|unit", _g("identity", "address_line2")),
    (r"address line 1|street address|^address", _g("identity", "address_line1")),
    (r"^city|town", _g("identity", "city")),
    (r"state|province", _g("identity", "state_full")),
    (r"zip|postal", _g("identity", "postal_code")),
    (r"country|nation", _g("identity", "country_full")),
    (r"pronoun", _g("identity", "pronouns")),
    (r"school|university|college|institution", _g("education", "school")),
    (r"degree", _g("education", "degree_short")),
    (r"field of study", _g("education", "field_of_study")),
    (r"major|concentration", _g("education", "major")),
    (r"gpa|grade point", _g("education", "gpa")),
    (r"graduat", _g("education", "grad_year")),
    (r"current company|current employer|company name|employer name|most recent employer|present employer",
     _g("employment", "current_employer")),
    (r"current (job )?title|job title|position title|^title",
     _g("employment", "current_title")),
    (r"years? of (professional |relevant )?experience|total experience",
     _g("employment", "years_total")),
    (r"desired (base )?(pay|salary)|salary expectation|expected (salary|compensation)",
     _g("compensation", "base_number")),
    (r"available to start|start date|earliest.*start|when can you start", "__START_DATE__"),
    (r"willing to relocate|relocation", _g("standard_answers", "relocate", default="Yes")),
    (r"willing to travel|travel requirement", _g("standard_answers", "travel", default="Yes")),
    (r"notice period", _g("standard_answers", "notice_period", default="2 weeks")),
    (r"previously (employed|worked)|former employee|worked (here|for us|at)",
     _g("standard_answers", "worked_here_before", default="No")),
    (r"relative|family member|know anyone",
     _g("standard_answers", "related_to_employee", default="No")),
    (r"non-?compet", _g("standard_answers", "non_compete", default="No")),
    (r"text (message|you)|sms", _g("standard_answers", "sms_consent", default="Yes")),
    (r"how did you (hear|find|learn)|source|referral source",
     _g("standard_answers", "how_did_you_hear", default="Company Website")),
    (r"who referred", _g("standard_answers", "na_text", default="N/A")),
    (r"cover letter", "__COVER_LETTER__"),
    (r"(describe|tell us about).*(ai|llm|project)", _g("essays", "ai_project")),
    (r"why (are you|do you want)|why this (role|company)|interest in",
     _g("essays", "why_interested")),
    (r"github|portfolio|personal website|links", _g("essays", "links")),
    (r"anything else|additional information", _g("essays", "strengths")),
    (r"^why [a-z][a-z0-9&.\- ]{1,28}\??\*?$", _g("essays", "why_interested")),
    (r"arbitration|agree(ment)? to arbitrate", "Yes"),
    (r"(have you )?read .{0,30}(policy|agreement|terms)|acknowledge", "Yes"),
    (r"(do you )?(agree|consent) to", "Yes"),
]

COMPILED = [(re.compile(p, re.I), v) for p, v in RULES]


def resolve(label: str):
    if not label:
        return None
    clean = re.sub(r"\s+", " ", label).strip().lower()
    clean = re.sub(r"[*:\u2217]|\(required\)|\(optional\)", "", clean).strip()
    for rx, val in COMPILED:
        if rx.search(clean):
            if val == "__START_DATE__":
                return _start_date().strftime("%m/%d/%Y")
            if val == "__COVER_LETTER__":
                return _g("essays", "why_interested")
            return val
    return None


def fuzzy_option(want: str, options: list):
    if not options:
        return None
    w = (want or "").strip().lower()
    opts = [(o, (o or "").strip().lower()) for o in options]
    if want == PREFER_NOT:
        for o, lo in opts:
            if re.search(r"prefer not|decline|do not wish|don't wish|not to answer|withhold", lo):
                return o
        return None
    for o, lo in opts:
        if lo == w:
            return o
    for o, lo in opts:
        if lo.startswith(w) and len(w) > 1:
            return o

    def _wordish(needle, hay):
        return re.search(r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])", hay) is not None

    for o, lo in opts:
        if not w:
            continue
        if _wordish(w, lo) or _wordish(lo, w):
            if re.search(r"\bnot\b|\bno\b", lo) != re.search(r"\bnot\b|\bno\b", w):
                continue
            return o
    if w in ("yes", "no"):
        for o, lo in opts:
            if re.match(rf"^{w}\b", lo):
                return o
    CONCEPTS = [(r"veteran", r"\bnot\b"), (r"disab", r"\bno\b|\bnot\b")]
    for concept_rx, neg_rx in CONCEPTS:
        if re.search(concept_rx, w) and re.search(neg_rx, w):
            for o, lo in opts:
                if re.search(concept_rx, lo) and re.search(neg_rx, lo):
                    if re.search(r"wish|decline|prefer not|self-?identify", lo):
                        continue
                    return o
    return None


def same_answer(intended: str, observed: str) -> bool:
    if not observed:
        return False
    a = re.sub(r"[^a-z0-9 ]+", " ", (intended or "").lower()).strip()
    b = re.sub(r"[^a-z0-9 ]+", " ", observed.lower()).strip()
    if not a:
        return False
    if a == b:
        return True
    neg = lambda s: bool(re.search(r"\bnot\b|\bno\b|\bnone\b", s))
    if neg(a) != neg(b):
        return False
    wb = lambda n, h: re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", h)
    return bool(wb(a, b) or wb(b, a)) or b.startswith(a[:24]) or a.startswith(b[:24])


def polarity_safe(want: str, chosen: str) -> bool:
    if not chosen:
        return False
    w_neg = bool(re.search(r"\bnot\b|\bno\b|\bnone\b", (want or "").lower()))
    c_neg = bool(re.search(r"\bnot\b|\bno\b|\bnone\b", chosen.lower()))
    return w_neg == c_neg
