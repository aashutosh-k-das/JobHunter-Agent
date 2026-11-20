from jobhunter.config import Criteria
from jobhunter.tools.apply import _profile_answer
from jobhunter.tools.resume import load_resume
from jobhunter.tools.sheets import AppLog

C = Criteria.model_validate({
    "resume_path": "-", "searches": [],
    "filters": {"experience_years": 2},
    "profile": {"phone": "9876543210", "notice_period_days": 15, "expected_ctc_lpa": 9,
                "extra_answers": {"willing to relocate": "Yes"}},
})


def test_profile_answers_match_common_form_labels():
    assert _profile_answer("Mobile phone number", C) == "9876543210"
    assert _profile_answer("Notice period (days)", C) == "15"
    assert _profile_answer("Expected CTC (LPA)", C) == "9.0"
    assert _profile_answer("How many years of experience do you have with Python?", C) == "2"
    assert _profile_answer("Are you willing to relocate?", C) == "Yes"


def test_unknown_label_falls_through_to_llm():
    assert _profile_answer("Describe your favourite algorithm", C) is None


def test_empty_profile_values_are_not_used():
    assert _profile_answer("LinkedIn profile URL", C) is None


def test_resume_loads_text(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("  # Jane\nPython  \n")
    assert load_resume(str(p)) == "# Jane\nPython"


def test_csv_log_roundtrip(tmp_path, monkeypatch):
    from jobhunter.config import ENV
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ENV, "sa_file", None)
    log = AppLog()
    log.append({"source": "naukri", "job_id": "42", "title": "Dev", "status": "applied",
                "cover_letter": "Line one,\nline two"})  # commas/newlines must survive
    assert AppLog().seen_keys() == {"naukri:42"}
