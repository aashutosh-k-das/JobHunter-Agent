"""LangGraph workflow.

    load_resume -> search -> prefilter -> score -> next_job --(queue empty / cap hit)--> END
                                                     |
                                                     v
                                                draft_letter -> review (human interrupt)
                                                     ^               |  approve / skip
                                                     |               v
                                                     +---- log <--- apply
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from rich.console import Console

from .config import Criteria
from .llm import draft_cover_letter, score_job
from .state import AgentState, Job
from .tools.apply import APPLIERS
from .tools.browser import Browser
from .tools.resume import load_resume
from .tools.sheets import AppLog

console = Console()


def build_graph(c: Criteria, log: AppLog):

    def _record(job: Job, status: str, note: str = "") -> Job:
        job = {**job, "status": status, "note": note or job.get("note", "")}
        log.append(job)
        return job

    # ------------------------------------------------------------ nodes
    def n_load_resume(state: AgentState) -> dict:
        text = load_resume(c.resume_path)
        console.print(f"[green]Resume loaded[/] ({len(text)} chars). Logging to {log.backend}")
        return {"resume_text": text, "applied_count": 0}

    def n_search(state: AgentState) -> dict:
        b = Browser.get()
        found: dict[str, Job] = {}
        for s in c.searches:
            for src in c.sources:
                fn = b.search_linkedin if src == "linkedin" else b.search_naukri
                try:
                    jobs = fn(s.keywords, s.location, c.max_jobs_per_search)
                except Exception as e:  # one broken source shouldn't kill the run
                    console.print(f"[red]{src} search failed for '{s.keywords}': {e}")
                    continue
                console.print(f"[cyan]{src}[/] '{s.keywords}' @ {s.location or 'any'}: {len(jobs)} jobs")
                for j in jobs:
                    found.setdefault(f"{j['source']}:{j['job_id']}", j)
        return {"jobs": list(found.values())}

    def n_prefilter(state: AgentState) -> dict:
        """Cheap deterministic filters before spending LLM tokens."""
        seen = log.seen_keys()
        f = c.filters
        keep, dropped = [], []
        for j in state["jobs"]:
            if f"{j['source']}:{j['job_id']}" in seen:
                continue  # already handled in a previous run
            hay = f"{j['title']} {j['company']} {j['location']}".lower()
            why = None
            if any(k.lower() in j["title"].lower() for k in f.exclude_keywords):
                why = "excluded keyword in title"
            elif any(x.lower() == j["company"].lower() for x in f.exclude_companies):
                why = "excluded company"
            elif f.remote_only and "remote" not in hay:
                why = "not remote"
            if why:
                dropped.append(_record(j, "filtered_out", why))
            else:
                keep.append(j)
        console.print(f"Prefilter: {len(keep)} new candidates, {len(dropped)} filtered out")
        return {"jobs": keep, "processed": dropped}

    def n_score(state: AgentState) -> dict:
        b = Browser.get()
        f = c.filters
        queue, low = [], []
        for j in state["jobs"]:
            try:
                j = {**j, "description": b.fetch_description(j)}
            except Exception as e:
                low.append(_record(j, "error", f"description fetch failed: {e}"))
                continue
            desc = j["description"].lower()
            if f.must_have_keywords and not any(k.lower() in desc for k in f.must_have_keywords):
                low.append(_record(j, "filtered_out", "missing must-have keywords"))
                continue
            m = score_job(j, state["resume_text"], c)
            j = {**j, "score": m.score, "reason": m.reason}
            if m.score >= c.min_match_score and m.seniority_ok:
                queue.append(j)
            else:
                low.append(_record(j, "low_score"))
            console.print(f"  {m.score:>3}  {j['title']} @ {j['company']}")
        queue.sort(key=lambda j: j["score"], reverse=True)
        console.print(f"[green]{len(queue)} jobs above threshold {c.min_match_score}[/]")
        return {"jobs": queue, "processed": low}

    def n_next_job(state: AgentState) -> dict:
        jobs = list(state.get("jobs", []))
        if not jobs or state.get("applied_count", 0) >= c.apply.max_applications_per_run:
            return {"current": None}
        return {"current": jobs.pop(0), "jobs": jobs}

    def n_draft_letter(state: AgentState) -> dict:
        j = state["current"]
        return {"current": {**j, "cover_letter": draft_cover_letter(j, state["resume_text"], c)}}

    def n_review(state: AgentState) -> dict:
        j = state["current"]
        if not c.apply.require_approval:
            return {}
        decision = interrupt({"job": j})  # resumed by the CLI with the human's choice
        if decision.get("action") == "skip":
            return {"current": {**j, "status": "skipped_by_user"}}
        if decision.get("cover_letter"):
            j = {**j, "cover_letter": decision["cover_letter"]}
        return {"current": j}

    def n_apply(state: AgentState) -> dict:
        j = state["current"]
        try:
            status, note = APPLIERS[j["source"]](j, state["resume_text"], c)
        except Exception as e:
            status, note = "error", str(e)[:300]
        console.print(f"  -> [bold]{status}[/] {note}")
        bump = 1 if status in ("applied", "ready_to_submit") else 0
        return {"current": {**j, "status": status, "note": note},
                "applied_count": state.get("applied_count", 0) + bump}

    def n_log(state: AgentState) -> dict:
        j = state["current"]
        return {"processed": [_record(j, j["status"], j.get("note", ""))]}

    # ------------------------------------------------------------ edges
    g = StateGraph(AgentState)
    for name, fn in [("load_resume", n_load_resume), ("search", n_search),
                     ("prefilter", n_prefilter), ("score", n_score),
                     ("next_job", n_next_job), ("draft_letter", n_draft_letter),
                     ("review", n_review), ("apply", n_apply), ("log", n_log)]:
        g.add_node(name, fn)

    g.add_edge(START, "load_resume")
    g.add_edge("load_resume", "search")
    g.add_edge("search", "prefilter")
    g.add_edge("prefilter", "score")
    g.add_edge("score", "next_job")
    g.add_conditional_edges("next_job", lambda s: "draft_letter" if s.get("current") else END,
                            ["draft_letter", END])
    g.add_edge("draft_letter", "review")
    g.add_conditional_edges(
        "review",
        lambda s: "log" if s["current"].get("status") == "skipped_by_user" else "apply",
        ["apply", "log"],
    )
    g.add_edge("apply", "log")
    g.add_edge("log", "next_job")

    return g.compile(checkpointer=MemorySaver())
