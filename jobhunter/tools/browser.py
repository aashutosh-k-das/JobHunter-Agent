"""Playwright session with a persistent, manually-logged-in browser profile."""
from __future__ import annotations

import random
import time

from playwright.sync_api import BrowserContext, Page, sync_playwright

from ..config import ENV

SEL = {
    "li_card": ["li[data-occludable-job-id]", "div.job-card-container"],
    "li_title": ["a.job-card-list__title--link", "a.job-card-container__link", "a[href*='/jobs/view/']"],
    "li_company": [".artdeco-entity-lockup__subtitle", ".job-card-container__primary-description"],
    "li_location": [".artdeco-entity-lockup__caption", ".job-card-container__metadata-item"],
    "li_desc": ["#job-details", ".jobs-description__content", ".jobs-box__html-content"],
    "li_easy_apply": ["button.jobs-apply-button", "button[aria-label*='Easy Apply']"],
    "nk_card": ["div.srp-jobtuple-wrapper", "article.jobTuple"],
    "nk_title": ["a.title"],
    "nk_company": ["a.comp-name", ".comp-name"],
    "nk_location": [".locWdth", ".loc-wrap", ".location"],
    "nk_desc": ["[class*='dang-inner-html']", "section[class*='job-desc']", ".job-desc"],
    "nk_apply": ["#apply-button", "button.apply-button"],
    "nk_company_site": ["#company-site-button", "button.company-site-button"],
}


def _human_pause(lo: float = 1.0, hi: float = 2.5) -> None:
    time.sleep(random.uniform(lo, hi))


def _first(scope, key: str):
    for s in SEL[key]:
        loc = scope.locator(s).first
        if loc.count():
            return loc
    return None


def _text(scope, key: str) -> str:
    loc = _first(scope, key)
    return loc.inner_text().strip() if loc else ""


class Browser:
    _inst: "Browser | None" = None

    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self.ctx: BrowserContext = self._pw.chromium.launch_persistent_context(
            ENV.profile_dir, headless=ENV.headless, viewport={"width": 1366, "height": 900},
        )
        self.page: Page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()

    @classmethod
    def get(cls) -> "Browser":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    @classmethod
    def close(cls) -> None:
        if cls._inst:
            cls._inst.ctx.close()
            cls._inst._pw.stop()
            cls._inst = None

    # ---------------------------------------------------------------- login
    def login_interactive(self) -> None:
        for url in ("https://www.linkedin.com/login", "https://www.naukri.com/nlogin/login"):
            self.page.goto(url)
            input(f"Log in at {url} in the opened browser, then press Enter here... ")

    # ------------------------------------------------------------- LinkedIn
    def search_linkedin(self, keywords: str, location: str, limit: int) -> list[Job]:
        from urllib.parse import quote_plus
        from ..state import Job
        url = (f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(keywords)}"
               f"&location={quote_plus(location)}&f_AL=true&f_TPR=r604800")
        p = self.page
        p.goto(url, wait_until="domcontentloaded")
        _human_pause(2, 4)
        if "login" in p.url or "authwall" in p.url:
            raise RuntimeError("Not logged in to LinkedIn. Run: python -m jobhunter login")

        jobs: list[Job] = []
        cards = p.locator(", ".join(SEL["li_card"]))
        for _ in range(4):
            if cards.count():
                cards.last.scroll_into_view_if_needed()
            _human_pause(0.8, 1.5)
        for i in range(min(cards.count(), limit)):
            c = cards.nth(i)
            job_id = c.get_attribute("data-occludable-job-id") or c.get_attribute("data-job-id")
            title_el = _first(c, "li_title")
            if not job_id or not title_el:
                continue
            jobs.append(Job(
                source="linkedin", job_id=job_id,
                title=title_el.inner_text().strip().split("\n")[0],
                company=_text(c, "li_company"), location=_text(c, "li_location"),
                url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            ))
        return jobs
