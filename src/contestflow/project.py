"""Bootstrap workspaces and give teams artifact-based collaboration guidance."""

from __future__ import annotations

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
    write_json(root / "configs/preflight.json", {"schema_version": 1, "profile": "core"})
    write_json(root / "configs/resources.json", {"schema_version": 1, "selected": []})
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
        "# 团队决策与阶段复盘\n\n"
        "按阶段记录实际发生的工作与讨论，不为普通命令单独填表。\n\n"
        "## 阶段记录格式\n\n"
        "- 本阶段目标与已授权范围：\n"
        "- AI 提供的候选方案、产物与证据位置：\n"
        "- 自动检查的结果与局限：\n"
        "- 团队实际意见、决定及依据（未讨论时写待讨论）：\n"
        "- 尚未解决的问题、下一步安排与预算：\n\n"
        "AI 建议与团队意见分开记录；没有实际反馈时，不填写已确认或已审定。\n",
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
        "materials/\ndata/\nruns/\nreviews/\ndeliverables/\n.venv/\n.env*\n*.local.json\n.contestflow/\n",
    )
    journal(root, "init", {"title": title})
    plan(root)
    return {"workspace": str(root), "next": str(root / "docs/AI_TASK.md")}


def doctor(root=None):
    from .preflight import inventory

    return inventory(root)


def _artifact_stage(root: Path):
    config(root)
    if local(root, "deliverables/FROZEN.json").exists():
        return {
            "stage": "frozen",
            "action": "协助只读核对冻结文件及已有回执，向团队报告差异。",
            "automatic": False,
        }
    if not local(root, "materials/manifest.json").exists():
        return {
            "stage": "intake",
            "action": "整理团队提供的题面与附件，建立原件、图表和数据索引。",
            "automatic": True,
        }
    requirements = read_json(local(root, "plans/requirements.json"))
    items = requirements.get("items", [])
    if not items or any(
        not all(item.get(k) for k in ("id", "question", "source", "acceptance")) for item in items
    ):
        return {
            "stage": "analysis",
            "action": "整理逐小问题意、约束、数据疑点与验收草案，提供候选路线和需要团队判断的问题。",
            "automatic": True,
        }
    experiments = read_json(local(root, "configs/experiments.json")).get("experiments", [])
    if not experiments:
        return {
            "stage": "baseline",
            "action": "按团队选定的目标与预算实现最小基线、独立验证及实验协议，交付可运行方案供审阅。",
            "automatic": True,
        }
    from .runner import current_runs

    records = current_runs(root)
    if any(r["status"] != "success" for r in records):
        return {
            "stage": "experiments",
            "action": "按已确定的实验安排运行、修复和比较，保留失败与负例，说明结果和待解释问题。",
            "automatic": True,
        }
    from .evidence import evidence_current

    if not evidence_current(root):
        return {
            "stage": "evidence",
            "action": "重建比较底表，整理单位、分母、覆盖范围和对照证据，供团队判断结论是否成立。",
            "automatic": True,
        }
    from .reporting import paper_current

    if not paper_current(root):
        return {
            "stage": "paper",
            "action": "按团队确定的论证组织论文草稿与图表，列出证据和未解决问题，构建候选文件供逐章审阅。",
            "automatic": True,
        }
    return {
        "stage": "delivery",
        "action": "协助核对候选论文与程序包、复现记录及待办，将实际文件交由团队审定。",
        "automatic": False,
    }


TEAM_FOCUS = {
    "intake": "确认材料完整性、使用范围与本阶段要回答的问题。",
    "analysis": "核对题意与当届规则，决定主攻问题、验收要求和可行性预跑范围。",
    "baseline": "决定建模假设、方案取舍、指标口径与实验预算；可安排小规模探索再作选择。",
    "experiments": "审阅方案合法性与实验设计，决定保留哪些结果、补哪些验证以及何时停止。",
    "evidence": "判断结果能支持哪些结论，核对异常、局限与独立验证，决定是否补实验。",
    "paper": "理解并审定模型、代码、结论、引用与图表，反馈需要修改的内容。",
    "delivery": "核对全文、实际文件、匿名性、AI 披露和比赛规则，决定冻结与提交安排。",
    "frozen": "确认使用哪个冻结版本并核对实际平台回执；字节冻结不表示人工审定或提交成功。",
}


def next_task(root: Path):
    """Suggest work from artifacts without inferring approval or executing a next step."""
    step = _artifact_stage(root)
    return {
        **step,
        "collaboration_mode": "team_led",
        "guidance_only": True,
        "team_focus": TEAM_FOCUS[step["stage"]],
        "human_review": "not_asserted",
    }


def plan(root: Path):
    require_mutable(root)
    step = next_task(root)
    body = (
        "# 当前阶段协作任务\n\n"
        f"建议处理阶段：{step['stage']}（依据现有文件，不代表团队已审定）\n\n"
        f"## 团队判断\n\n{step['team_focus']}\n\n"
        f"## AI 辅助工作\n\n{step['action']}\n\n"
        "先读本工作区 AGENTS.md、contest.json、docs/DECISIONS.md，"
        "按团队已确定的目标和授权范围推进，常规工作不逐条询问。\n\n"
        "阶段完成后交付可审阅的产物、证据、局限和待决策事项，"
        "记录团队实际意见及下一步安排。需要新的关键判断时，"
        "先准备有依据的选项，不把 AI 建议当作团队已经接受。\n\n"
        "阶段建议只根据现有产物给出，不自动执行后续任务。"
        "团队审阅以实际反馈为准，本文件不生成批准记录。\n\n"
        "CLI 不调用模型。候选论文、自动检查通过与字节冻结都不是可直接提交的证明；"
        "最终内容和实际提交由团队决定。\n"
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
        "human_review": "not_asserted",
        "collaboration_mode": "team_led",
        "note": "阶段来自文件状态，仅供安排工作；自动检查、候选包和冻结均不代表团队已审定或可直接提交。",
    }


def workspace_identity(root: Path):
    return snapshot(root, ["contest.json", "configs", "src", "evidence", "paper"])
