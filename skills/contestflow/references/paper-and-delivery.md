# 论文与交付

用于已有证据后的图表、正文、候选包和复现。用户只要求一部分时，只执行相应范围；候选构建不隐含冻结或平台提交。

## 图表与论文

| 命令 | 前置条件、作用与限制 |
| --- | --- |
| `contestflow charts WS` | 基于当前有效比较底表写图表候选和离线审阅页；内置 bar/dot 用于实验标量指标对比 |
| `contestflow select WS SELECTION.json` | 导入与本轮候选身份匹配的实际呈现选择；不能用合成选择冒充用户选择 |
| `contestflow paper WS --format html` | 将当前正文、证据引用、图表交给 Pandoc 构建 HTML 候选 |
| `contestflow paper WS --format pdf` | 另需可用 XeLaTeX/字体，构建 PDF 候选；依赖路径用 CLI 工具发现，不自行拼默认路径 |

修改数据、资源或字体后重新生成受影响图表与候选；不手改已记录哈希的图再重签旧选择。样式选择不改变证据含义，团队仍需检查数值、单位、图例、纸面尺寸和正文解释。分布、消融、配对和灵敏度图需结合题目另行实现，不能将标量图装作这些验证。

正文唯一入口是 `paper/draft.md`，引用为 `paper/references.bib`。可用 `{{metric:实验ID:指标名}}`、`{{table:comparison}}`、`{{figures}}` 引入登记证据；构建不核对所有手写数字、推导和引用真实性。保留真实来源与结论边界，不用润色掩盖尚未解决的科学问题。

当前 alpha 只接受 Markdown/Bib 与 `paper/figures/` 内的 PNG/JPEG 正文图片，例如 `![图注](paper/figures/result.png)`。不接受网络/data 图片、SVG、原始 HTML/TeX、正文元数据、自定义 CSS 或宏；数学命令采用允许列表。用可信工具转换素材并实际审阅，不通过关闭检查消除错误。构建会绑定实际输入字节；修改正文、配置、引用或图片后重建候选。

PDF 要查看实际页面，检查中文、公式、分页、图表与引用；HTML 与 PDF 的版式分别核对。生成成功不等于视觉审阅完成。按当届规则披露实际 AI 参与、来源与核验，工具元数据未知时明确待核实，不统一虚填型号或日期。

## 候选包、复现和冻结

先审查 `contest.json.package.include`、实际交付格式、`private_markers` 和比赛要求。默认允许清单不是规则结论；原始材料、字体和第三方素材只有在明确允许交付时才列入。`paper/build/` 仅收集当前登记产物，不通过扩大白名单带入旧稿、构建日志或本机配置。

```text
contestflow package WS
contestflow verify WS
contestflow verify WS --smoke --allow-exec
```

- `package` 从允许清单生成实际 ZIP 和 `deliverables/candidate.json`，需要当前论文与证据。
- `verify` 核对实际包与源身份，未冻结时写 `deliverables/verification.json`；冻结后只核验并返回结果，不改冻结记录。
- `--smoke --allow-exec` 会把实际 ZIP 解压到独立目录并执行配置的复现程序，先审查 `package.smoke` 与执行授权。烟测须生成新结果，不能把包里已有结果当复现成功。

复现配置包含 argv `command`、新的 `result` 相对路径、`timeout_seconds`、`expected_metrics`。超时必须为有限数值且在 0 到 180 秒之间（不含 0），预期指标与容差也必须为有限数值。`docs/REPRODUCE.md` 写实际依赖、输入和命令，说明哪些实验已复现及哪些未覆盖。配置的单例烟测成功不等于所有实验均已重跑。

团队核对模型、全文、引用、匿名性、真实 AI 披露与提交规则，并明确安排冻结时，使用：

```text
contestflow freeze WS --confirm
```

冻结固定候选字节，产生 `deliverables/FROZEN.json`，不会填写团队签认或平台成功。已有冻结版本保持只读；内容修改需要另建版本，不改旧冻结记录。比赛报名、上传、点击提交或公开发布按用户另行明确授权执行，CLI 不提供这些平台操作。向用户报告候选文件、实际校验范围、未完成审阅和需其判断的内容。
