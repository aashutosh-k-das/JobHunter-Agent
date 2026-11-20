from __future__ import annotations

from functools import cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from .config import ENV, Criteria
from .state import Job


@cache
def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=ENV.openai_model, temperature=0.2)


class MatchScore(BaseModel):
    score: int = Field(ge=0, le=100, description="How well the candidate fits this job")
    reason: str = Field(description="One or two sentences: key matches and gaps")
    seniority_ok: bool = Field(description="Is the required experience within reach?")


def score_job(job: Job, resume: str, criteria: Criteria) -> MatchScore:
    return _llm().with_structured_output(MatchScore).invoke([
        SystemMessage(content=(
            "You are a strict technical recruiter. Score candidate-job fit 0-100. "
            "Weigh required skills and experience most heavily. Penalise roles that "
            f"need far more than {criteria.filters.experience_years} years of experience."
        )),
        HumanMessage(content=(
            f"RESUME:\n{resume[:8000]}\n\n"
            f"JOB: {job['title']} at {job['company']} ({job.get('location', '')})\n"
            f"{job.get('description', '')[:6000]}"
        )),
    ])


def draft_cover_letter(job: Job, resume: str, criteria: Criteria) -> str:
    msg = _llm().invoke([
        SystemMessage(content=(
            "Write a concise cover letter (150-220 words, 3 short paragraphs). "
            "Be specific: connect 2-3 concrete achievements from the resume to the job's "
            "requirements. No clichés ('I am writing to express...'), no invented facts, "
            "no placeholders. Plain text, sign off with the candidate's name."
        )),
        HumanMessage(content=(
            f"Candidate name: {criteria.profile.full_name}\n\nRESUME:\n{resume[:8000]}\n\n"
            f"JOB: {job['title']} at {job['company']}\n{job.get('description', '')[:6000]}"
        )),
    ])
    return msg.content.strip()
