"""Decide whether a post is someone hiring, and whether it names the job."""
from __future__ import annotations

import re

_HIRING = [re.compile(p, re.IGNORECASE) for p in (
    r"\bhiring\b",
    r"#\w*hiring\w*",
    r"#job(?:opening|openings|alert|alerts|vacancy|vacancies)\b",
    r"\b(?:job|new|urgent|immediate|multiple|current)\s+openings?\b",
    r"\bopenings?\s+(?:for|in|at)\b",
    r"\bwe have (?:an? )?openings?\b",
    r"\bvacanc(?:y|ies)\b",
    r"\bpositions?\s+(?:open|available)\b",
    r"\bopen\s+(?:positions?|roles?)\b",
    r"\bjoin\s+(?:our|my|the)\s+team\b",
    r"\bapply\s+(?:now|here|today|via|at|through|using)\b",
    r"\b(?:send|share|drop|email|mail)\b[^.\n]{0,30}?\b(?:cv|resume|résumé)s?\b",
    r"\b(?:dm|inbox|message)\s+me\b",
    r"\breferrals?\b",
    r"\bimmediate\s+joiners?\b",
    r"\bwalk[- ]?in\b",
    r"\blooking\s+for\s+(?:an?|talented|candidates|someone|people)\b",
)]

_SEEKER = [re.compile(p, re.IGNORECASE) for p in (
    r"#?\bopen\s?to\s?work\b",
    r"\b(?:i am|i'm|im)\s+(?:actively\s+|currently\s+|now\s+)?(?:looking|seeking|searching)\s+for\s+"
    r"(?:(?:a|an|new|my|next|full[- ]time|part[- ]time)\s+)*(?:job|role|opportunit|position|opening)",
    r"\b(?:i am|i'm|im)\s+(?:actively\s+|currently\s+|now\s+)?seeking\s+"
    r"(?:(?:new|full[- ]time|part[- ]time)\s+)*(?:job|role|opportunit|position)",
    r"\b(?:i am|i'm|im)\s+an?\s+immediate\s+joiner",
)]


def _normalise(text: str) -> str:
    return (text or "").replace("’", "'").replace("‘", "'")


def is_hiring_post(text: str) -> bool:
    """Has hiring language, and doesn't read like the author is the one job hunting."""
    body = _normalise(text)
    if not any(p.search(body) for p in _HIRING):
        return False
    return not any(p.search(body) for p in _SEEKER)


def mentions_title(text: str, job_title: str) -> bool:
    """Every word of the job title starts a word somewhere in the text ('analyst' matches 'Analysts')."""
    words = [w.rstrip(".") for w in re.findall(r"[\w+#.]+", (job_title or "").lower())]
    words = [w for w in words if w]
    body = _normalise(text).lower()
    return bool(words) and all(re.search(r"(?<!\w)" + re.escape(w), body) for w in words)
