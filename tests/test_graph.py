import uuid

from langgraph.types import Command

import jobhunter.graph as G
from jobhunter.config import Criteria
from jobhunter.tools.sheets import AppLog


def make_criteria(**over):
    base = dict(resume_path="resume.txt", searches=[{"keywords": "ml"}],
                min_match_score=70, filters={"exclude_keywords": ["senior"]})
    base.update(over)
    return Criteria.model_validate(base)


def run(criteria, decisions):
    """Drive the graph, answering each review interrupt from `decisions`."""
    graph = G.build_graph(criteria, AppLog())
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 200}
    answers, reviewed, inp = iter(decisions), [], {}
    while True:
        result = graph.invoke(inp, cfg)
        pending = result.get("__interrupt__")
        if not pending:
            break
        reviewed.append(pending[0].value["job"])
        inp = Command(resume=next(answers))
    return graph.get_state(cfg).values["processed"], reviewed


def statuses(processed):
    return {j["title"]: j["status"] for j in processed}


def test_full_pipeline_filters_scores_and_reviews_in_score_order(env):
    processed, reviewed = run(make_criteria(), [{"action": "approve"}, {"action": "skip"}])

    assert [j["title"] for j in reviewed] == ["ML Engineer", "Python Developer"]  # by score
    assert reviewed[0]["cover_letter"] == "Letter for Acme"
    assert statuses(processed) == {
        "Senior Staff Engineer": "filtered_out",
        "Data Scientist": "low_score",
        "ML Engineer": "ready_to_submit",
        "Python Developer": "skipped_by_user",
    }
    assert [j["title"] for j in env] == ["ML Engineer"]  # skipped job never applied


def test_edited_cover_letter_is_used_for_application(env):
    run(make_criteria(sources=["linkedin"]),
        [{"action": "approve", "cover_letter": "My own words"}])
    assert env[0]["cover_letter"] == "My own words"


def test_second_run_skips_jobs_already_logged(env):
    run(make_criteria(), [{"action": "approve"}, {"action": "approve"}])
    processed, reviewed = run(make_criteria(), [])
    assert processed == [] and reviewed == []


def test_application_cap_stops_the_loop(env):
    c = make_criteria(apply={"max_applications_per_run": 1})
    processed, reviewed = run(c, [{"action": "approve"}])
    assert len(reviewed) == 1 and len(env) == 1


def test_no_approval_mode_applies_without_interrupt(env):
    processed, reviewed = run(make_criteria(apply={"require_approval": False}), [])
    assert reviewed == []
    assert {j["title"] for j in env} == {"ML Engineer", "Python Developer"}


def test_must_have_keywords_filter_on_description(env):
    processed, _ = run(make_criteria(filters={"must_have_keywords": ["kubernetes"]}), [])
    assert set(statuses(processed).values()) == {"filtered_out"}


def test_failing_applier_is_logged_as_error(env, monkeypatch):
    def boom(job, resume, c):
        raise RuntimeError("selector not found")
    monkeypatch.setattr(G, "APPLIERS", {"linkedin": boom, "naukri": boom})
    processed, _ = run(make_criteria(sources=["linkedin"]), [{"action": "approve"}])
    ml = next(j for j in processed if j["title"] == "ML Engineer")
    assert ml["status"] == "error" and "selector not found" in ml["note"]
