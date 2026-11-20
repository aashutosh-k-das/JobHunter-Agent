from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

Status = Literal[
    "found", "filtered_out", "low_score", "skipped_by_user",
    "applied", "ready_to_submit", "needs_manual", "external", "error",
]


class Job(TypedDict, total=False):
    source: str            # "linkedin" | "naukri"
    job_id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    score: int
    reason: str
    cover_letter: str
    status: Status
    note: str


class AgentState(TypedDict, total=False):
    resume_text: str
    jobs: list[Job]                       # queue being worked on
    current: Job | None                   # job currently in the apply loop
    processed: Annotated[list[Job], operator.add]   # everything logged this run
    applied_count: int
