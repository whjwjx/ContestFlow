<div align="center">

<img src="docs/assets/contestflow-hero.svg" alt="ContestFlow：团队主导的数模竞赛工作流" width="100%">

<p><strong>把读题、建模、实验、论文与交付连接成可审查、可复现的证据链。</strong></p>

<p>
  <img src="https://img.shields.io/badge/release-0.2.0a1-7C3AED?style=flat-square" alt="Release 0.2.0a1">
  <img src="https://img.shields.io/badge/Python-3.11%2B-2563EB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/workflow-human--led-0F766E?style=flat-square" alt="Human-led workflow">
  <img src="https://img.shields.io/badge/license-MIT-334155?style=flat-square" alt="MIT License">
  <a href="https://github.com/whjwjx/ContestFlow/stargazers"><img src="https://img.shields.io/github/stars/whjwjx/ContestFlow?style=flat-square&color=F59E0B" alt="GitHub Stars"></a>
</p>

<p>
  <a href="#agent-如何工作">工作方式</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#主要命令">主要命令</a> ·
  <a href="#文档与参与">文档与参与</a>
</p>

</div>

ContestFlow 是一个**团队主导、面向 Agent 的数模竞赛工作流与本地工具包**。团队决定题意、模型、预算、结论和最终提交；Agent 在已授权范围内主动规划、实现、验证和复盘；CLI 保存材料来源、实验身份、证据与候选产物。

> [!IMPORTANT]
> “全流程”表示覆盖比赛各阶段，不表示把题面交给 AI 后即可直接提交。CLI 不调用 LLM，也不上传比赛平台。当前为 `0.2.0a1` Alpha 版本，效果以具体赛题、环境和实际核验为准。

## 核心能力

| 能力 | 作用 |
|---|---|
| Agent 工作闭环 | 生成阶段目标，要求 Agent 按“规划 → 执行 → 验证 → 复盘 → 继续”主动推进 |
| 材料与证据 | 保存原件哈希、实验输入、代码、参数、环境、指标和失败记录 |
| 环境与资源复用 | 发现非默认目录工具，复用科研绘图工具、配色和固定预检 |
| 论文与交付 | 从同一正文源构建 HTML/PDF，核对图表、实际 ZIP、包内复现和冻结字节 |
| 简单团队协作 | 精确锁定比赛仓库，用独立任务分支提交并按模式决定是否推送 |

仓库由轻量 [ContestFlow skill](skills/contestflow/SKILL.md)、按阶段读取的参考指南和 Python CLI 组成。skill 负责 Agent 的工作方式，CLI 负责可核验的文件与执行操作；两者都不会替团队作研究结论。

## Agent 如何工作

新比赛默认先核对材料和规则、形成逐问要求与候选路线。之后 Agent 在既有范围内持续执行：

1. 根据目标和现有证据列出优先项、预算、完成条件和停止条件；
2. 完成价值最高且不受阻的实现、实验或文稿工作，不停在列计划和状态汇报；
3. 用题目约束、独立验证和官方评测器检查实际产物，保留失败与反例；
4. 在 `docs/DECISIONS.md` 复盘完成项、证据、局限、当前阶段和下一步；
5. 刷新 `contestflow plan`，仍在授权范围且没有阻塞时继续下一项，并在里程碑提交。

只有缺少会改变路线、指标或预算的团队判断，涉及付费、账户、不可逆操作、外部提交，或工作区已经冻结时才暂停。团队审定与自动检查始终分开记录。

可以这样启动 Agent：

> 使用 ContestFlow。比赛工作区是 `<绝对路径>`，题面在 `<材料路径>`。先核对准确仓库和环境，整理逐问要求并建立阶段计划；随后主动完成不受阻的任务，每个阶段验证、复盘并继续。路线或指标需要我们决定时，先完成独立工作并给出有依据的选项。

## 快速开始

以下示例从源码建立独立环境，并把正式比赛放在工具仓库之外：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[science,documents]"
$ContestWorkspace = "D:\contests\my-contest"
.\.venv\Scripts\contestflow start $ContestWorkspace --materials "D:\path\to\problems" --title "我的比赛" --git-mode local
.\.venv\Scripts\contestflow repo $ContestWorkspace
```

需要 Python 3.11 或以上。Linux/macOS 使用 `.venv/bin/python` 和 `.venv/bin/contestflow`；PDF 另需 XeLaTeX、相应 TeX 包和字体。接下来让 Agent 读取工作区生成的 `AGENTS.md` 与 `docs/AI_TASK.md`。

已有工作区不会被重新初始化，也不会自动改写 `AGENTS.md`。升级后按需合并新版原则，再运行 `contestflow plan <工作区>`；保留已有团队记录和冻结版本。

## 比赛仓库与队友协作

正式比赛使用独立 Git 仓库。Agent 开始编辑和提交前运行 `contestflow repo <工作区绝对路径>`；启用 Git 时必须得到 `status: ready` 与 `root_matches: true`。

| 模式 | 行为 |
|---|---|
| `off` | 不初始化、不提交、不推送 |
| `local` | 在 `agent/<member>/<goal>` 分支做里程碑提交，不推送 |
| `team` | 同样提交；远端已由团队配置时，只正常推送自己的任务分支 |

CLI 不会自行 commit、push、merge 或配置远端。`main`、`dev` 保持受保护；队友交换分支名和提交号后审阅、合并或拣选。原始题面、数据、运行目录、候选成品和本机配置默认不入 Git。详见 [Git 与团队协作](docs/git-collaboration.md)。

## 环境、工具与资源

```powershell
.\.venv\Scripts\contestflow doctor $ContestWorkspace
.\.venv\Scripts\contestflow resources $ContestWorkspace --select tool.numpy tool.matplotlib palette.project-p7
.\.venv\Scripts\contestflow preflight $ContestWorkspace --profile full-html --level rehearsal --output "$ContestWorkspace\.contestflow\preflight\first-rehearsal"
```

`doctor` 只盘点；`preflight` 可做固定小样例或独立合成流程演练。工具不在默认目录时使用 `contestflow tools` 的有限发现和本机配置，不扫描整盘。预检通过只说明所选能力可运行，图表与 PDF 仍需实际查看。详见 [环境预检](docs/preflight.md)与[资源库](docs/resources.md)。

## 教学示例

```powershell
.\.venv\Scripts\contestflow demo workspaces/demo-assignment --example assignment --format html --allow-exec
.\.venv\Scripts\contestflow demo workspaces/demo-forecast --example forecast --format html --allow-exec
```

教学例连续演示实验、底表、图表、论文、实际 ZIP 复现与冻结前核验。它们使用合成数据，只证明工具链，不代表 Agent 能独立解决新赛题。来源与固定结果见 [示例说明](docs/example-provenance.md)。

## 主要命令

```text
contestflow start PATH --materials SOURCE [--git-mode MODE]
contestflow status PATH
contestflow next PATH
contestflow plan PATH
contestflow repo PATH [--init MODE | --disable]
contestflow doctor [PATH]
contestflow tools [PATH]
contestflow resources [PATH]
contestflow preflight [PATH]
contestflow run PATH --allow-exec [--workers 2] [--force]
contestflow compare PATH
contestflow charts PATH
contestflow select PATH SELECTION.json
contestflow paper PATH --format html|pdf
contestflow package PATH
contestflow verify PATH
contestflow verify PATH --smoke --allow-exec
contestflow freeze PATH --confirm
```

所有命令支持 `--help`。`run --allow-exec` 是运行已审查本地命令的许可，运行器不是安全沙箱。`verify` 证明已实现的技术检查，`freeze` 只固定候选字节；二者都不表示团队已审定或平台已接收。

`MODE` 可取 `off`、`local` 或 `team`；`repo --init` 只接受 `local`、`team`。

正文唯一入口是 `paper/draft.md`，可用 `{{metric:实验ID:指标名}}`、`{{table:comparison}}` 和 `{{figures}}` 引用登记证据。当前论文资源契约与安全边界见 [论文资源说明](docs/paper-resources.md)。

## 文档与参与

- [团队与 Agent 入口](AGENTS.md)
- [接入真实赛题](docs/adapter-guide.md)
- [Agent skill 安装](docs/agent-skill.md)
- [架构与证据契约](docs/architecture.md)
- [安全与公开边界](SECURITY.md)
- [Alpha 发布检查](docs/releasing.md)
- [当前路线图](docs/roadmap.md)
- [贡献约定](CONTRIBUTING.md)

发现错误、环境兼容问题或流程断点，欢迎[提交 Issue](https://github.com/whjwjx/ContestFlow/issues/new)；不要上传私有题面、凭据或队伍信息。贡献新的题型适配、资源或检查规则时，请附公开最小样例、测试和适用边界。如果项目对你有帮助，也欢迎给仓库一个 [Star](https://github.com/whjwjx/ContestFlow/stargazers)。

开发检查：

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check src tests scripts
.\.venv\Scripts\python -m ruff format --check src tests scripts
.\.venv\Scripts\python -m build
```

核心与示例代码采用 MIT 许可证。输入题面、第三方数据、字体、论文模板和官方评测器不会因使用本工具自动获得再分发许可。
