"""Application submitters. Each returns (status, note).

Safety: when criteria.apply.submit is False, forms are filled up to the final
review step and left open for you; nothing is submitted.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from ..config import Criteria
from ..llm import answer_form_question
from ..state import Job
from .browser import SEL, Browser, _first, _human_pause


def _profile_answer(label: str, c: Criteria) -> str | None:
    lab = label.lower()
    p = c.profile
    table = [
        (("phone", "mobile"), p.phone),
        (("email",), p.email),
        (("city", "location"), p.city),
        (("notice",), str(p.notice_period_days)),
        (("current ctc", "current salary", "current compensation"),
         "" if p.current_ctc_lpa is None else str(p.current_ctc_lpa)),
        (("expected ctc", "expected salary", "expected compensation"),
         "" if p.expected_ctc_lpa is None else str(p.expected_ctc_lpa)),
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

    for fs in modal.locator("fieldset").all():  # radio groups
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


def apply_linkedin(job: Job, resume: str, c: Criteria) -> tuple[str, str]:
    page = Browser.get().page
    page.goto(job["url"], wait_until="domcontentloaded")
    _human_pause(2, 3)
    btn = _first(page, "li_easy_apply")
    if not btn or "easy apply" not in btn.inner_text().lower():
        return "external", "No Easy Apply button"
    btn.click()
    _human_pause()

    modal = page.locator("div.jobs-easy-apply-modal, div[role='dialog']").first
    for _step in range(12):
        unresolved = _fill_modal(page, modal, job, resume, c)
        if unresolved:
            return "needs_manual", "Couldn't answer: " + "; ".join(unresolved)[:300]

        submit = modal.locator("button[aria-label*='Submit application']").first
        if submit.count():
            follow = modal.locator("label[for*='follow-company']").first
            if follow.count():
                follow.click()  # untick "follow company"
            if not c.apply.submit:
                return "ready_to_submit", "Filled; left at review step (submit disabled)"
            submit.click()
            _human_pause(2, 3)
            return "applied", "Submitted via Easy Apply"

        nxt = modal.locator("button[aria-label*='Continue to next step'], "
                            "button[aria-label*='Review your application']").first
        if not nxt.count():
            return "needs_manual", "Unexpected Easy Apply step"
        nxt.click()
        _human_pause()
        if modal.locator(".artdeco-inline-feedback--error").count():
            return "needs_manual", "Form validation error"
    return "needs_manual", "Too many steps"


def apply_naukri(job: Job, resume: str, c: Criteria) -> tuple[str, str]:
    page = Browser.get().page
    page.goto(job["url"], wait_until="domcontentloaded")
    _human_pause(2, 3)
    if _first(page, "nk_company_site"):
        return "external", "Applies on company website"
    btn = _first(page, "nk_apply")
    if not btn:
        return "needs_manual", "Apply button not found"
    if "applied" in btn.inner_text().lower():
        return "applied", "Already applied earlier"
    if not c.apply.submit:
        return "ready_to_submit", "Native Naukri apply available (submit disabled)"
    btn.click()
    _human_pause(2, 3)
    # Naukri may open a chatbot questionnaire; hand that to the user.
    if page.locator("[class*='chatbot']").count():
        return "needs_manual", "Recruiter questionnaire opened"
    return "applied", "Applied on Naukri"


APPLIERS = {"linkedin": apply_linkedin, "naukri": apply_naukri}
