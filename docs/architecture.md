# 架构与证据契约

核心仅依赖Python标准库，文件即接口；科学计算和文档依赖按需安装。

| 模块 | 职责 |
|---|---|
| `project` | 初始化、只读环境报告、下一阶段和AI任务 |
| `intake` | 有上限的复制与提取、原件哈希、来源定位 |
| `runner` | argv命令、唯一运行目录、环境/输入指纹、超时、失败和续跑 |
| `evidence` | 显式指标定义、完整性与比较底表 |
| `charts` | 科研图候选、离线审阅、版本绑定选择 |
| `reporting` | MD结果引用、Pandoc构建与失效检查 |
| `release` | 白名单打包、实际ZIP验证、包内烟测和字节冻结 |

`contest.json`、实验配置、指标定义及各清单使用`schema_version: 1`。一个运行产物的身份由相关文件字节、命令参数、Python/系统、声明的库版本及环境变量共同决定；未声明依赖、外部服务和非确定性设备仍可能影响结果。

依赖链：输入/源码 -> 运行 -> 指标底表 -> 图表选择 -> MD构建 -> ZIP -> 校验 -> 冻结。上游改变，下游检查不再有效。数学正确性、未登记的手写数字、来源真实性不由哈希自动证明。

工作区锁阻止CLI并发写入；每次实验使用独立输出目录。它不拦截用户编辑器或外部进程，因此运行和打包还会前后检查输入身份。冻结也不是操作系统权限锁；外部改写通过只读核验发现。

自动检查、AI审读、人工签认、用户报告上传和平台成功凭证不是同一状态。0.1版不提供假装可以代替团队审定的签字按钮。

来源参考：

- [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/why/)：标准化工程组织。
- [DVC流水线](https://doc.dvc.org/user-guide/pipelines)：阶段与依赖建模；本版本未集成DVC。
- [Pandoc手册](https://pandoc.org/MANUAL.html)：转换、引用和PDF引擎。
- [SciPy分配求解器](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)：优化示例依赖。
- [NumPy最小二乘](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html)：预测示例依赖。

设计来自一次数模项目的流程复盘，新仓库从零实现通用边界，没有复制官方题面、数据、评分器、成品论文或原仓库Git历史。
