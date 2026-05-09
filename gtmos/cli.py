"""`gtmos` command-line entrypoint.

Subcommands:

    gtmos verify              # static doctrine + agent/eval pairing
    gtmos eval [agent]        # run all evals (or one), structural by default
    gtmos run-agent <name>    # execute one agent against ad-hoc inputs
    gtmos clients             # list active clients
    gtmos tasks               # task store CRUD + overdue dispatch (planning)
    gtmos slack-app           # run the Slack handler (HTTP server)
    gtmos routine <name>      # run a single named routine

All subcommands respect ``--repo`` and ``--json`` flags.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from gtmos import __version__
from gtmos.config import ConfigError, Settings
from gtmos.security import safe_join, validate_slug

logger = logging.getLogger("gtmos.cli")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _bootstrap_logging(args.verbose)

    try:
        return args.func(args)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.exception("unhandled error")
        print(f"error: {e}", file=sys.stderr)
        return 1


# ---- parser ----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gtmos", description=f"GTM Agency OS v{__version__}")
    p.add_argument("--repo", help="repo root (default: env GTMOS_REPO_ROOT or auto-detect)")
    p.add_argument("--verbose", "-v", action="count", default=0)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s_verify = sub.add_parser("verify", help="static doctrine + pairing checks")
    s_verify.set_defaults(func=cmd_verify)

    s_eval = sub.add_parser("eval", help="run agent eval(s)")
    s_eval.add_argument("agent", nargs="?", help="single agent name; default: all")
    s_eval.add_argument(
        "--mode",
        choices=("auto", "structural", "judge"),
        default="auto",
        help="auto = judge if ANTHROPIC_API_KEY set else structural",
    )
    s_eval.set_defaults(func=cmd_eval)

    s_run = sub.add_parser("run-agent", help="execute one agent")
    s_run.add_argument("name")
    s_run.add_argument(
        "--input",
        default="{}",
        help="JSON object with the agent's input fields",
    )
    s_run.add_argument("--client", help="optional client slug (per-client run)")
    s_run.add_argument("--task", help="task label embedded in run filename")
    s_run.set_defaults(func=cmd_run_agent)

    s_clients = sub.add_parser("clients", help="list active clients")
    s_clients.add_argument(
        "--include-template",
        action="store_true",
        help="include _example template clients",
    )
    s_clients.set_defaults(func=cmd_clients)

    s_tasks = sub.add_parser("tasks", help="task store ops")
    s_tasks_sub = s_tasks.add_subparsers(dest="task_cmd", required=True)

    s_t_add = s_tasks_sub.add_parser("add")
    s_t_add.add_argument("--title", required=True)
    s_t_add.add_argument("--owner", required=True)
    s_t_add.add_argument("--client", required=True)
    s_t_add.add_argument(
        "--due", required=True, help="ISO-8601 datetime, must include timezone"
    )
    s_t_add.set_defaults(func=cmd_tasks_add)

    s_t_list = s_tasks_sub.add_parser("list")
    s_t_list.add_argument("--owner", required=True)
    s_t_list.set_defaults(func=cmd_tasks_list)

    s_t_overdue = s_tasks_sub.add_parser("overdue")
    s_t_overdue.set_defaults(func=cmd_tasks_overdue)

    s_t_done = s_tasks_sub.add_parser("done")
    s_t_done.add_argument("--id", type=int, required=True)
    s_t_done.set_defaults(func=cmd_tasks_done)

    s_routine = sub.add_parser("routine", help="run a named routine")
    s_routine.add_argument("name")
    s_routine.set_defaults(func=cmd_routine)

    s_slack = sub.add_parser("slack-app", help="serve the Slack handler over HTTP")
    # Default to loopback. Production deploys must opt into binding all
    # interfaces explicitly via `--host 0.0.0.0`; the runtime should sit behind
    # a TLS-terminating proxy (Pattern 16). See SECURITY.md.
    s_slack.add_argument("--host", default="127.0.0.1")
    s_slack.add_argument("--port", type=int, default=3000)
    s_slack.set_defaults(func=cmd_slack_app)

    s_pipe = sub.add_parser("pipeline", help="run an end-to-end pipeline")
    pipe_sub = s_pipe.add_subparsers(dest="pipeline_cmd", required=True)

    s_review = pipe_sub.add_parser("weekly-review", help="HubSpot pull → agent → Slack DM")
    s_review.add_argument("--client", required=True)
    s_review.set_defaults(func=cmd_pipeline_weekly_review)

    s_tri = pipe_sub.add_parser("inbound-triage", help="classify a reply + take action")
    s_tri.add_argument("--client", required=True)
    s_tri.add_argument("--from-email", required=True)
    s_tri.add_argument("--from-name", default="")
    s_tri.add_argument("--subject", default="")
    s_tri.add_argument("--body", help="reply body text; reads stdin if omitted")
    s_tri.add_argument("--thread-id", default="")
    s_tri.add_argument(
        "--gate", type=float, default=0.7, help="confidence gate; below → escalate"
    )
    s_tri.set_defaults(func=cmd_pipeline_inbound_triage)

    return p


def _bootstrap_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
    )


# ---- commands --------------------------------------------------------------


def _settings(args: argparse.Namespace, *, require: tuple[str, ...] = ()) -> Settings:
    if args.repo:
        os.environ["GTMOS_REPO_ROOT"] = str(Path(args.repo).resolve())
    return Settings.load(require=require)


def cmd_verify(args: argparse.Namespace) -> int:
    # Verify is a pure static check — don't gate on an API key.
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        os.environ["ANTHROPIC_API_KEY"] = "offline-mode-placeholder"
    settings = _settings(args)
    root = settings.repo_root

    issues: list[str] = []

    claude_md = root / "CLAUDE.md"
    if not claude_md.is_file() or claude_md.read_text().count("\n") < 50:
        issues.append("CLAUDE.md missing or too short")

    agents_dir = safe_join(root, "agents")
    evals_dir = safe_join(root, "evals")
    for a in sorted(agents_dir.glob("*.md")):
        name = a.stem
        if not (evals_dir / f"{name}.yaml").is_file():
            issues.append(f"agents/{name}.md has no evals/{name}.yaml")

    if issues:
        for i in issues:
            print(f"✗ {i}")
        return 1
    print("✓ verify: PASS")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from gtmos.judge import EvalRunner, evaluate_offline

    # Structural mode + GTMOS_OFFLINE=1 work without the LLM capability.
    offline = (
        args.mode == "structural"
        or os.environ.get("GTMOS_OFFLINE", "").strip() == "1"
        or not os.environ.get("ANTHROPIC_API_KEY", "").strip()
    )

    if offline and not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        os.environ["ANTHROPIC_API_KEY"] = "offline-mode-placeholder"

    settings = _settings(args)

    targets: list[str]
    if args.agent:
        targets = [args.agent]
    else:
        targets = [p.stem for p in sorted((settings.repo_root / "agents").glob("*.md"))]

    failures = 0
    for name in targets:
        if offline or args.mode == "structural":
            result = evaluate_offline(settings.repo_root, name)
        else:
            runner = EvalRunner.from_settings(settings)
            result = runner.run(name, mode=args.mode)
        verdict = "✓" if result.passed else "✗"
        print(
            f"{verdict} {name}: overall {result.overall:.2f}/10 "
            f"(threshold {result.threshold}); fixtures={len(result.fixture_scores)}"
        )
        if result.error:
            print(f"   error: {result.error}")
            failures += 1
        elif not result.passed:
            failures += 1
    return 0 if failures == 0 else 1


def cmd_run_agent(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.agents import AgentExecutor

    try:
        inputs: dict[str, Any] = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(f"--input must be valid JSON object: {e}", file=sys.stderr)
        return 2
    if not isinstance(inputs, dict):
        print("--input must decode to a JSON object", file=sys.stderr)
        return 2

    if args.client:
        validate_slug(args.client, allow_underscore_prefix=True)

    executor = AgentExecutor.from_settings(settings)
    run = executor.run(
        args.name,
        inputs,
        client_slug=args.client,
        task=args.task,
    )
    print(f"run artifact: {run.artifact_path.relative_to(settings.repo_root)}")
    if run.error:
        print(f"error: {run.error}", file=sys.stderr)
        return 1
    return 0


def cmd_clients(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.clients import list_clients

    for slug in list_clients(settings.repo_root, include_template=args.include_template):
        print(slug)
    return 0


def cmd_tasks_add(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.tasks import TaskStore

    due = dt.datetime.fromisoformat(args.due)
    if due.tzinfo is None:
        print("--due must include a timezone (e.g., 2026-05-12T17:00:00-07:00)",
              file=sys.stderr)
        return 2

    store = TaskStore(db_path=settings.tasks_db_path)
    t = store.add(
        title=args.title,
        owner_slack_id=args.owner,
        client_slug=args.client,
        due_at=due,
    )
    print(f"added task #{t.id}")
    return 0


def cmd_tasks_list(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.tasks import TaskStore

    store = TaskStore(db_path=settings.tasks_db_path)
    for t in store.list_by_owner(args.owner):
        print(f"#{t.id}  due={t.due_at.isoformat(timespec='minutes')}  "
              f"[{t.status}]  {t.title}")
    return 0


def cmd_tasks_overdue(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.tasks import TaskStore, dispatch_overdue_dms

    store = TaskStore(db_path=settings.tasks_db_path)
    plan = dispatch_overdue_dms(store)
    if not plan:
        print("✓ no overdue tasks (or all throttled)")
        return 0
    for dm in plan:
        print(f"DM {dm.owner_slack_id}: \"{dm.title}\" — {dm.days_late}d late "
              f"(task #{dm.task_id})")
    return 0


def cmd_tasks_done(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.tasks import TaskStore

    store = TaskStore(db_path=settings.tasks_db_path)
    t = store.update_status(args.id, "done")
    print(f"task #{t.id} marked done")
    return 0


def cmd_routine(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from gtmos.routines import run_routine

    return run_routine(settings, args.name)


def cmd_slack_app(args: argparse.Namespace) -> int:
    settings = _settings(args, require=("slack",))
    from gtmos.slack_app import build_app

    app = build_app(settings)
    print(f"gtmos slack-app listening on http://{args.host}:{args.port}/slack/events")
    app.start(port=args.port, host=args.host)  # type: ignore[call-arg]
    return 0


def cmd_pipeline_weekly_review(args: argparse.Namespace) -> int:
    settings = _settings(args, require=("hubspot", "slack"))
    from gtmos.pipelines import run_weekly_review

    validate_slug(args.client, allow_underscore_prefix=True)
    result = run_weekly_review(settings, client_slug=args.client)
    if result.skipped:
        print(f"⏭  weekly-review skipped: {result.skip_reason}")
        return 0
    print(f"weekly-review for {result.client_slug}:")
    print(f"  metrics:  {json.dumps(result.metrics, default=str)}")
    print(f"  artifact: {result.artifact_path}")
    if result.slack_ts:
        print(f"  slack_ts: {result.slack_ts}")
    if result.errors:
        for e in result.errors:
            print(f"  ⚠ {e}", file=sys.stderr)
        return 1 if not result.succeeded else 0
    return 0


def cmd_pipeline_inbound_triage(args: argparse.Namespace) -> int:
    settings = _settings(args, require=("hubspot", "slack"))
    from gtmos.pipelines import InboundReply, run_inbound_triage

    validate_slug(args.client, allow_underscore_prefix=True)

    body = args.body
    if body is None:
        body = sys.stdin.read()
    if not body or not body.strip():
        print("--body is empty (and stdin is empty)", file=sys.stderr)
        return 2

    reply = InboundReply(
        client_slug=args.client,
        sender_email=args.from_email,
        sender_name=args.from_name,
        subject=args.subject,
        body=body,
        thread_id=args.thread_id,
    )
    result = run_inbound_triage(settings, reply, confidence_gate=args.gate)
    print(
        f"triage: tier={result.tier} conf={result.confidence:.2f} "
        f"contact_id={result.contact_id or 'unresolved'} "
        f"escalated={result.escalated}"
    )
    if result.evidence:
        print(f"  evidence: {result.evidence[:200]!r}")
    if result.artifact_path:
        print(f"  artifact: {result.artifact_path}")
    if result.hubspot_engagement_ids:
        print(f"  hubspot:  {','.join(result.hubspot_engagement_ids)}")
    if result.slack_ts:
        print(f"  slack:    ts={result.slack_ts}")
    if result.errors:
        for e in result.errors:
            print(f"  ⚠ {e}", file=sys.stderr)
        return 1 if not result.succeeded else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
