# 架构与证据契约

ContestFlow 面向团队主导的数模协作：团队作出研究与提交判断，AI 在已授权阶段内辅助执行，工具记录证据并检查已实现的约束。核心仅依赖 Python 标准库，文件即接口；科学计算和文档依赖按需安装。

| 模块 | 职责 |
|---|---|
| `project` | 初始化、只读环境报告、技术阶段建议和团队判断提示 |
| `version_control` | 精确工作区仓库身份、Git 模式、只读状态和运行溯源 |
| `intake` | 有上限的复制与提取、原件哈希、来源定位 |
| `runner` | argv 命令、唯一运行目录、环境/输入指纹、超时、失败和续跑 |
| `evidence` | 显式指标定义、完整性与比较底表 |
| `charts` | 科研图候选、离线审阅、版本绑定选择 |
| `reporting` | MD 结果引用、Pandoc 构建与失效检查 |
| `paper_resources` | 受限 AST、输入字节与哈希绑定、栅格图片暂存 |
| `release` | 白名单打包、实际 ZIP 验证、包内烟测和字节冻结 |

## 阶段建议与人的判断

默认启动任务聚焦材料阅读、逐问要求和待决策清单。团队决定问题理解、模型假设、方法路线、预算和结论，AI 可在既有授权内连续辅助执行。每阶段提供成果、证据、局限与待审事项；已有授权不因调用下一条命令而失效。

`plan` / `next` 从文件与产物推断技术进度，输出协作信息：

| 字段 | 含义 |
|---|---|
| `stage` | 当前技术阶段，沿用既有值与含义 |
| `action` | 根据已有产物推荐的后续任务 |
| `automatic` | 该任务类型是否可辅助执行；不代表取得了团队授权 |
| `collaboration_mode` | 当前为 `team_led`，表达团队主导的协作约定 |
| `guidance_only` | 当前为 `true`，表示 CLI 只生成提示；不要求 Agent 停止等待 |
| `agent_execution` | `proactive_within_scope`，要求 Agent 在已有范围内主动形成工作闭环 |
| `continue_when_unblocked` | 未冻结时为 `true`，提示 Agent 完成复盘后继续不受阻的下一项 |
| `team_focus` | 当前阶段需要团队判断或审阅的事项 |
| `human_review` | 当前为 `not_asserted`，工具未声称团队已经审阅 |

协作字段以兼容方式追加，`schema_version` 仍为 1。Agent 按“规划、执行、验证、复盘、继续”推进；CLI 只保存提示与产物状态。技术进度可以推进，`human_review` 不会因此自动变成“已审阅”；当前没有基于身份的签认、可信签名或强制人工审核门禁。

## 证据与状态

`contest.json`、实验配置、指标定义及各清单使用 `schema_version: 1`。一个运行产物的身份由相关文件字节、命令参数、Python/系统、声明的库版本及环境变量共同决定；未声明依赖、外部服务和非确定性设备仍可能影响结果。

依赖链：输入/源码 -> 运行 -> 指标底表 -> 图表选择 -> MD 构建 -> ZIP -> 校验 -> 冻结。上游改变，下游检查不再有效。数学正确性、未登记的手写数字、来源真实性不由哈希自动证明。

工作区锁阻止 CLI 并发写入；每次实验使用独立输出目录。它不拦截用户编辑器或外部进程，因此运行和打包还会前后检查输入身份。冻结也不是操作系统权限锁；外部改写通过只读核验发现。

## 比赛仓库身份

正式比赛工作区与 ContestFlow 工具源码分离。`contest.json.version_control` 保存 `off`、`local` 或 `team` 策略；启用 Git 时，Git 顶层必须与 `contest.json` 所在目录完全一致。若目录已属于父仓库，工具拒绝创建嵌套仓库。`repo` 返回工作区、仓库顶层、分支、提交、脏状态和远端名称，不返回远端 URL。

CLI 只建立和检查身份，不执行 commit、push、merge 或远端配置。生成的 `AGENTS.md` 让 Agent 使用 `agent/<member>/<goal>` 任务分支形成里程碑；`local` 不推送，`team` 仅允许正常推送自己负责的任务分支。实验记录保存路径无关的模式、分支、提交与脏状态，但不把 Git 提交加入实验指纹，避免仅提交同一字节后把有效运行误判为过期。

自动检查、AI 审读、团队审定、用户报告上传和平台成功凭证应分别说明。图表样式选择只记录呈现选择；`verify` 只验证实现的技术检查；`freeze` 只冻结文件字节。它们不能作为团队已经理解、认可最终内容的证明。

`demo` 使用预设题目、程序、指标与报告演示这条依赖链，不包含真实比赛中由团队完成的建模决策。生产工作区的读题与论证应以原题、团队判断和可复现实验为依据。

## Agent 入口与文稿边界

`skills/contestflow/` 是可独立复制的薄协作入口，按阶段读取自身三个引用文件；算法、工具定位与校验仍调用 CLI。安装 skill 不安装 Python 包，两者都不会启动后台模型服务。

论文采用[受限输入契约](paper-resources.md)。草稿、配置、Bib 和图片的实际使用字节匹配快照后再转换；解析与引用处理后分别检查 AST，HTML 的内嵌图片由已核验字节生成。策略实现进入论文身份，旧构建需重建；这不是 OS 沙箱，也不会给人工审定赋值。

## 设计参考

- [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/why/)：标准化工程组织。
- [DVC 流水线](https://doc.dvc.org/user-guide/pipelines)：阶段与依赖建模；本版本未集成 DVC。
- [Pandoc 手册](https://pandoc.org/MANUAL.html)：转换、引用和 PDF 引擎。
- [SciPy 分配求解器](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)：优化示例依赖。
- [NumPy 最小二乘](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html)：预测示例依赖。

设计来自一次数模项目的流程复盘，新仓库从零实现通用边界，没有复制官方题面、数据、评分器、成品论文或原仓库 Git 历史。

## 环境发现、资源与预检

`toolchain` 合并用户/工作区本机配置，在有限范围定位受支持的程序；`reporting` 与 `doctor` 共用解析器，路径或文件状态变化会使旧论文身份失效，公共清单只记录摘要。发现本身不执行工具。

`resources` 管理内置与共享自定义资源、所选 ID 和配色定义。资源只声明固定检查组，不携带可执行命令。图表身份包括实际资源定义及字体配置，避免配色改变后旧图表仍被判断为当前。

`preflight` 负责配置、能力清单和本地报告，`preflight_probe` 在受时限约束的独立进程执行小样例。整链演练创建新的合成工作区，沿用所选工具和资源，不执行真实比赛代码。机器路径保存在 tools.local.json 或本地报告中；.contestflow 目录不能进入交付包。预检状态与人工审阅保持独立。

完整用法见[预检说明](preflight.md)与[资源库说明](resources.md)。
