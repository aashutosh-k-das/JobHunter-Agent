"""CLI:  python -m jobhunter login | run [--dry-run] [--criteria criteria.yaml] | graph"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import uuid
from collections import Counter

from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel

from .config import load_criteria
from .tools.browser import Browser

console = Console()


def _edit_text(text: str) -> str:
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write(text)
    subprocess.call([os.environ.get("EDITOR", "nano"), f.name])
    with open(f.name) as f2:
        return f2.read().strip()


def _ask(job: dict) -> dict:
    console.print(Panel(
        f"[bold]{job['title']}[/] @ {job['company']} — {job.get('location', '')}\n"
        f"{job['url']}\nScore: [bold]{job['score']}[/]  {job.get('reason', '')}\n\n"
        f"[dim]{job.get('cover_letter', '')}[/]",
        title=f"Review ({job['source']})",
    ))
    while True:
        a = console.input("[a]pprove  [e]dit letter  [s]kip  [q]uit > ").strip().lower()
        if a == "a":
            return {"action": "approve"}
        if a == "s":
            return {"action": "skip"}
        if a == "e":
            job["cover_letter"] = _edit_text(job.get("cover_letter", ""))
            return {"action": "approve", "cover_letter": job["cover_letter"]}
        if a == "q":
            raise KeyboardInterrupt


def _preflight() -> None:
    if not os.getenv("OPENAI_API_KEY", "").startswith("sk-"):
        raise SystemExit("OPENAI_API_KEY is missing. Add it to .env (see .env.example).")


def dry_run(criteria_path: str) -> None:
    """Search + filter + score only. Nothing is applied to and nothing is logged."""
    from rich.table import Table

    from .graph import build_graph
    from .tools.sheets import AppLog

    class NoLog(AppLog):
        def append(self, job) -> None:
            pass

    graph = build_graph(load_criteria(criteria_path), NoLog())
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    try:
        graph.invoke({}, cfg, interrupt_after=["score"])
    finally:
        Browser.close()
    s = graph.get_state(cfg).values
    t = Table("Score", "Title", "Company", "Location", "Source", "Why", title="Would review")
    for j in s.get("jobs", []):
        t.add_row(str(j["score"]), j["title"], j["company"], j.get("location", ""),
                  j["source"], j.get("reason", ""))
    console.print(t)
    rejected = Counter(j["status"] for j in s.get("processed", []))
    console.print(f"Rejected: {dict(rejected)}")


def run(criteria_path: str) -> None:
    from .graph import build_graph
    from .tools.sheets import AppLog

    c = load_criteria(criteria_path)
    graph = build_graph(c, AppLog())
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 500}

    inp: object = {}
    try:
        while True:
            result = graph.invoke(inp, cfg)
            pending = result.get("__interrupt__")
            if not pending:
                break
            inp = Command(resume=_ask(pending[0].value["job"]))
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user.[/]")
    finally:
        Browser.close()

    processed = graph.get_state(cfg).values.get("processed", [])
    console.print(Panel(
        "\n".join(f"{k}: {v}" for k, v in Counter(j["status"] for j in processed).items())
        or "Nothing processed.", title="Run summary"))


def main() -> None:
    ap = argparse.ArgumentParser(prog="jobhunter")
    ap.add_argument("command", choices=["login", "run", "graph"])
    ap.add_argument("--criteria", default="criteria.yaml")
    ap.add_argument("--dry-run", action="store_true", help="search + score only")
    args = ap.parse_args()

    if args.command == "login":
        from playwright.sync_api import Error as PlaywrightError
        try:
            Browser.get().login_interactive()
        except PlaywrightError as e:
            reason = "timed out" if "Timeout" in type(e).__name__ else "browser window was closed"
            raise SystemExit(f"Login not completed ({reason}). Run `python -m jobhunter login` again.")
        finally:
            Browser.close()
    elif args.command == "graph":
        from .config import Criteria
        from .graph import build_graph
        from .tools.sheets import AppLog
        dummy = Criteria(resume_path="-", searches=[])
        print(build_graph(dummy, AppLog()).get_graph().draw_mermaid())
    else:
        _preflight()
        (dry_run if args.dry_run else run)(args.criteria)


if __name__ == "__main__":
    main()
