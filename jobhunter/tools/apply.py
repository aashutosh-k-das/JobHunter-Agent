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

from .browser import SEL, Browser, _first, _human_pause


def apply_linkedin(job: Job, resume: str, c: Criteria) -> tuple[str, str]:
    page = Browser.get().page
    page.goto(job["url"], wait_until="domcontentloaded")
    _human_pause(2, 3)

    btn = _first(page, "li_easy_apply")
    if not btn:
        return ("external", "no Easy Apply button; redirected or external")
    btn.click()
    _human_pause(1, 2)

    modal = page.locator("div[data-test-modal], .jobs-easy-apply-modal").first
    if not modal.count():
        return ("error", "Easy Apply modal didn't open")

    for step in range(12):
        unresolved = _fill_modal(page, modal, job, resume, c)
        if unresolved:
            return ("needs_manual", f"unresolved questions: {', '.join(unresolved[:3])}")

        submit_btn = modal.locator("button[aria-label*='Submit application' i]").first
        if submit_btn.count():
            if c.apply.submit:
                submit_btn.click()
                _human_pause(2, 4)
                return ("applied", "submitted via Easy Apply")
            return ("ready_to_submit", "filled form, stopped at review (apply.submit is false)")

        nxt = modal.locator("button[aria-label*='Continue to next step' i], "
                            "button[aria-label*='Review your application' i]").first
        if not nxt.count():
            nxt = modal.locator("footer button.artdeco-button--primary").first
        if not nxt.count():
            return ("error", f"no next button on step {step}")
        nxt.click()
        _human_pause(1, 2)

    return ("error", "Easy Apply exceeded max step count")


def apply_naukri(job: Job, resume: str, c: Criteria) -> tuple[str, str]:
    page = Browser.get().page
    page.goto(job["url"], wait_until="domcontentloaded")
    _human_pause(2, 3)

    if _first(page, "nk_company_site"):
        return ("external", "applies on company site")

    btn = _first(page, "nk_apply")
    if not btn:
        return ("needs_manual", "no direct apply button found")
    if "already applied" in btn.inner_text().lower():
        return ("applied", "already applied previously")

    if not c.apply.submit:
        return ("ready_to_submit", "stopped at 1-click apply (apply.submit is false)")
    btn.click()
    _human_pause(2, 4)
    return ("applied", "clicked 1-click apply on Naukri")


APPLIERS = {
    "linkedin": apply_linkedin,
    "naukri": apply_naukri,
}
