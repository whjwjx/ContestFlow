"""Local tools for human-led competition work with stage-scoped AI assistance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import FlowError, read_json, workspace_lock


def parser():
    result = argparse.ArgumentParser(
        prog="contestflow",
        description="Human-led modeling workflows with AI-assisted stages.",
        epilog="Technical checks do not certify team review or submission readiness.",
    )
    result.add_argument("--version", action="version", version=__version__)
    subs = result.add_subparsers(dest="command", required=True)
    doctor = subs.add_parser("doctor", help="Read-only inventory using the actual tool resolver")
    doctor.add_argument("workspace", type=Path, nargs="?")
    tool = subs.add_parser("tools", help="Discover tools or remember local executable paths")
    tool.add_argument("workspace", type=Path, nargs="?")
    changes = tool.add_mutually_exclusive_group()
    changes.add_argument("--set", nargs=2, metavar=("TOOL", "EXECUTABLE"))
    changes.add_argument("--search-dir", type=Path)
    changes.add_argument("--unset", metavar="TOOL")
    resource = subs.add_parser(
        "resources", help="Browse reusable tools/styles or select them for a workspace"
    )
    resource.add_argument("workspace", type=Path, nargs="?")
    resource.add_argument("--select", nargs="*", metavar="RESOURCE_ID")
    check = subs.add_parser(
        "preflight", help="Inventory, fixed functional probes, or a synthetic rehearsal"
    )
    check.add_argument("workspace", type=Path, nargs="?")
    from .preflight import PROFILES

    check.add_argument("--profile", choices=tuple(PROFILES))
    check.add_argument(
        "--level", choices=("inventory", "functional", "rehearsal"), default="inventory"
    )
    check.add_argument(
        "--output", type=Path, help="New local report/artifact directory; never overwrites"
    )
    for command in (
        "init",
        "start",
        "intake",
        "plan",
        "next",
        "status",
        "repo",
        "run",
        "compare",
        "charts",
        "select",
        "paper",
        "package",
        "verify",
        "freeze",
        "demo",
    ):
        help_text = {
            "init": "Create a team workspace",
            "intake": "Index materials and preserve source copies",
            "run": "Run configured experiments within the selected scope",
            "compare": "Build evidence tables from recorded results",
            "charts": "Generate chart choices for review",
            "select": "Import chart presentation choices",
            "paper": "Build a candidate manuscript for team review",
            "start": "Import materials for team-led problem analysis",
            "plan": "Write stage guidance for the team and AI",
            "next": "Suggest next work from artifact state",
            "status": "Show artifact state and unverified human-review status",
            "repo": "Inspect or initialize the exact competition Git repository",
            "package": "Build a candidate archive for team review",
            "verify": "Check file integrity and configured reproduction",
            "freeze": "Freeze candidate bytes",
            "demo": "Run a preset teaching example",
        }
        sub = subs.add_parser(
            command, help=help_text.get(command), description=help_text.get(command)
        )
        sub.add_argument("workspace", type=Path)
        if command in ("init", "start"):
            sub.add_argument("--title", default="New competition")
            sub.add_argument(
                "--git-mode",
                choices=("off", "local", "team"),
                help="Initialize/adopt this exact workspace as a local or team Git repository",
            )
        if command == "init":
            sub.add_argument("--example", choices=("assignment", "forecast"))
        if command in ("start", "intake"):
            sub.add_argument("--materials", type=Path, required=True)
        if command in ("run", "verify", "demo"):
            sub.add_argument(
                "--allow-exec",
                action="store_true",
                help="Permit configured code execution; does not approve a model or its results",
            )
        if command == "run":
            sub.add_argument("--workers", type=int)
            sub.add_argument("--force", action="store_true")
        if command == "select":
            sub.add_argument("selection", type=Path)
        if command in ("paper", "demo"):
            sub.add_argument("--format", choices=("html", "pdf"), default="html")
        if command == "verify":
            sub.add_argument("--smoke", action="store_true")
        if command == "freeze":
            sub.add_argument(
                "--confirm", action="store_true", help="Confirm byte freeze, not team review"
            )
        if command == "demo":
            sub.add_argument("--example", choices=("assignment", "forecast"), default="assignment")
        if command == "repo":
            changes = sub.add_mutually_exclusive_group()
            changes.add_argument("--init", choices=("local", "team"), dest="repo_init")
            changes.add_argument("--disable", action="store_true")
    return result


def dispatch(args):
    from . import (
        charts,
        evidence,
        examples,
        intake,
        project,
        release,
        reporting,
        runner,
        version_control,
    )

    if args.command in ("doctor", "tools", "resources", "preflight"):
        root = args.workspace.absolute() if args.workspace else None
        if root is not None:
            from .core import config

            config(root)
        if args.command == "doctor":
            return project.doctor(root)
        if args.command == "tools":
            from . import toolchain

            if args.set or args.search_dir or args.unset:
                kwargs = {
                    "tool": args.set[0] if args.set else None,
                    "path": args.set[1] if args.set else None,
                    "search_dir": str(args.search_dir) if args.search_dir else None,
                    "unset": args.unset,
                }
                if root is not None:
                    with workspace_lock(root):
                        return toolchain.configure(root, **kwargs)
                return toolchain.configure(**kwargs)
            return {
                name: toolchain.discover_tool(name, root)
                for name in ("pandoc", "xelatex", "git", "nvidia-smi")
            }
        if args.command == "resources":
            from . import resources

            if args.select is not None:
                if root is None:
                    raise FlowError("Selecting resources requires a workspace")
                with workspace_lock(root):
                    return resources.select_resources(root, args.select)
            return resources.catalog(root)
        from .preflight import preflight

        return preflight(root, args.profile, args.level, args.output)
    root = args.workspace.absolute()
    command = args.command
    if command == "init":
        result = project.init(root, args.title, args.git_mode or "off")
        if args.example:
            examples.seed_example(root, args.example)
            project.plan(root)
        return result
    if command == "start":
        if not (root / "contest.json").exists():
            project.init(root, args.title, args.git_mode or "off")
        with workspace_lock(root):
            if args.git_mode and version_control.policy(root)["mode"] != args.git_mode:
                if args.git_mode == "off":
                    version_control.disable(root)
                else:
                    version_control.enable(root, args.git_mode)
            imported = intake.intake(root, args.materials)
            step = project.plan(root)
        return {
            "workspace": str(root),
            "imported": len(imported["files"]),
            "next": step,
            "agent_entry": str(root / "docs/AI_TASK.md"),
            "repository": version_control.inspect(root),
        }
    if command == "repo":
        if args.repo_init or args.disable:
            with workspace_lock(root):
                return (
                    version_control.enable(root, args.repo_init)
                    if args.repo_init
                    else version_control.disable(root)
                )
        return version_control.inspect(root)
    if command in ("next", "status"):
        return project.next_task(root) if command == "next" else project.status(root)
    if command == "demo":
        if not args.allow_exec:
            raise FlowError("Demo runs bundled example code; pass --allow-exec")
        project.init(root, "Synthetic example")
        with workspace_lock(root):
            examples.seed_example(root, args.example)
            records = runner.run(root, allow_exec=True)
            if any(item["status"] != "success" for item in records):
                raise FlowError("Demo experiment failed; inspect runs before continuing")
            evidence.compare(root)
            charts.charts(root)
            reporting.build_paper(root, args.format)
            if args.format == "html":
                from .core import config, write_json

                cfg = config(root)
                cfg["package"]["require_pdf"] = False
                write_json(root / "contest.json", cfg)
                reporting.build_paper(root, "html")
            release.package(root)
            checked = release.verify(root, smoke=True, allow_exec=True)
            project.plan(root)
        return {
            "workspace": str(root),
            "review": str(root / "reviews/index.html"),
            "paper": str(root / f"paper/build/paper.{args.format}"),
            "verification": checked,
            "purpose": "toolchain_demo",
            "human_review": "not_asserted",
            "note": "预设教学例只演示工具链。实际比赛仍需团队理解题意、选择模型、审定结果与论文。",
        }
    with workspace_lock(root):
        if command == "intake":
            return intake.intake(root, args.materials)
        if command == "plan":
            return project.plan(root)
        if command == "run":
            return runner.run(root, args.allow_exec, args.workers, args.force)
        if command == "compare":
            return evidence.compare(root)
        if command == "charts":
            return charts.charts(root)
        if command == "select":
            return charts.apply_selection(root, read_json(args.selection))
        if command == "paper":
            return reporting.build_paper(root, args.format)
        if command == "package":
            return release.package(root)
        if command == "verify":
            return release.verify(root, args.smoke, args.allow_exec)
        if command == "freeze":
            return release.freeze(root, args.confirm)
    raise FlowError("Unknown command")


def main(argv=None):
    # JSON is UTF-8 even when Windows pipes would otherwise use a legacy code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.command == "run" and any(r["status"] != "success" for r in result):
            return 1
        if args.command == "preflight" and result["result"] == "failed":
            return 1
        return 0
    except (FlowError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
