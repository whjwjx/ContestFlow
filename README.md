# ContestFlow

面向数模与离线算法竞赛的本地、AI就绪工作流。把赛题交给有文件与终端能力的AI后，由AI阅读题面、自主规划并执行；工具负责材料索引、可复现实验、证据、图表审阅、论文构建和交付校验。

**目前是可运行的0.1版，不是通用自动解题模型。** CLI本身不调用LLM，也不会在没有AI会话时自动理解新赛题。它不保证获奖，不自动上传比赛平台，不代替团队审定。

## 下次比赛怎样用

在本项目打开AI任务，给出题面/附件路径，并说：

> 按AGENTS.md启动这次比赛。赛题在`<路径>`，截止时间是`<时间和时区>`。请自主读题、逐小问分析、制定预算、实现基线、做实验并同步写论文；每完成阶段复盘后继续。缺少关键信息或需要人工确认时再问我。

AI应按[入口规范](AGENTS.md)建立独立工作区，不在工具源码目录里混放比赛材料。想直接启动材料导入，也可以使用下面的CLI。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[science,documents,dev]"
.\.venv\Scripts\contestflow start workspaces/my-contest --materials "D:\path\to\problems" --title "我的比赛"
```

Linux/macOS使用`.venv/bin/python`和`.venv/bin/contestflow`。当前Windows本机已创建`.venv`；公开项目不绑定本机路径。核心命令不依赖科学计算包，`science`供示例与绘图，`documents`供PDF读取和Pandoc。生成PDF还需系统安装XeLaTeX及所用字体。

接下来让AI读取生成的`workspaces/my-contest/AGENTS.md`与`docs/AI_TASK.md`，持续推进。既有比赛不会被重新初始化覆盖；原件按哈希复制，导入代码不执行。

## 先跑一个完整例子

```powershell
.\.venv\Scripts\contestflow doctor
.\.venv\Scripts\contestflow demo workspaces/demo-assignment --example assignment --format html --allow-exec
.\.venv\Scripts\contestflow demo workspaces/demo-forecast --example forecast --format html --allow-exec
```

优化示例使用SciPy求解分配问题，并以小规模枚举独立核对；预测示例使用NumPy拟合线性趋势，按时间划分训练与留出数据。两者都是合成教学题，不是本次竞赛题、国奖成果或真实泛化验证。

演示结束后查看：

| 内容 | 工作区内路径 |
|---|---|
| 当前AI任务与下一阶段 | `docs/AI_TASK.md`、`contestflow next <工作区>` |
| 原始输入、代码版本和失败记录 | `runs/<实验>/<运行>/record.json`与日志 |
| 指标定义与可重算底表 | `evidence/metrics.json`、`comparison.csv` |
| 可离线打开的图型/配色/表格选择页 | `reviews/index.html` |
| 唯一正文源与生成报告 | `paper/draft.md`、`paper/build/paper.html` |
| 实际ZIP与校验结果 | `deliverables/candidate.json`、`verification.json` |

浏览器导出的选择文件用`contestflow select <工作区> <figure-selection.json>`导入；重新构建论文后生成新候选包。默认样式会明确记为`automatic-default`，不冒充用户确认。

## 工作流命令

所有命令都可加`--help`；路径参数允许绝对或相对路径。

```text
contestflow init PATH [--example assignment|forecast]
contestflow start PATH --materials SOURCE
contestflow intake PATH --materials SOURCE
contestflow plan PATH
contestflow next PATH
contestflow status PATH
contestflow run PATH --allow-exec [--workers 2] [--force]
contestflow compare PATH
contestflow charts PATH
contestflow select PATH SELECTION.json
contestflow paper PATH --format html|pdf
contestflow package PATH
contestflow verify PATH [--smoke --allow-exec]
contestflow freeze PATH --confirm
```

`run`默认复用指纹及产物哈希均一致的成功记录；输入、源码、声明的包版本或参数变化后重新运行。失败、超时和旧尝试保留。先审查配置，再授予`--allow-exec`；运行器不是安全沙箱。

`package`只复制允许清单；`verify --smoke`从实际ZIP解压后运行配置的复现例。`freeze`只冻结字节，不表示团队已经审定或平台提交成功，且默认不生成平台MD5。冻结后必须创建新版本才能继续修改。

## 论文与图表

Markdown支持`{{metric:实验ID:指标名}}`、`{{table:comparison}}`和`{{figures}}`，构建时从有效底表替换。未运行成功、证据过期、未知指标或`TODO`占位会阻止构建。手写数字与数学推导仍需AI和团队审读，工具不声称能自动验证所有论文内容。

中文PDF在`contest.json`的`paper.cjk_font`填已安装字体名，规则优先于个人偏好。PDF/HTML共享正文，版式仍需分别检查。图表提供两种适合标量比较的图型、三套配色及两种表格样式；复杂流程图、分布和配对分析由AI按题目另行实现，不能用错误图型装饰数据。

## 文档与开发

- [AI启动与自主边界](AGENTS.md)
- [架构与协议](docs/architecture.md)
- [扩展赛题适配器](docs/adapter-guide.md)
- [安全与公开边界](SECURITY.md)
- [路线图与验证记录](docs/roadmap.md)
- [贡献规范](CONTRIBUTING.md)

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check src tests
.\.venv\Scripts\python -m build
```

核心与示例代码采用MIT许可证。输入题面、第三方数据、字体、论文模板、官方评测器不因使用本工具自动获得再分发许可。仓库默认忽略`workspaces/`，尚未创建远端仓库或发布到包索引。
