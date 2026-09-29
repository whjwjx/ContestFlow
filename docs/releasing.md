# Alpha 发布检查

当前候选版本为 `0.2.0a1`，定位是“团队主导、面向 Agent 的数模竞赛工作流与可复现工具包”。它提供分阶段协作约定、资源复用和本地执行工具；没有后台模型服务，也不能把技术链路成功解释为完成比赛研究。

## 构建与验证

从干净检出或已核对的工作区，在独立 Python 环境执行：

~~~text
python -m pip install -e ".[science,documents,dev,audit]"
python -m pip check
python -m pytest -q
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pip freeze --exclude-editable --all > audit-requirements.txt
python -m pip_audit --strict --disable-pip --no-deps -r audit-requirements.txt
python -m build --outdir output/release-dist
python scripts/check_release_artifacts.py output/release-dist
~~~

使用新的输出目录，避免把旧版包当成此次结果。检查器读取实际归档，核对新增模块、模板、完整 skill 和许可证，拒绝常见私人缓存、路径和链接问题，输出 SHA-256；这不是内容隐私扫描的替代品。wheel 提供 CLI，sdist 另含完整 `skills/contestflow/`，安装方式见 [Agent skill](agent-skill.md)。

审计清单来自独立环境中全部已解析第三方包，只排除源码仓库自身的 editable 安装；`--no-deps` 用于审计完整精确清单，不能拿只有顶层依赖的列表代替。审计工具依赖也列入清单。不要通过忽略漏洞或关闭严格收集把失败改成通过；安装问题与漏洞结果分开记录。

[Windows/Python 3.13 依赖快照](../constraints/windows-py313-20260929.txt) 保存一次验证使用的版本，可在相同平台与解释器下作为 `pip install -c` 约束。它不包含安装包哈希，也不是 Linux、macOS 或所有 Python 版本的通用锁文件；其他环境应重新解析、测试和审计。

然后从构建的 wheel 安装到另一个不继承系统包的环境，检查版本、资源库及核心预检。带科学依赖的环境还应执行两个教学例、实际 ZIP 复现、HTML 和 PDF 功能检查。PDF 需要单独安装可信 XeLaTeX 和字体；实际打开生成文件审阅排版，自动文本检查不能替代视觉检查。

## 自动检查范围

`.github/workflows/ci.yml` 配置 Windows/Ubuntu × Python 3.11/3.13 的回归、格式、构建和归档检查，以及单独的依赖审计。Actions 固定到提交，权限仅为读取仓库，不执行发布。**配置已加入不代表远端运行已通过。** PDF 引擎未装入 CI，不据此声明完整 PDF 跨平台支持；不同平台不满足条件的跳过项必须在测试摘要中查看。

## 公开前由维护者完成

- 核对最终 diff、归档内容、第三方素材及来源说明；真实题面、数据、字体和模板的再分发权限不能从本工具的 MIT 许可证推导。
- 选择是否接受提交历史中的真实姓名或邮箱公开；需要处理时先制定方案，不直接改写已共享历史。修改未来提交身份不会删除过去的记录。
- 核实仓库可见性、远端目标、分支，以及 [私密漏洞报告](https://github.com/whjwjx/ContestFlow/security) 的可用性。参见 [GitHub 官方配置说明](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)。
- 查看当前提交的实际 CI 结果；由团队完成一次阶段式试用和成品审阅，明确已验证平台与未验证范围。
- 明确公开发布授权后再推送、创建版本或改变仓库可见性。不要自动上传比赛产物。

## 升级注意

论文资源规则在本版本收紧。旧工作区若引用外部图片、SVG、原始 HTML/TeX 或自定义宏，需要先将素材转换为受支持格式或改写文稿，再重建论文与候选包；不要静默放宽规则。旧构建身份会失效，已冻结成品保持原字节。新分配教学例的基线/最优值是 66/44，来源见 [示例配方](example-provenance.md)；历史工作区与历史验证记录不追改。
