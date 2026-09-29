# 可复用工具与样式

资源库保存来源、适用场景、依赖、检查组和复用方法。本次比赛的选择与资源定义分开保存，便于下一场复用。它不会自动安装工具、下载字体、运行资源提供的命令，也不把团队选色写成规则合规或人工审定。

## 查看和选择

```powershell
contestflow resources
contestflow resources workspaces/my-contest
contestflow resources workspaces/my-contest --select tool.numpy tool.matplotlib palette.project-p7
contestflow preflight workspaces/my-contest
```

未激活环境时使用 `.venv\Scripts\contestflow.exe`；Linux/macOS 为 `.venv/bin/contestflow`。

`--select` 写入本次**完整选择**，不是追加。顺序决定绘图候选配色顺序；初次生成图表时，默认采用首套配色的柱形图，并标记 `automatic-default` / `human_review: not_asserted`。该默认值不代表团队已经看过图。

- `configs/resources.json`：本次显式选择的资源 ID，可共享；执行 `contestflow resources workspaces/my-contest --select` 可清空显式选择。
- `configs/resource-library.json`：项目自定义资源，可复制到下一场比赛，也可随项目分享。
- 工具实际安装路径与本机版本不写在资源定义中；本机路径由工具发现配置管理，实际版本和功能检查结果由预检报告记录。

资源 `checks` 会加入预检所需检查组。只收录或选择一个工具不表示它在本机已安装或可用；要求范围和未验证项目以当次预检报告为准。

## 内置资源

| ID | 用途与边界 |
| --- | --- |
| `tool.numpy`、`tool.scipy` | 科学计算；先验证小算例，再根据题目约束选择算法 |
| `tool.matplotlib` | 从底表生成图；检查字体、尺寸、标注和图表解释 |
| `tool.pandoc`、`tool.xelatex`、`tool.pypdf` | 文稿转换、中文 PDF 编译和 PDF 技术检查 |
| `palette.journal`、`palette.contrast`、`palette.mono` | 保留原有三组候选；名称不代表期刊标准或已通过可访问性检查 |
| `palette.project-p6` | 项目经验三色子集：`#4477BB`、`#228833`、`#CC4466` |
| `palette.project-p7` | 项目经验三色子集：`#56B4E9`、`#E69F00`、`#CC79A7` |

P6 的历史来源记录指向 [Paul Tol 的说明](https://sronpersonalpages.nl/~pault/)，P7 的颜色来源为 [Color Universal Design](https://jfly.uni-koeln.de/color/)。P6/P7 是项目内的标签，不是完整官方调色板名称；只提取通用颜色值和选择经验，没有导入比赛数据、结果、论文或字体文件。使用者仍须结合当前背景、类别数量和纸面尺寸审阅成图，并用文字、形状或线型补充颜色编码。

未显式选择配色时，`charts` 仍生成旧有三组配色；选择 P6/P7 后只生成所选组，不会把所有收藏全部展开。仅选择工具时也继续使用旧有三组配色。

图表记录所用资源的完整定义和内容哈希，以及 `contest.json` 中的 `paper.cjk_font`。明确配置字体时必须在当前环境可用；未配置时按可用中文字体候选回退。修改所选颜色、来源说明或字体配置后，旧审阅记录会过期，需要重新生成图表再选。已有图表选择文件不会被自动覆盖。旧版本缺少资源上下文的审阅记录也会要求重建，冻结工作区不作迁移。

## 添加自己的资源

新建或编辑 `configs/resource-library.json`：

```json
{
  "schema_version": 1,
  "resources": [
    {
      "id": "palette.team-three",
      "kind": "palette",
      "title": "团队三色候选",
      "source_url": "https://jfly.uni-koeln.de/color/",
      "purpose": "少量类别的离散对比图；按实际纸面尺寸审阅。",
      "requirements": ["contestflow-local[science]"],
      "checks": ["plots"],
      "reuse": "选取来源中的三色作为候选，结合标签或形状区分类别；尚未完成本项目图表审阅。",
      "status": "collected",
      "colors": ["#0072B2", "#D55E00", "#009E73"]
    }
  ]
}
```

然后执行 `contestflow resources workspaces/my-contest --select palette.team-three`。这份定义本身就是可移植的最小配色示例；使用教学工作区的合成底表可以预览效果。

字段约定：

- `id`：`tool.` 或 `palette.` 开头，后面为小写字母、数字、连字符或下划线，最长 48 个字符；须与 `kind` 对应，不允许重复或覆盖内置 ID。
- `kind`：当前只支持 `tool`、`palette`。后续图型方法或经验文章可先在项目文档记录，不冒充已有可执行适配器。
- `title`、`purpose`、`reuse`：非空文本。`reuse` 建议写实际使用方法、失败条件、使用限制及需要人工检查的内容。
- `source_url`：HTTP(S) 原始来源。工具引用官方文档，配色保留原作者来源；自行设计的样式可引用自己的公开项目页面。登记来源不自动授权复制软件、素材或字体。
- `requirements`：可读的依赖说明列表；不是安装命令，也不会自动解析执行。
- `checks`：仅支持 `core`、`science`、`plots`、`documents-html`、`documents-pdf`、`delivery`、`gpu` 这些内置组。不能填 Shell 命令或 Python 代码。
- `colors`：仅配色资源使用，1 至 12 个 `#RRGGBB` 颜色；类别超出颜色数量时绘图会循环，须检查可区分性。
- `status`：资源积累阶段，含义见下表。

| 状态 | 记录的事实 | 仍需确认 |
| --- | --- | --- |
| `collected` | 已收录来源和使用说明 | 在目标环境运行与适用性 |
| `tested` | 维护者曾按明确场景试用；在 `reuse` 写明证据、版本和局限 | 本机是否仍能运行、是否适合当前题目 |
| `project_used` | 已有项目采用记录；在 `reuse` 说明范围 | 新项目数据、图型、规则和团队审定 |

内置工具先记为 `collected`；当前机器的实测版本由预检报告提供，不写成跨机器保证。内置配色记为历史 `project_used`，也不推断新团队的偏好。不要把状态升级代替实际运行和团队审阅。

## 赛后如何沉淀

保留真正使用过的资源定义、依赖要求、最小合成示例和有效/失败经验；将版本实测与检查结果保存在对应环境记录。下一次复制共享配置，重新发现本机工具并运行预检，再根据新题目选择。字体文件和第三方素材仅在明确许可允许时另行整理。

Matplotlib 的样式复用方式参考[官方样式与 rcParams 文档](https://matplotlib.org/stable/users/explain/customizing.html)。项目目前提供配色定义与现有 bar/dot 渲染，不声称已实现任意字体包、图型模板或通用绘图平台。
