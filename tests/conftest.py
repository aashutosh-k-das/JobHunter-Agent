import pytest

import jobhunter.graph as G
from jobhunter.config import ENV
from jobhunter.llm import MatchScore


class FakeBrowser:
    """Stands in for Playwright: fixed search results, canned descriptions."""

    linkedin = [
        ("1", "ML Engineer", "Acme", "Remote"),
        ("2", "Senior Staff Engineer", "Acme", "Remote"),
        ("3", "Data Scientist", "Globex", "Bengaluru"),
    ]
    naukri = [("9", "Python Developer", "Initech", "Pune")]

    def search_linkedin(self, keywords, location, limit):
        return [dict(source="linkedin", job_id=i, title=t, company=c, location=l,
                     url=f"https://li/{i}") for i, t, c, l in self.linkedin][:limit]

    def search_naukri(self, keywords, location, limit):
        return [dict(source="naukri", job_id=i, title=t, company=c, location=l,
                     url=f"https://nk/{i}") for i, t, c, l in self.naukri][:limit]

    def fetch_description(self, job):
        return f"We need python and ml skills for {job['title']}."


SCORES = {"ML Engineer": 90, "Data Scientist": 50, "Python Developer": 80}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated run: temp dir (CSV log lands here), fake browser/LLM/appliers."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ENV, "sa_file", None)  # force CSV backend
    monkeypatch.setattr(G.Browser, "get", staticmethod(lambda: FakeBrowser()))
    monkeypatch.setattr(G, "score_job", lambda j, r, c: MatchScore(
        score=SCORES.get(j["title"], 0), reason="stub", seniority_ok=True))
    monkeypatch.setattr(G, "draft_cover_letter", lambda j, r, c: f"Letter for {j['company']}")
    applied: list[dict] = []

    def fake_apply(job, resume, c):
        applied.append(job)
        return ("ready_to_submit", "stub")

    monkeypatch.setattr(G, "APPLIERS", {"linkedin": fake_apply, "naukri": fake_apply})
    (tmp_path / "resume.txt").write_text("Python ML engineer, 1 year experience.")
    return applied
