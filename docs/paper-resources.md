# 论文资源的 alpha 支持范围

论文构建接受 Markdown 正文、`paper/references.bib` 和 `paper/figures/` 内的 PNG/JPEG 图片。引用式图片与行内图片采用相同规则。正文中的 HTTP、HTTPS、mailto 与页内链接可以保留；构建不会为这些链接下载内容。

## 支持与拒绝

- 图片使用工作区根目录相对路径，例如 `![图注](paper/figures/extra.png){width=90%}`；只接受字面路径，不接受 URL 编码、查询串、片段、绝对路径、`..`、符号链接或 Windows junction。图片内容须有相应的 PNG/JPEG 头与受限尺寸。
- 不接收网络图片、用户提供的 data URI、SVG、PDF 图片、HTML/CSS 资源及其他容器。需要使用这些来源时，由团队用可信工具导出 PNG/JPEG，检查结果后放入 `paper/figures/`。
- Markdown 原生表格、引用、脚注、列表和代码展示可以使用。普通 fenced code 中展示 HTML/TeX 不会被执行，也不因此被拒绝。
- 不接收原始 HTML/TeX 节点、`{=html}` 等原始内容块和正文元数据块。标题、字体与字号在 `contest.json` 中配置；标题作为字面文本处理。字号限于 `10pt`、`11pt`、`12pt`，字体限于已安装的字体家族名称，不接收字体文件路径或 TeX 参数。
- 元素支持安全的 ID、class，以及数字加单位的 `width`/`height`。自定义 CSS、事件属性、样式和未知属性被拒绝。内置论文 CSS 固定生成，不读取用户样式表。

## 数学表达

常用算术、上下标、希腊字母、分数、根号、求和、积分、极限、关系和集合符号、数学字体、重音、`\text` 和 `\operatorname` 等采用明确的命令允许列表；完整列表是 `src/contestflow/paper_resources.py` 中的 `MATH_COMMANDS`。矩阵/分段/对齐环境支持 `matrix`、`pmatrix`、`bmatrix`、`Bmatrix`、`vmatrix`、`Vmatrix`、`smallmatrix`、`cases`、`aligned`、`alignedat`、`gathered`、`split`、`array`。

例如 `$\min_{\pi}\sum_i c_{i,\pi(i)}$` 可以使用。不支持 `\input`、`\includegraphics`、`\special`、`\csname`、命令定义、包加载、自定义宏和 TeX 字符编码改写；未知命令直接报告错误。不要通过关闭检查绕过错误，可改写公式或提出带测试的范围扩展。

## 输入身份与隔离目录

构建先由 Pandoc 将 Markdown 解析为 JSON AST，检查所有节点和资源引用，再处理明确指定的本地 Bib，重新检查引用处理后的 AST。随后按输入快照复制图片与 Bib，在临时目录构建。HTML 中的图片 data URI 由程序根据已校验字节生成，不使用 Pandoc 的 `--embed-resources`；PDF 只引用暂存的栅格图片。原始工作区不作为转换器的资源搜索路径。

正文、Bib 和配置每份最多 2 MiB；图目录最多 256 个文件/目录条目，单文件最多 16 MiB，全部论文输入最多 64 MiB；栅格最多 4000 万像素。这些是工具预算，不是当届提交规则。图目录中的 PDF 导出副本仍计入快照与预算，但不能作为正文图片输入。

`paper_context`/`paper_current` 只读文件，不运行转换器。整个图目录和资源策略实现进入输入身份；新增、修改或删除图片会使旧论文失效。正文、配置与 Bib 的实际读入字节、图片的实际复制字节均再次匹配快照哈希，然后才解码或解析；构建结束还会复核输入身份。

## 安全边界与依据

使用显式 Pandoc reader、`--sandbox` 和空的 `--data-dir`，不加载自定义 reader、filter、用户模板或默认数据目录覆盖项。Pandoc 的 sandbox 限制 reader/writer 的文件读取，**不等于隔离 PDF 引擎或整个操作系统**；它也不为任意过滤器提供隔离。依据：[Pandoc 官方手册](https://pandoc.org/MANUAL.html#general-options)。原 `--embed-resources` 会主动读取或下载引用资源，现已移除。依据：[官方 HTML 资源说明](https://pandoc.org/MANUAL.html#option--embed-resources)。

PDF 仍使用本机已选定的可信 Pandoc、XeLaTeX、字体与 TeX 包，并关闭 shell escape。输入约束不能代替可信工具来源、依赖更新或处理恶意文件所需的 OS 容器/沙箱；并发修改文件的本机攻击者也不在此隔离保证内。图片头与尺寸检查不是完整图像解码器安全审计。自动构建通过不说明图片匿名、模型正确、人工审稿完成或已满足竞赛规则。
