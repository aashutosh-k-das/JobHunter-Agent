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
