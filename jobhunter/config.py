from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Search(BaseModel):
    keywords: str
    location: str = ""


class Filters(BaseModel):
    experience_years: float = 0
    must_have_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    remote_only: bool = False


class ApplySettings(BaseModel):
    submit: bool = False
    require_approval: bool = True
    max_applications_per_run: int = 10


class Profile(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    notice_period_days: int = 30
    current_ctc_lpa: float = 0
    expected_ctc_lpa: float = 0
    linkedin_url: str = ""
    github_url: str = ""
    extra_answers: dict[str, str] = Field(default_factory=dict)


class Criteria(BaseModel):
    resume_path: str
    searches: list[Search]
    sources: list[str] = Field(default_factory=lambda: ["linkedin", "naukri"])
    max_jobs_per_search: int = 15
    min_match_score: int = 70
    filters: Filters = Field(default_factory=Filters)
    apply: ApplySettings = Field(default_factory=ApplySettings)
    profile: Profile = Field(default_factory=Profile)


class Env(BaseModel):
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    sa_file: str | None = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    sheet_id: str | None = os.getenv("GOOGLE_SHEET_ID")
    profile_dir: str = os.getenv("BROWSER_PROFILE_DIR", ".browser_profile")
    headless: bool = os.getenv("HEADLESS", "false").lower() == "true"


def load_criteria(path: str | Path = "criteria.yaml") -> Criteria:
    with open(path) as f:
        return Criteria.model_validate(yaml.safe_load(f))


ENV = Env()
