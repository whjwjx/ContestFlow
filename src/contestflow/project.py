"""Bootstrap a workspace and prepare the next bounded assignment for an AI."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from importlib.resources import files
from pathlib import Path

from .core import (
    FlowError,
    config,
    journal,
    local,
    now,
    read_json,
    require_mutable,
    snapshot,
    write_json,
    write_text,
)

DIRECTORIES = (
    "materials",
    "data/raw",
    "data/processed",
    "src",
    "configs",
    "runs",
    "evidence",
    "paper/figures",
    "reviews",
    "deliverables",
    "docs",
    "plans",
    "tests",
)


def template(name):
    return files("contestflow").joinpath("templates", name).read_text(encoding="utf-8")


def init(root: Path, title="New competition"):
    if root.exists() and any(root.iterdir()):
        raise FlowError(f"Refusing to initialize a nonempty directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for name in DIRECTORIES:
        local(root, name).mkdir(parents=True, exist_ok=True)
    write_json(
        root / "contest.json",
        {
            "schema_version": 1,
            "title": title,
            "created_at": now(),
            "budget": {"workers": 2, "max_experiments": 20, "timeout_seconds": 120},
            "rules": {
                "source": None,
                "review_status": "unconfirmed",
                "timezone": "Asia/Shanghai",
                "deadlines": [],
                "ai_policy": "unconfirmed",
                "max_archive_mb": 50,
            },
            "paper": {"cjk_font": "", "main_font": "", "fontsize": "11pt"},
            "package": {
                "include": ["src", "configs", "evidence", "paper", "docs/REPRODUCE.md"],
                "require_pdf": True,
                "private_markers": [],
            },
        },
    )
    write_json(root / "configs/experiments.json", {"schema_version": 1, "experiments": []})
    write_json(root / "plans/requirements.json", {"schema_version": 1, "items": []})
    write_json(root / "evidence/metrics.json", {"schema_version": 1, "metrics": {}})
    write_text(root / "AGENTS.md", template("workspace-agents.md"))
    write_text(
        root / "paper/draft.md",
        "# " + title + "\n\nTODO: 请依据题面与已验证证据撰写，禁止填入虚构结果。\n",
    )
    write_text(root / "paper/references.bib", "% Add only verified references.\n")
    write_text(
        root / "docs/DECISIONS.md",
        "# 决策与阶段复盘\n\n记录目标、证据、局限、下一步；不要逐条记录普通命令。\n",
    )
    write_text(
        root / "docs/AI_USAGE.md",
        "# AI辅助记录\n\n记录实际工具、型号、参与范围、日期来源及核验情况。未知信息不得猜填。\n",
    )
    write_text(
        root / "docs/REPRODUCE.md",
        "# 复现说明\n\nTODO: 记录实际依赖、输入和运行命令；不得声称未执行的复现已通过。\n",
    )
    write_text(
        root / ".gitignore",
        "materials/\ndata/\nruns/\nreviews/\ndeliverables/\n.venv/\n.env*\n*.local.json\n",
    )
    journal(root, "init", {"title": title})
    plan(root)
    return {"workspace": str(root), "next": str(root / "docs/AI_TASK.md")}


def doctor():
    packages = {
        name: importlib.util.find_spec(name) is not None
        for name in ("numpy", "scipy", "matplotlib", "pypdf", "pypandoc")
    }
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
        "tools": {n: shutil.which(n) for n in ("pandoc", "xelatex", "git", "nvidia-smi")},
        "note": "Read-only. GPU and document dependencies are optional; nothing was installed.",
    }


def next_task(root: Path):
    config(root)
    if local(root, "deliverables/FROZEN.json").exists():
        return {
            "stage": "frozen",
            "action": "核对既有文件与平台回执；禁止覆盖冻结成品。",
            "automatic": False,
        }
    if not local(root, "materials/manifest.json").exists():
        return {
            "stage": "intake",
            "action": "导入题面与附件，检查提取的文本、图片与数据字典。",
            "automatic": True,
        }
    requirements = read_json(local(root, "plans/requirements.json"))
    items = requirements.get("items", [])
    if not items or any(
        not all(item.get(k) for k in ("id", "question", "source", "acceptance")) for item in items
    ):
        return {
            "stage": "analysis",
            "action": "阅读原始题面和全部小问，填写requirements.json；核查规则来源并拟定有预算的主备路线。",
            "automatic": True,
        }
    experiments = read_json(local(root, "configs/experiments.json")).get("experiments", [])
    if not experiments:
        return {
            "stage": "baseline",
            "action": "实现最小合法基线、独立合法性/评分检查；登记实验命令、输入依赖、指标定义和超时。",
            "automatic": True,
        }
    from .runner import current_runs

    records = current_runs(root)
    if any(r["status"] != "success" for r in records):
        return {
            "stage": "experiments",
            "action": "检查未运行、过期或失败的实验；修复并在预算内运行，保留错误和负例。",
            "automatic": True,
        }
    from .evidence import evidence_current

    if not evidence_current(root):
        return {
            "stage": "evidence",
            "action": "重建compare底表，核对单位、分母、覆盖和结论；不将探索结果冒充独立验证。",
            "automatic": True,
        }
    from .reporting import paper_current

    if not paper_current(root):
        return {
            "stage": "paper",
            "action": "据证据完成MD主稿、公式与引用，生成图表候选并核对实际论文宽度，再构建与审读PDF。",
            "automatic": True,
        }
    return {
        "stage": "delivery",
        "action": "核查规则、匿名、AI披露和实际程序包，记录真实人工审定；经用户确认再冻结，绝不自动上传。",
        "automatic": False,
    }


def plan(root: Path):
    require_mutable(root)
    step = next_task(root)
    body = (
        "# 当前AI任务\n\n" + f"阶段：`{step['stage']}`\n\n{step['action']}\n\n"
        "先读本工作区AGENTS.md、contest.json、docs/DECISIONS.md。每完成有意义的阶段，"
        "记录证据和下一步，再运行`contestflow next .`。能够继续时自主推进，不等待逐条指令。\n\n"
        "工具不会自行调用模型。此任务交由当前具有文件和终端能力的AI执行；"
        "没有AI在线时，CLI只运行明确配置的程序，不会凭空生成通用赛题解答。\n"
    )
    write_text(local(root, "docs/AI_TASK.md"), body)
    write_json(
        local(root, "plans/current.json"), {"schema_version": 1, "updated_at": now(), **step}
    )
    return step


def status(root: Path):
    settings = config(root)
    return {
        "title": settings["title"],
        "next": next_task(root),
        "rules": settings["rules"],
        "platform_submission": "not_observed",
        "note": "Automation never asserts human review or platform acceptance.",
    }


def workspace_identity(root: Path):
    return snapshot(root, ["contest.json", "configs", "src", "evidence", "paper"])
