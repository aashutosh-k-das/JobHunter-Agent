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

from ..llm import answer_form_question


def _fill_modal(page: Page, modal: Locator, job: Job, resume: str, c: Criteria) -> list[str]:
    """Fill empty fields in the current Easy Apply step. Returns unanswerable labels."""
    unresolved: list[str] = []

    for el in modal.locator("input[type='text'], input[type='tel'], input:not([type]), textarea").all():
        if not el.is_visible() or el.input_value().strip():
            continue
        label = _label_for(page, el)
        if "cover letter" in label.lower():
            el.fill(job.get("cover_letter", ""))
            continue
        ans = _profile_answer(label, c) or answer_form_question(label, None, resume, c)
        if ans == "UNKNOWN":
            unresolved.append(label)
        else:
            el.fill(ans)

    for sel in modal.locator("select").all():
        if not sel.is_visible():
            continue
        current = sel.evaluate("s => s.options[s.selectedIndex]?.text || ''")
        if current and "select" not in current.lower():
            continue
        label = _label_for(page, sel)
        opts = [o for o in sel.locator("option").all_inner_texts() if "select" not in o.lower()]
        ans = _profile_answer(label, c) or answer_form_question(label, opts, resume, c)
        match = next((o for o in opts if o.strip().lower() == ans.strip().lower()), None)
        if match:
            sel.select_option(label=match)
        else:
            unresolved.append(label)

    for fs in modal.locator("fieldset").all():
        radios = fs.locator("input[type='radio']")
        if not radios.count() or fs.locator("input[type='radio']:checked").count():
            continue
        legend = fs.locator("legend, span").first.inner_text().strip()
        opts = [l.strip() for l in fs.locator("label").all_inner_texts()]
        ans = _profile_answer(legend, c) or answer_form_question(legend, opts, resume, c)
        target = fs.locator("label", has_text=ans).first
        if ans != "UNKNOWN" and target.count():
            target.click()
        else:
            unresolved.append(legend)

    return unresolved
