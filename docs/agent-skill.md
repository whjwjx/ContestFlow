# 面向 Agent 的 skill 入口

ContestFlow 提供协作 skill 和 Python CLI 两部分：skill 帮助 Agent 判断当前范围、读取阶段指南和调用工具；CLI 负责本地运行、记录与技术校验。团队负责模型路线、预算、证据解释和最终审定。安装 skill 不会安装 Python 依赖，也不启动模型服务或无人值守比赛任务。

## 准备与使用

1. 按仓库 README 安装 `contestflow-local` 到独立 Python 环境，核对该环境的 `python -m contestflow --version`。科学计算、文稿转换与系统 PDF 工具按本次需要准备。
2. 按所用 Agent 的 skill 安装方式，将完整的 [`skills/contestflow`](../skills/contestflow/SKILL.md) 目录复制或注册到其支持的位置。保留 `SKILL.md`、`references/` 与 `agents/` 的相对关系；不要只复制主文件。安装位置由宿主决定，本仓库不自动改写用户全局 skill 目录。
3. 告知 Agent 比赛工作区绝对路径、题面来源、Git 模式和已经确定的阶段范围。CLI 若不在 PATH，提供安装环境或解释器路径；工具的其他非默认目录交给 `doctor` / `tools` 发现。Agent 会用 `contestflow repo <工作区>` 核对 `contest.json` 与 Git 顶层，避免误改工具包或另一场比赛。

支持 SKILL.md 的宿主可加载该目录；不支持 skill 自动发现的 Agent，也可由用户明确要求阅读入口文件。`agents/openai.yaml` 提供可选的界面元数据，默认保持自动发现；是否自动选择及调用方式由宿主能力决定。不要假定所有 Agent 都支持同一种安装路径或调用语法。

启动示例：

> 使用 ContestFlow skill。比赛工作区为 `<绝对路径>`，题面为 `<材料路径>`，Git 使用 `local` 模式。先核对仓库与环境，再整理逐问要求、约束、评价口径和材料缺口，给出需要团队判断的路线选项。暂不展开正式模型与整篇论文。

继续已有阶段：

> 使用 ContestFlow skill。继续 `<工作区>` 中已经确定的路线 B，先验证假设 H1，实验总预算 30 分钟。请在此范围内连续实现、运行与修复，结束后报告证据、失败与结论边界。

若宿主支持 `$skill-name` 显式调用，也可用 `$contestflow`。这些示例描述用户意图，不是放宽执行权限、付费权限或平台提交权限的通行证。

## 分工与维护边界

- [主入口](../skills/contestflow/SKILL.md) 保留任务范围、工作区定位、团队决策与命令结果解释。
- [准备与复用](../skills/contestflow/references/setup-and-resources.md) 覆盖安装前提、路径发现、预检及资源。
- [研究与证据](../skills/contestflow/references/research-and-evidence.md) 覆盖读题、研究决定、实验协议和底表。
- [论文与交付](../skills/contestflow/references/paper-and-delivery.md) 覆盖图表选择、正文、实际包和冻结。

skill 的三个引用文件随 skill 一起分发，运行时不依赖安装目录之外的仓库文档。命令行为以所安装 CLI 的帮助和版本为准；更新 CLI 契约时同步维护这些说明。它不复制算法实现、工具发现代码或模型服务；`plan` / `next` 仍只根据产物给出技术进度建议，研究计划和实际团队决定单独保存。

升级 skill 时替换已安装 skill 的对应文件；比赛工作区的 AGENTS 和团队记录不会因此自动迁移。已有工作区应按实际需要合并适用的新原则，不能重新初始化覆盖记录或改写冻结成品。
