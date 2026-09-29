# 环境发现与赛前预检

预检服务于团队选定的工作方式。报告证明的是当前解释器、已选工具与小型样例的运行情况；题意、模型有效性、完整数据、图表表达、AI 披露和提交规则仍由团队判断。它不会把未进行的人工审阅记为完成。

## 三种检查深度

~~~powershell
$ContestWorkspace = "D:\contests\my-contest"

# 无工作区也能先盘点；只发现路径和安装信息，不执行工具。
contestflow doctor
contestflow tools

# 已有比赛按共享配置和所选资源检查。
contestflow preflight $ContestWorkspace

# 实际运行随包小样例，保留本地报告和可查看的图表/文档。
contestflow preflight $ContestWorkspace --profile full-html --level functional --output "$ContestWorkspace\.contestflow\preflight\first-check"

# 用独立合成例演练实验、底表、所选配色、论文和实际 ZIP 解包复现。
contestflow preflight $ContestWorkspace --profile full-pdf --level rehearsal --output "$ContestWorkspace\.contestflow\preflight\pdf-rehearsal"
~~~

未激活环境时使用 `.venv\Scripts\contestflow.exe`；Linux/macOS 为 `.venv/bin/contestflow`。当前进程的 Python 就是受检解释器，报告记录其准确路径。更换 Python 时从目标环境启动命令，不自动切换解释器。

- `inventory`：包存在性/版本和工具路径盘点；已找到但未运行标为 `not_tested`。
- `functional`：实际 CSV 读写、NumPy/SciPy 求解、中文 PNG/PDF、含公式/表格/引用的 HTML/PDF、ZIP 校验及解包运行。每组只运行固定小样例，受独立子进程超时约束。
- `rehearsal`：扩展为 HTML 或 PDF 全链路，在独立目录运行预设预测例；不运行原工作区的比赛代码。前置检查失败时保留诊断并跳过整链演练。

`--output` 必须是新目录，避免覆盖旧检查证据；省略时功能样例放临时目录，结束清理，结果打印至终端。建议放 `.contestflow/preflight/<本次名称>`，该目录被新工作区和工具仓库忽略，也被交付打包器拒绝。报告/日志包含本机路径，供本地诊断。冻结工作区可盘点或使用外部临时目录检查，不向其中保存报告或进行写入试验。

## 按需配置

新工作区生成 `configs/preflight.json`：

~~~json
{"schema_version": 1, "profile": "core"}
~~~

可选 profile 为 `core`、`science`、`plots`、`documents-html`、`documents-pdf`、`delivery`、`gpu`、`full-html`、`full-pdf`。命令行 `--profile` 临时覆盖。所选[资源](resources.md)的检查组自动并入；例如选用科研配色会检查绘图及科学计算。GPU 只有选中时才成为要求；GPU 检查仅核实 NVIDIA 驱动查询，不证明某个 CUDA/框架任务可用。

PDF 使用 `contest.json` 中 `paper.cjk_font` 和 `paper.main_font`。未配置中文字体且正文含汉字时，探针与论文构建共用按系统选择的默认值；缺字体明确失败并提示配置。绘图探针检查中文、负号和导出，论文探针检查 PDF 可读取、示例数值和缺字警告；字号、裁切、可读性仍需打开实际文件审阅。MiKTeX 的 PDF 探针和整链演练都禁用自动补包，缺包时报告失败。

结果逐项使用 `passed`、`failed`、`missing`、`not_tested`、`not_needed`。顶层 `result` 只汇总选中项；存在失败/缺失时退出码为 1，配置/用法错误为 2，其余为 0。`inventory` 的退出码 0 不表示功能验证通过。失败项带诊断和修复方向，修复后创建新报告目录复查。

## 工具不在默认目录

定位与论文实际构建共用同一实现，支持 `pandoc`、`xelatex`、`git` 和 `nvidia-smi`：

1. 工作区和用户已指定的工具路径。
2. `PANDOC`、`XELATEX`、`GIT`、`NVIDIA_SMI` 环境变量。
3. 当前 Python 环境邻近工具、PATH、Python 包自带 Pandoc。
4. 已知安装位置与用户登记的补充目录，按有限范围查找。

~~~powershell
# 无工作区参数：保存到用户本机配置，下次比赛可继续使用。
contestflow tools --set pandoc "D:\My Tools\Pandoc\pandoc.exe"

# 仅本场比赛使用该路径，覆盖用户级设置。
contestflow tools $ContestWorkspace --set xelatex "D:\TeX Tools\bin\xelatex.exe"

# 登记补充目录；查该目录及有限的 bin/Scripts 子目录，不遍历整盘。
contestflow tools --search-dir "E:\Research Tools"

# 清除本层指定路径，再按优先级发现。
contestflow tools $ContestWorkspace --unset xelatex
~~~

指定路径失效时明确报 `invalid`，避免悄悄换成另一版本。补充搜索同一优先级出现多个候选时报 `ambiguous` 并列出路径，团队选择后用 `--set` 保存。PATH 已有的顺序会被尊重。每次使用重新检查路径，不依赖永不过期的发现缓存。

共享配置只保存功能和资源选择；内置依赖最低版本参与检查，资源 requirements 是可读说明，尚不解析任意第三方版本约束；路径放工作区 `tools.local.json` 或用户配置目录中的同名文件。可用 `CONTESTFLOW_USER_CONFIG` 指向独立的用户配置文件。发现不会安装或升级软件；功能预检会启动被选定的程序验证。CLI 返回候选和修复建议，由当前 AI 会话据此继续排查，只有仍有歧义时集中询问用户。

已有工作区不会自动迁移规则或忽略列表：可手动增加 `.contestflow/` 忽略项；缺省共享预检配置按 `core` 处理，无需重新初始化。字体、专用求解器、R/MATLAB、远程服务和付费许可证尚没有通用自动发现/验收适配器，按实际需要扩展固定检查，未检测能力不能记为通过。
