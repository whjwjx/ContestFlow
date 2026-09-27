# 接入一份真实赛题

AI先完成原题理解，再填写下面文件。`start`只导入材料并安排读题任务，不自动臆测小问、竞赛规则或合适算法。

## 小问和规则

在`plans/requirements.json`的`items`中逐项填写`id`、`question`、`source`、`acceptance`。`source`指材料清单中的原件及页码/段落。约束、允许的决策变量、输出格式和评价口径另补在每项中。

规则填入`contest.json.rules`，保存官方来源和核查情况；截止时间应含日期、时间及时区。当前默认50MiB只是保守演示配置，不代表任何比赛真实限制。真实AI规定必须核对当届原文，工具不预填模型名或发布日期。

## 实验协议

`configs/experiments.json`示例：

```json
{
  "schema_version": 1,
  "experiments": [{
    "id": "baseline",
    "command": ["{python}", "{workspace}/src/solve.py", "--output", "{run_dir}/result.json"],
    "inputs": ["src", "data/processed"],
    "outputs": ["result.json"],
    "packages": ["numpy"],
    "timeout_seconds": 120
  }]
}
```

`command`必须为参数数组，不拼shell字符串。路径占位仅替换`{python}`、`{workspace}`、`{run_dir}`。工作目录为工作区，输出写入本次运行目录；第三方程序也可通过适配脚本转换协议。完整登记模型文件、评分器、输入和环境文件，避免漏掉影响结果的依赖。

`result.json`需要`valid: true`和有限数值的`metrics`对象。`valid`须由适配器对实际方案验证，不能恒定写true。额外字段可记录预测、约束检查、官方评分器结果、诊断与限制。通用引擎检查协议，题目合法性仍由适配器实现并测试。

`evidence/metrics.json`逐项定义`label`、`unit`、`direction`（min/max）、`definition`和`aggregation`。结果指标集合必须严格对应；空值、NaN、失败和缺项不会作为高分隐藏。

默认预算只限制单次实验数量、并发与单任务时间。AI还须在复盘中设置总时间、总候选数和停止条件；当前没有跨调用累计计费或分布式资源配额系统。

## 图、文与提交

先核对比较底表，再构建图表。0.1版内置的是“各实验标量指标对比”，不能替代分布图、消融、灵敏度或配对因果分析。需要专用图时扩展绘图器及其证据清单，不能直接覆盖已记录哈希的图后继续使用旧选择。

正文放`paper/draft.md`，引用放`paper/references.bib`。结果占位可自动同步，所有其余论证仍须逐章审读。图表配色与表格样式不改变数字；图片和公式要核对最终PDF。

配置`package.include`只收集必要公开源码、说明与证据；原始材料默认不能打包。确需交付数据，先检查许可并显式选择派生或经许可数据。`package.private_markers`填队号、姓名等应从匿名文件排除的标记。

Python字节码及`__pycache__`、pytest/ruff缓存会自动排除；私人目录和密钥文件则直接拒绝，不能用“忽略警告”跳过。其他大文件应通过缩小白名单明确排除。

`paper/build/`仅纳入当前构建清单登记的输出与清单本身，排除旧格式产物和可能包含本机路径的构建日志。需要同时提交HTML和PDF时，在相同源版本下分别构建两种格式。

可选`package.smoke`含`command`、新生成的`result`路径、`timeout_seconds`和`expected_metrics`。烟测从实际ZIP独立解压后执行，不允许拿包内原有结果文件当运行成功证据。程序声明需按真实AI使用与规则落实，本版不自动给全部代码填写虚假统一署名。
