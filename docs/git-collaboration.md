# Git 与团队协作

ContestFlow 把通用工具和每场比赛分成两个仓库。工具源码仓库保存 CLI、skill、模板和测试；比赛仓库保存该场比赛的代码、配置、证据摘要、论文和协作文档。正式比赛建议使用工具仓库之外的目录，例如 `D:\contests\HuaweiCup2027`。

## 锁定准确仓库

比赛工作区 `WS` 是包含 `contest.json` 的目录。开始编辑和提交前运行：

```powershell
contestflow repo "D:\contests\HuaweiCup2027"
```

启用 Git 的工作区只有同时满足下列条件才可进行 Git 写操作：

- `status` 为 `ready`；
- `root_matches` 为 `true`；
- `workspace_root` 和 `repository_root` 都指向预期的 `WS`；
- 当前分支、现有差异和任务负责人可以解释。

如果工作区位于另一个仓库内部，ContestFlow 会拒绝初始化嵌套仓库。移动到独立目录或由团队明确按父仓库管理，不能因为终端当前所在位置相近就继续提交。

## 三种模式

| 模式 | 提交 | 推送 | 适用场景 |
|---|---|---|---|
| `off` | Agent 不自行提交 | 不推送 | 临时试用或团队另有版本管理方式 |
| `local` | 任务分支上的里程碑提交 | 不自动推送 | 单人比赛、先在本机积累可回退节点 |
| `team` | 任务分支上的里程碑提交 | 正常推送自己的任务分支 | 简单多人协作 |

新建工作区时选择模式：

```powershell
contestflow start WS --materials MATERIALS --git-mode local
contestflow start WS --materials MATERIALS --git-mode team
```

已有工作区可显式启用或关闭 Agent Git 行为：

```powershell
contestflow repo WS --init local
contestflow repo WS --init team
contestflow repo WS --disable
```

`--disable` 只关闭 Agent 的提交和推送策略，不删除 `.git` 或历史。CLI 不自动 commit、push、merge，也不设置远端。

## Agent 的提交方式

每个明确目标使用 `agent/<member>/<goal>` 分支，例如 `agent/alice/baseline` 或 `agent/bob/paper-methods`。一条任务分支由一名队友或一个 Agent 负责；`main`、`dev` 是受保护分支。新仓库还没有提交时，先创建任务分支，再形成首个里程碑。

开始修改前先检查当前分支、工作区状态和已有差异。保留不属于当前任务的修改，只暂存本任务的明确路径。以下节点适合提交：

1. 读题与需求基线已经可审阅；
2. 合法基线能够运行并有检查；
3. 一组成体系的实验及证据摘要完成；
4. 论文一个阶段稿与对应证据一致；
5. 交付候选完成技术核验。

提交说明应写清本次可审阅的结果与边界。普通格式微调可以并入相邻里程碑，不为制造记录而提交。

## 简单多人协作

`team` 模式不替团队创建远端。团队确认仓库地址和权限后配置一次：

```powershell
git -C WS remote add origin <团队仓库地址>
```

Agent 只正常推送自己负责的任务分支。没有远端时报告本地分支和提交号；不得猜测地址、强推、改写他人历史、直接推送受保护分支或自动合并队友分支。队友交换分支名和提交号，获取并审阅后，由团队决定合并整个分支还是拣选具体提交。

这种方式刻意保持简单：ContestFlow 不实现权限系统、任务锁或自动冲突解决。同一文件需要多人修改时，由团队先划分章节或顺序，避免多人长期写同一分支。

## 进入 Git 与留在本地的内容

默认适合进入 Git：

- `src/`、`configs/`、`tests/`；
- 可复核的 `evidence/` 摘要和底表；
- `paper/`、`docs/`、`plans/`；
- `contest.json`、`AGENTS.md` 与 `.gitignore`。

默认留在本地：

- 原始 `materials/` 与 `data/`；
- `runs/`、`reviews/`、`deliverables/`；
- `.venv/`、`.env*`、`*.local.json`；
- `.contestflow/` 和本机锁文件。

忽略只表示不进入 Git，不表示已经备份。队友确需共享原始题面、私有数据、大文件或候选 PDF 时，使用团队有权限的渠道并交换哈希；公开仓库前仍要检查实际已跟踪文件与 Git 历史。

## 实验溯源

实验记录保存运行时的 Git 模式、分支、提交号、脏状态和根目录是否匹配，不保存本机仓库路径或远端 URL。Git 提交号不参与实验输入指纹：同一批输入字节仅因形成提交，不会使运行自动过期；真正改变源码、配置或登记输入时仍会按字节身份失效。
