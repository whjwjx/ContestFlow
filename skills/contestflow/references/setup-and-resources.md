# 准备与复用

仅在安装、赛前准备、环境变化或资源选择时读取。本 skill 随附说明，不包含 Python 包、依赖、字体或模型服务。

## 先找到 CLI，再准备所需能力

优先沿用用户指定环境或项目已有虚拟环境，并用该解释器运行 `python -m contestflow --version`。不存在可用安装时，检查用户提供的可信 ContestFlow 源码或发布包；来源路径仍不清楚时询问具体位置，不假定已上架公共包索引。

从源码安装时在源码根目录使用 Python 3.11 及以上建立独立虚拟环境。以下为 Windows 示例：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m contestflow --version
```

Linux/macOS 对应 `.venv/bin/python`。已授权安装所需能力时，科学计算与绘图使用 `-e ".[science]"`，文稿读取和转换使用 `-e ".[documents]"`，两者使用 `-e ".[science,documents]"`；不为参赛用户默认安装开发工具或升级全局环境。PDF 另需可用 XeLaTeX、相应 TeX 包和字体；CLI 发现/预检不会自动安装这些软件。

## 非默认目录

```text
contestflow doctor
contestflow tools
contestflow tools WS
contestflow tools WS --set pandoc "D:\My Tools\Pandoc\pandoc.exe"
contestflow tools WS --search-dir "E:\Research Tools"
contestflow tools WS --unset pandoc
```

`doctor` 和不带修改选项的 `tools` 只发现安装信息与路径，不执行工具。发现顺序为显式本机配置、环境变量、当前环境/PATH/包内工具、已知及有限补充目录；不要另写全盘扫描脚本或仅因 PATH 没有就判未安装。支持定位 `pandoc`、`xelatex`、`git`、`nvidia-smi`。

失效配置会给出 `invalid`，补充目录的同级多候选可能给出 `ambiguous`。核对实际路径与差异；不能合理决定时集中请用户选择，再用 `--set` 记录。缺少 `WS` 的修改保存到用户本机配置，带 `WS` 的修改只影响该比赛。选用较窄范围；不要把本机绝对路径写到共享配置。工具版本和最小功能由下一步验证。

## 按本次能力预检

已有工作区先读取 `configs/preflight.json` 和 `configs/resources.json`；没有工作区也可省略 `WS` 先检查当前环境。

```text
contestflow preflight WS --profile core --level inventory
contestflow preflight WS --profile full-html --level functional --output .contestflow/preflight/check-001
contestflow preflight WS --profile full-pdf --level rehearsal --output .contestflow/preflight/rehearsal-001
```

- `inventory`：只盘点，已找到但未运行可标为 `not_tested`。
- `functional`：运行所选固定小样例，覆盖计算、绘图、文稿或解包复现等能力。
- `rehearsal`：在独立目录运行合成预测例的整链流程，不运行当前比赛代码。

按需要选 `core`、`science`、`plots`、`documents-html`、`documents-pdf`、`delivery`、`gpu`、`full-html` 或 `full-pdf`；所选资源的检查组会自动并入。GPU 不是默认必需，其当前检查只查询 NVIDIA 驱动，不验证任意 CUDA 任务。只要求盘点时不升级为功能运行或整链演练。

`--output` 必须是新的目录，相对当前命令工作目录解析；可使用比赛工作区下 `.contestflow/preflight/` 的绝对路径防止混淆。该输出包含本机路径，留在本地。省略输出目录时功能样例在临时目录完成并清理。冻结工作区的检查使用外部输出目录，不写入冻结内容。

逐项读 `passed`、`failed`、`missing`、`not_tested`、`not_needed`，不能把退出码 0 或盘点成功等同功能全通过。PDF/图表还需实际打开看字体、裁切、字号和可读性；报告的 `visual_review: required` 不由文本提取结果消除。修复已定位的问题后再新建报告复查。专用求解器、R/MATLAB 和远程服务没有通用适配器，未测项如实保留。

## 资源选择与跨比赛复用

```text
contestflow resources
contestflow resources WS
contestflow resources WS --select tool.numpy tool.matplotlib palette.project-p7
```

不带 `--select` 为只读资源目录；带该选项会覆盖本次完整选择，先读旧选择再合并要保留的条目。空 `--select` 清空显式选择。默认绘图样式记为 `automatic-default`，不能写成用户选稿。

共享选择在 `configs/resources.json`；自定义资源放 `configs/resource-library.json`，顶层为 `schema_version: 1` 与 `resources` 列表。参照 `resources` 返回的同类条目保留 `id`、`kind`、`title`、`source_url`、`purpose`、`requirements`、`checks`、`reuse`、`status`；配色另含 `colors`。目前仅支持 `tool` 和 `palette`，自定义 ID 不覆盖内置条目。

`checks` 只声明内置检查组，不可放可执行命令。`requirements` 为可读说明，不是任意软件自动安装或版本约束解析器。来源、许可范围和复用方法随资源保存，本机路径留在 `tools.local.json`；`collected`、`tested`、`project_used` 记录积累事实，不证明本次可用或符合比赛规则。赛后只沉淀实际有效的配置、合成最小例和失败经验，不把原始赛题或私人材料直接收入共享资源。
