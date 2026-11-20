"""Application submitters. Each returns (status, note)."""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from ..config import Criteria
from ..state import Job


def _profile_answer(label: str, c: Criteria) -> str | None:
    lab = label.lower()
    p = c.profile
    table = [
        (("phone", "mobile"), p.phone),
        (("email",), p.email),
        (("city", "location"), p.city),
        (("notice",), str(p.notice_period_days)),
        (("current ctc", "current salary", "current compensation"), str(p.current_ctc_lpa)),
        (("expected ctc", "expected salary", "expected compensation"), str(p.expected_ctc_lpa)),
        (("linkedin",), p.linkedin_url),
        (("github", "portfolio", "website"), p.github_url),
        (("years of experience", "years of work experience", "how many years"),
         str(int(c.filters.experience_years))),
    ]
    for needles, val in table:
        if val and any(n in lab for n in needles):
            return val
    for k, v in p.extra_answers.items():
        if k.lower() in lab:
            return v
    return None


def _label_for(page: Page, el: Locator) -> str:
    el_id = el.get_attribute("id")
    if el_id:
        lab = page.locator(f"label[for='{el_id}']").first
        if lab.count():
            return lab.inner_text().strip()
    return (el.get_attribute("aria-label") or el.get_attribute("placeholder") or "").strip()
