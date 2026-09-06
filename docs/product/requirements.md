# PDF 论文语义分析、翻译与重排工具——产品需求文档

[中文](./requirements.md) | [English](./requirements.en.md)

> Document Type: Product / User Requirements
> Status: Draft v0.2
> Scope: Product Requirements Source of Truth
> Language: zh-CN
> Supersedes: v0.1

---

## 1. 文档目的

本文档定义本项目面向最终用户所需要解决的问题、核心使用场景、功能需求、交互要求、质量要求、产品边界、阶段性范围与验收标准。

本文档回答的是：

> **“这个产品应该为用户做到什么？”**

而不是：

> “具体应该使用什么 Parser、Schema、框架、算法或语言实现？”

项目中的：

* Architecture；
* Schema；
* ADR；
* Implementation Plan；
* Milestone；
* Phase Plan；

均应以本文档作为上游需求约束。

当技术方案与本文档中的产品需求发生冲突时，应优先重新审视技术方案，而不是静默修改产品需求。

---

## 2. 产品定义

本项目是一套面向学术论文的：

```text
PDF
↓
结构与语义恢复
↓
Semantic Document
↓
翻译
↓
学术文档重排
↓
Target PDF
```

处理系统。

产品的核心目标不是简单提取 PDF 文本，也不是在原 PDF 页面中直接覆盖翻译文本，而是：

> **从 PDF 中恢复论文的阅读结构、语义结构、公式、表格、图片、引用关系及来源位置，在此基础上生成结构正确、可重新排版、可追溯，并能够与原 PDF 建立语义对应关系的目标语言论文。**

最终用户看到的不应当是一组孤立文本块，而应当仍然是一篇可以正常阅读的学术论文。

---

## 3. 产品背景

传统 PDF 翻译通常采用以下几类方案：

1. PDF 文本提取后输出纯文本或 Markdown；
2. 在原 PDF bbox 中直接替换文本；
3. OCR 后按照页面坐标重新拼装；
4. 将 PDF 转换为 HTML 后进行浏览器排版；
5. 对每一个文本块独立翻译并覆盖回原页面。

这些方案对于学术论文存在明显问题。

不同语言之间文本长度不同，因此简单的 bbox 替换很容易出现：

* 文本溢出；
* 字号被迫缩小；
* 行距异常；
* 多栏错位；
* Figure/Table 与正文互相覆盖；
* 脚注位置错误；
* 页面布局越来越难以维护。

另一方面，如果完全放弃论文结构，只输出 Markdown，则 PDF 本身包含的大量信息会被丢失，例如：

* 标题层级；
* 作者与机构；
* 双栏阅读顺序；
* 数学公式；
* Figure；
* Table；
* Caption；
* Footnote；
* Citation；
* Reference；
* Section 层级；
* 页面来源位置。

因此，本项目采用另一种产品思路：

> **不复制 PDF 的像素布局，而是恢复论文的语义结构与阅读流，再重新生成目标语言学术文档。**

---

## 4. 产品核心原则

本项目遵循三个核心原则：

> **Preserve semantics, not pixels.**

保留语义，而不是像素。

> **Preserve provenance, not page positions.**

保留来源，而不是页码位置。

> **Reconstruct the paper, not the PDF canvas.**

重建论文，而不是复制 PDF 画布。

---

## 5. 产品目标

## G1. 恢复论文，而不仅是恢复文字

系统必须能够理解 PDF 中哪些内容属于：

* Title；
* Author；
* Affiliation；
* Abstract；
* Section；
* Subsection；
* Paragraph；
* Equation；
* Figure；
* Table；
* Caption；
* Footnote；
* Citation；
* References；
* 其他必要学术文档结构。

用户最终获得的是一篇具有正常论文结构的目标语言文档。

---

## G2. 保持信息来源可追溯

目标语言文档中的主要语义单元必须能够追溯到原 PDF。

用户应能够知道：

> “这一段译文对应原 PDF 的哪一段？”

以及：

> “原 PDF 的这一段对应哪一段译文？”

这种关系不能因为重新分页或重新排版而失效。

---

## G3. 正确处理语言长度变化

翻译造成的文本长度变化必须通过正常文档 Reflow 解决，而不是：

* 强行限制文本框大小；
* 极端缩小字体；
* 覆盖相邻内容；
* 强制保持源 PDF 页码。

目标语言论文允许重新分页。

---

## G4. 保留学术论文阅读体验

生成后的目标语言 PDF 应当仍然像一篇正式论文，而不是：

* 网页截图；
* Markdown 打印稿；
* OCR 文本集合；
* 大量文本框拼接得到的 PDF。

必须尽可能保留：

* 清晰结构层级；
* 正确 Figure/Table；
* 数学公式；
* Caption；
* Citation；
* References；
* 正常分页；
* 学术排版。

---

## G5. 支持原文与译文联合阅读

初步产品中，Target PDF 默认只包含译文。

因此用户在阅读译文时仍然需要随时查阅 Source PDF。

产品需要支持：

```text
Source PDF ↔ Target PDF
```

之间的快速双向语义定位。

---

## G6. Local First

初步产品优先作为本地应用运行。

PDF：

* 解析；
* 中间结构；
* 缓存；
* 渲染；
* 项目状态；

原则上均由本地应用负责管理。

翻译服务可以通过外部 Provider 调用。

未来再扩展：

```text
Server + Web Client
```

形态。

---

## 6. 当前阶段产品范围

本文档将需求划分为：

```text
Initial Product
```

与：

```text
Post-Initial Product
```

两个层级。

其中 Initial Product 是当前开发工作的主要目标。

---

## 7. Initial Product 定义

首个可用产品至少满足：

```text
Born-digital Academic PDF
        ↓
结构恢复
        ↓
SemanticDocument
        ↓
外部翻译 Provider
        ↓
单栏纯译文 PDF
        ↓
Source / Target 双栏 Viewer
        ↓
Paragraph / SemanticNode 双向定位
```

当前明确：

* 不支持扫描 PDF；
* Target PDF 默认单栏；
* Target PDF 默认纯译文；
* Figure 图片内部文字不翻译；
* References 不翻译；
* SemanticDocument 暂不允许用户编辑；
* Translation Provider 可替换；
* 产品本地运行。

---

## 8. 非目标

## NG1. 初版不支持扫描 PDF

首个正式版本仅要求支持：

> **Born-digital PDF**

即具有正常数字文本层、字体信息和页面对象结构的 PDF。

以下内容暂不属于 Initial Product：

* 扫描论文；
* 图片型 PDF；
* 全文 OCR；
* OCR Reading Order Recovery。

扫描 PDF 支持作为后续扩展能力。

---

## NG2. 不追求像素级复刻原 PDF

Target PDF 不需要满足：

```text
Source Element Coordinates
=
Target Element Coordinates
```

原文第 4 页的一段内容，翻译后完全可以出现在目标文档第 5 页。

---

## NG3. 不要求 Source Page 与 Target Page 一一对应

分页属于 Renderer 的结果，不属于文档语义。

因此：

```text
Source Page 5
↓
Target Page 5
```

不是系统需要维护的核心关系。

真正需要维护的是：

```text
Source Semantic Node
↕
Translated Semantic Node
```

---

## NG4. 不进行字符级 Source Mapping

当前产品只要求至少达到：

> **Paragraph / SemanticNode Level**

稳定映射。

不要求：

```text
source character 125
↔
translated character 218
```

也不要求 Word-Level Alignment。

---

## NG5. 不以 Markdown 作为最终产品形态

Markdown 可以作为：

* Debug 输出；
* 中间表示；
* 开发辅助；
* 可选导出格式。

但 Markdown 不应取代正式目标语言 PDF。

---

## NG6. 不为每个出版社重写完整 Renderer

产品需要支持不同论文风格，但不应发展成：

```text
ElsevierRenderer
IEEERenderer
SpringerRenderer
ACMRenderer
...
```

完全独立的模板体系。

模板与布局能力应尽可能组合与复用。

---

## NG7. 初版不提供 SemanticDocument 人工编辑

初步产品中 SemanticDocument 属于系统内部文档模型。

用户暂时不能通过 UI：

* Move Paragraph；
* Change Node Type；
* Relink Figure；
* 修改 Reading Order；
* 修改 Semantic Tree。

但内部 Schema、Identity、Provenance 和 Pipeline 应避免阻止未来加入人工修正能力。

---

## 9. 核心用户

当前产品主要面向需要阅读外语学术论文的用户，包括：

* 学生；
* 研究人员；
* 工程师；
* 学术阅读者；
* 需要进行跨语言论文阅读的人。

核心场景是：

> 用户已经拥有一篇 Born-digital PDF 学术论文，希望获得一份高质量、适合目标语言阅读的 PDF，同时能够随时定位原文。

当前产品不是：

* 出版社 DTP 软件；
* OCR 软件；
* PDF 编辑器；
* 通用文档编辑器。

---

## 10. 核心用户流程

用户的主要操作流程为：

```text
选择 PDF
↓
选择目标语言
↓
选择 Translation Provider / Model
↓
分析论文
↓
检查处理状态
↓
翻译
↓
生成 Target PDF
↓
阅读 / 导出
```

内部则表现为：

```text
Import PDF
↓
Analyze PDF
↓
Recover Document Structure
↓
Build Semantic Document
↓
Translate Semantic Content
↓
Generate Render Document
↓
Render Target PDF
↓
Source PDF ↔ Target PDF Interactive Reading
```

Parser、Layout Detection、Semantic Recovery 等复杂过程应尽量隐藏在产品内部。

---

## 11. PDF 输入需求

## FR-PDF-001 PDF 导入

系统必须允许用户导入 Born-digital 学术 PDF。

导入后应建立唯一 Document Identity。

---

## FR-PDF-002 输入能力检测

系统应能够识别当前输入 PDF 是否满足 Initial Product 的基本处理条件。

如果输入明显属于：

* 扫描 PDF；
* 无有效文本层；
* 当前无法可靠解析的文档；

系统应明确告诉用户当前版本不支持，而不是静默产生低质量结果。

---

## FR-PDF-003 页面信息

系统必须保留原 PDF：

* Page Number；
* Page Size；
* Coordinate System；
* 页面元素来源位置。

用于 Source Mapping 与 Viewer 定位。

---

## FR-PDF-004 原始证据不可丢失

结构分析不能覆盖原始解析结果。

即使系统最终认为某个内容是 Paragraph，也应能够追踪这个判断来自哪些原始 PDF 元素。

---

## 12. Reading Order

Reading Order 是系统最核心的能力之一。

## FR-READ-001 多栏阅读顺序

对于常见双栏论文：

```text
LEFT COLUMN        RIGHT COLUMN

A                   D
B                   E
C                   F
```

系统必须能够恢复：

```text
A → B → C → D → E → F
```

不能仅按照全页面坐标排序。

---

## FR-READ-002 跨栏元素

系统必须正确处理：

* 跨栏标题；
* 跨栏 Figure；
* 跨栏 Table；
* Abstract；
* 页面顶部/底部跨栏内容。

跨栏元素不能破坏正文 Reading Flow。

---

## FR-READ-003 Footnote

系统必须区分：

```text
Body Paragraph
```

与：

```text
Footnote
```

脚注不能错误插入正文 Reading Flow。

---

## FR-READ-004 Header / Footer

页眉、页脚、页码等重复页面元素不应被误识别为论文正文。

---

## 13. Semantic Document

PDF 页面布局不能直接成为后续翻译系统的核心数据结构。

系统必须建立独立于 PDF 页面布局的 Semantic Document。

Semantic Document 应表达：

```text
Document
├── Metadata
├── Abstract
├── Section
│   ├── Paragraph
│   ├── Equation
│   ├── Figure
│   └── Table
├── Section
│   └── ...
└── References
```

而不是：

```text
Page
└── Block
    └── Span
```

PDF Page Model 与 Semantic Document Model 必须概念分离。

---

## 14. Paragraph

## FR-PARA-001 Paragraph Recovery

系统必须能够从 PDF 的：

* Line；
* Span；
* Glyph；
* Layout Evidence；

中恢复真正的 Paragraph。

不能简单把：

```text
PDF Text Block
```

等价为：

```text
Semantic Paragraph
```

---

## FR-PARA-002 跨页 Paragraph

一个 Semantic Paragraph 允许跨越多个 PDF 页面。

Source Mapping 因此必须能够对应多个 Source Geometry。

---

## 15. 数学公式

数学公式属于论文内容，而不是普通文字。

系统至少需要区分：

```text
Inline Equation
```

与：

```text
Display Equation
```

---

## FR-EQ-001 公式检测

系统必须能够识别 PDF 中的数学公式区域。

---

## FR-EQ-002 公式语义恢复

系统应尽可能将 PDF 中数学表达恢复为可重新排版的数学表示。

目标不是保留原始 Glyph 的坐标，而是恢复公式本身。

---

## FR-EQ-003 Source Geometry

公式仍必须保留对应原 PDF 的来源 bbox。

---

## FR-EQ-004 公式翻译策略

数学表达本身不得被自然语言翻译模型任意改写。

公式周围的解释文本可以正常翻译。

---

## FR-EQ-005 Equation Number

如原论文存在：

```text
(1)
(2)
(3)
```

等 Equation Number，系统应尽可能保持逻辑编号。

---

## 16. Figure

Figure 必须作为一级语义对象处理。

一个 Figure 至少包含：

```text
Figure
├── Asset
├── Caption
├── Label
├── Source Geometry
└── References
```

---

## FR-FIG-001 Figure Asset

系统必须能够从 PDF 中恢复或裁剪 Figure 资源。

---

## FR-FIG-002 Figure Caption

Caption 必须与 Figure 建立显式关系，而不能仅作为相邻 Paragraph。

---

## FR-FIG-003 Figure Reference

正文中的：

```text
Figure 2
Fig. 3
```

等引用应能够与对应 Figure 建立关系。

---

## FR-FIG-004 Figure Caption Translation

Figure Caption 属于可翻译内容。

---

## FR-FIG-005 Figure Internal Text

Initial Product 中，Figure 图片内部内容保持原样。

包括：

* Axis Label；
* Legend；
* Flowchart Text；
* Diagram Annotation；
* 图片中嵌入的其他文字。

当前不要求：

* OCR；
* Figure 内文字翻译；
* Figure 重绘；
* translated overlay。

即：

```text
Figure Image
→ Preserve Original Asset
```

---

## 17. Table

Table 不能只作为截图处理。

系统需要尽可能恢复 Table 的结构：

```text
Table
├── Rows
├── Columns
├── Cells
├── Caption
├── Label
└── Source Geometry
```

---

## FR-TABLE-001 Table Structure

系统应恢复：

* Row；
* Column；
* Cell；
* Cell Span。

---

## FR-TABLE-002 Table Caption

Table Caption 必须与 Table 显式关联。

---

## FR-TABLE-003 Table Translation

表格中的自然语言内容原则上应翻译。

数值、公式、符号不能因为翻译而错误修改。

---

## FR-TABLE-004 Table Reference

正文中的：

```text
Table 1
Table II
```

等引用应保持与目标表格关联。

---

## 18. Citation 与 References

学术引用属于文档结构。

系统必须区分：

```text
Citation
```

与普通文字中的数字。

---

## FR-CITE-001 Citation

正文 Citation 应尽可能保持原论文引用关系。

---

## FR-CITE-002 Reference Entry

References 中单条文献必须作为独立 Semantic Node。

---

## FR-CITE-003 Citation Linking

如果能够解析：

```text
[12]
```

系统应建立：

```text
Citation → Reference Entry
```

关系。

---

## FR-CITE-004 References Translation

Initial Product 中：

> **References 不翻译。**

例如：

```text
Smith et al. (2024), "Asset Pricing..."
```

应保持原文。

系统不能将论文标题、作者名、期刊名等 Reference Entry 内容自动翻译。

References 可以重新排版，但其内容保持原样。

---

## 19. 翻译需求

翻译必须发生在 Semantic Document 层，而不是 PDF Glyph 层。

---

## FR-TRANS-001 Semantic Translation

翻译输入应以：

* Paragraph；
* Heading；
* Caption；
* Table Cell；
* Footnote；

等语义内容为单位。

---

## FR-TRANS-002 Structure Preservation

翻译不得破坏：

* Section；
* Figure；
* Table；
* Equation；
* Citation；
* Reference；
* Footnote；

之间的结构关系。

---

## FR-TRANS-003 Translation Identity

每个可翻译 Semantic Node 应拥有稳定身份，使：

```text
Source Node
↔
Translated Node
```

关系独立于最终页面布局。

---

## FR-TRANS-004 Translation Re-run

重新翻译某一个 Paragraph 时，不应要求重新解析整篇 PDF。

---

## FR-TRANS-005 Partial Translation

架构上应允许单独重新生成：

* Paragraph；
* Section；
* Caption；
* Table；

而不是只能重新翻译整篇文档。

---

## 20. Translation Provider

Translation Provider 必须是可替换能力。

系统不能将整个翻译 Pipeline 固定绑定在某一个：

* LLM；
* 公司；
* API；
* Model。

概念上应表现为：

```text
Translation Pipeline
        ↓
Translation Provider Interface
        ↓
Provider A / Provider B / Provider C
```

---

## FR-PROVIDER-001 外部服务

Initial Product 允许接入外部 Translation / LLM 服务。

---

## FR-PROVIDER-002 Provider Adapter

不同 Provider 应通过统一的 Provider Adapter 与 Domain 层交互。

---

## FR-PROVIDER-003 Provider Configuration

产品应允许用户配置使用的外部服务所需要的必要信息，例如：

* Endpoint；
* API Key；
* Model；
* 必要 Provider Parameters。

具体 UI 根据开发阶段实现。

---

## FR-PROVIDER-004 Domain Independence

SemanticDocument、TranslationMapping 与 RenderDocument 不得直接绑定某一家 Provider 的 API Response Schema。

---

## 21. Layout Reflow

这是本产品与“PDF 文本覆盖翻译器”的主要区别之一。

翻译以后：

```text
Source Paragraph Length
≠
Target Paragraph Length
```

属于正常情况。

系统必须允许 Renderer 自然重新排版。

---

## FR-LAYOUT-001 Natural Reflow

当内容变长时，系统应允许：

* Paragraph 变高；
* 后续内容向后移动；
* Figure/Table 调整位置；
* Page Break 改变；
* 总页数改变。

---

## FR-LAYOUT-002 不强制保持原页码

例如原文 10 页，译文变为：

```text
11 pages
12 pages
13 pages
```

均属于正常情况。

---

## FR-LAYOUT-003 不要求复杂 Layout Optimizer

当前产品不要求通过复杂 Optimization Algorithm：

> 尽可能把目标元素重新摆回 Source PDF 对应坐标。

正常学术文档排版系统的自然 Reflow 即为期望行为。

---

## 22. Initial Product 的 Target Layout

这是当前阶段已经明确的产品决策。

Initial Product 的目标语言 PDF：

> **默认使用适合译文阅读的单栏布局。**

即使 Source PDF 为：

```text
Two Column
```

Target PDF 也不要求继续保持双栏。

---

## FR-LAYOUT-004 Default Single Column

Initial Product 默认：

```text
Source PDF
Two Column / Single Column / Complex Academic Layout
        ↓
SemanticDocument
        ↓
Target PDF
Readable Single Column Layout
```

单栏译文优先考虑：

* 阅读舒适性；
* 翻译后文本长度变化；
* 数学公式可读性；
* Figure/Table 排版；
* 屏幕阅读体验。

而不是复制 Source Column Layout。

---

## 23. 后续 Layout Profile

完成初步产品后，可以加入用户可选择 Layout Profile 的能力。

目标包括：

```text
Readable Single Column
```

以及：

```text
Inherit Source Layout Characteristics
```

“继承原 PDF”意味着尽可能继承：

* Single / Double Column；
* Paper Size；
* Margin Style；
* Typography Characteristics；
* Heading；
* Caption；
* Equation；
* Reference Style。

仍然不意味着像素级复刻。

---

## 24. Target PDF 内容模式

Initial Product 默认生成：

> **纯目标语言译文 PDF。**

不要求同一 PDF 同时排版原文与译文。

---

## FR-OUTPUT-001 Translation Only

Initial Product：

```text
Target PDF
=
Translated Academic Document
```

其中以下内容例外：

* Figure Asset 保持原图；
* Figure 内文字保持原文；
* References 保持原文；
* 数学表达保持数学语义；
* 不应翻译的专有结构按相应策略保留。

---

## 25. 双语 PDF

双语 PDF 不属于 Initial Product。

完成初步产品后，可以支持：

```text
Bilingual PDF
```

可能的布局包括：

* 原文 / 译文连续排版；
* Paragraph Pair；
* Section Pair；
* 其他双语阅读设计。

具体设计留待后续需求阶段确定。

---

## 26. Renderer

当前第一阶段采用：

> **LaTeX**

作为正式 PDF Rendering Backend。

未来可以加入：

> **Typst**

或其他 Renderer。

用户需求层面对 Renderer 的要求是：

```text
SemanticDocument
↓
Render Model
↓
Renderer Backend
↓
PDF
```

而不是让业务逻辑直接依赖某一个 `.tex` 文件。

---

## FR-RENDER-001 Renderer Independence

Semantic Document 不应直接绑定 LaTeX。

---

## FR-RENDER-002 Style Composition

论文样式应由可组合属性构成，而不是每个 Publisher 完整复制模板。

概念上应表达：

```text
RenderProfile
+
RenderPolicy
+
Backend
```

从而复用：

* Typography；
* Spacing；
* Columns；
* Heading；
* Caption；
* Equation；
* Bibliography。

---

## 27. Source / Target 双向定位

在 Initial Product 中：

* Source PDF 为原论文；
* Target PDF 为纯译文；
* 两者属于不同 PDF。

因此双向定位属于核心产品能力。

---

## FR-SYNC-001 Source → Target

用户在 Source PDF 中选择或双击某个 Paragraph 时，系统应能够定位 Target PDF 中对应 Paragraph。

---

## FR-SYNC-002 Target → Source

用户在 Target PDF 中选择或双击某个 Paragraph 时，系统应能够定位 Source PDF 对应位置。

---

## FR-SYNC-003 Highlight

完成定位后，应高亮对应内容。

---

## FR-SYNC-004 Semantic Mapping

同步关系必须基于：

```text
SemanticNode ID
```

或等价稳定 Identity。

不能依赖：

```text
source page == target page
```

或者：

```text
source bbox ≈ target bbox
```

---

## FR-SYNC-005 Mapping Granularity

当前同步粒度为：

> **Paragraph / SemanticNode Level**

不要求字符级 SyncTeX。

---

## 28. Viewer

Initial Product 的 Viewer 主要承担 Source / Target 联合阅读。

默认概念布局：

```text
┌─────────────────────┬─────────────────────┐
│                     │                     │
│     Source PDF      │     Target PDF      │
│                     │                     │
│                     │                     │
└─────────────────────┴─────────────────────┘
```

用户可以：

```text
Source → Target
Target → Source
```

进行语义导航。

---

## FR-VIEW-001 Dual Document Layout

Initial Product 需要支持 Source PDF 与 Target PDF 联合查看。

---

## FR-VIEW-002 Semantic Navigation

用户应通过 Paragraph / SemanticNode 对应关系完成跳转。

---

## FR-VIEW-003 Mapping Debug

开发阶段应允许查看元素的：

```text
Semantic ID
Source Geometry
Translation Mapping
Render Geometry
```

用于诊断结构恢复问题。

正式用户界面可以隐藏这些信息。

---

## 29. 双语模式后的 Viewer 演进

当未来支持 Bilingual PDF 后：

```text
Original + Translation
```

已经可以存在于同一个 Rendered Document 中。

在这种模式下，不再要求必须采用：

```text
Left Source PDF
+
Right Target PDF
```

的双栏前端 Layout。

Viewer 可以根据 Document Mode 切换。

例如：

```text
Translation-only Mode
→ Source / Target Dual Viewer
```

```text
Bilingual PDF Mode
→ Single Document Viewer
```

因此 Source/Target Side-by-Side Viewer 是 Initial Product 的核心交互，但不应成为 Viewer 架构永久不可替换的唯一 Layout。

---

## 30. Source Mapping

Source Mapping 至少需要表达：

```text
Semantic Node
↓
Source PDF
↓
Page + Geometry
```

一个 Semantic Node 允许拥有：

```text
1 → N
```

个 Source Geometry。

例如跨页 Paragraph。

Target 侧同样可以维护：

```text
Translated Semantic Node
↓
Rendered Geometry
```

但 Source → Target 核心逻辑身份仍然是 Semantic Node，而不是 Geometry Matching。

---

## 31. DocumentBundle

系统应保留能够同时承载 Source 与 Target 的文档级中间层。

其目的包括：

* 双侧文档关联；
* Source Mapping；
* Translation Mapping；
* Schema 演进；
* Renderer 数据交换；
* Viewer 数据交换；
* Pipeline Cache；
* 后续扩展。

DocumentBundle 不属于 UI 概念，而是完整处理结果的逻辑容器。

---

## 32. SemanticDocument 编辑策略

Initial Product 中：

> SemanticDocument 不向最终用户开放直接编辑能力。

这是当前明确产品决定。

但系统内部设计应避免把 SemanticDocument 做成不可演进的临时对象。

未来可以研究加入：

```text
Incorrect Reading Order
→ Correct Order

Wrong Caption Association
→ Relink Figure

Wrong Semantic Type
→ Change Node Type
```

等 Human-in-the-loop 修正能力。

因此当前应：

* 保持 Stable ID；
* 保持 Provenance；
* 保持 Schema Version；
* 避免由 Parser Output 直接充当唯一 Domain Model。

但不需要在 Initial Product 中开发完整 Semantic Editor。

---

## 33. 中间结果与可诊断性

PDF 解析存在天然不确定性。

因此系统不能只输出：

```text
Success
```

或者：

```text
Failure
```

而需要能够表达局部问题，例如：

```text
Equation confidence low
Table structure ambiguous
Caption association uncertain
Reading order conflict
```

单个局部解析问题原则上不应导致整篇论文完全无法处理。

---

## 34. Parser Ensemble 产品约束

产品不要求：

> 每个 Parser 都完整解析整篇论文，然后多数投票。

第三方 Parser 应视为不同类型的 Evidence Provider。

当前已经讨论的职责倾向：

```text
PDFium
→ Physical PDF Backend

MinerU
→ Layout / Formula Evidence

Docling
→ Table Specialist

GROBID
→ Academic Semantics / Citation / Metadata

PyMuPDF
→ Optional Diagnostics / Compatibility
```

最终：

```text
LayoutDocument
SemanticDocument
```

应由本项目自身的数据模型拥有。

第三方 Parser 不得成为内部 Domain Model 的唯一真源。

---

## 35. 核心 Domain Pipeline

当前逻辑处理链为：

```text
PDF
↓
PhysicalDocument
↓
Evidence
↓
LayoutDocument
↓
SemanticDocument
↓
TranslationLayer
↓
RenderDocument
↓
PDF
```

通过：

```text
Mapping
DocumentBundle
```

维护不同阶段之间的关系。

这些模型分别服务于：

| Model            | 用户需求                    |
| ---------------- | ----------------------- |
| PhysicalDocument | 保留 PDF 原始物理证据           |
| Evidence         | 支持多个 Parser 协作          |
| LayoutDocument   | 恢复页面布局关系                |
| SemanticDocument | 恢复论文逻辑结构                |
| TranslationLayer | 保存 Source ↔ Translation |
| Mapping          | 双向定位                    |
| RenderDocument   | 与具体 Renderer 解耦         |
| DocumentBundle   | 管理完整处理结果                |

---

## 36. Parser 错误隔离

第三方 Parser 的失败不能破坏完整 Pipeline。

例如：

```text
Docling Table Parser Failed
```

不应自动意味着：

```text
Entire Document Failed
```

系统应尽可能：

* 降级；
* 保留已有 Evidence；
* 标记 Issue；
* 继续处理其他 Semantic Nodes。

---

## 37. Local Application

Initial Product 的主要运行形态为：

> **Local Application**

核心产品状态优先保存在本地。

包括：

* Imported PDF；
* Parsed Data；
* SemanticDocument；
* DocumentBundle；
* Translation Cache；
* Render Artifacts；
* Mapping；
* Project Metadata。

---

## FR-LOCAL-001 Local Project

用户导入论文后，应可以形成一个可恢复的本地 Project / Document Workspace，而不是一次性转换任务。

---

## FR-LOCAL-002 Pipeline Cache

已完成的解析与中间结果应可以持久化。

用户再次打开论文时，不应每次都重新执行全部 Pipeline。

---

## FR-LOCAL-003 External Translation Exception

Local First 不意味着所有计算都必须离线。

用户选择外部 Translation Provider 后：

```text
Semantic Content
→ External Translation Service
```

属于允许行为。

产品应明确区分：

```text
Local Document Processing
```

与：

```text
External Translation Request
```

---

## 38. Server + Web Client

Server + Web Client 不属于 Initial Product。

完成初步产品后，可以扩展：

```text
Client
↓
Server
↓
Document Processing / Translation / Storage
```

但 Initial Product 的 Domain Model 和 DocumentBundle 不应依赖 Desktop-only 状态。

未来迁移到 Server 时，应尽量复用：

* SemanticDocument；
* Parser Adapter；
* Translation Provider；
* Render Pipeline；
* Mapping；
* Schema。

---

## 39. 非功能需求

## NFR-001 Deterministic Identity

同一个 PDF 的稳定内容应尽可能获得稳定 Semantic Identity。

否则：

* Translation Cache；
* Mapping；
* Incremental Processing；

无法可靠实现。

---

## NFR-002 Provenance

任何经过推断产生的重要 Semantic Object 都应能够追踪来源。

---

## NFR-003 Incremental Processing

修改 Renderer、Translation 或某个后处理步骤时，不应强制重新执行昂贵 PDF Parsing。

---

## NFR-004 Serializable

主要中间模型必须稳定序列化与反序列化。

---

## NFR-005 Versionable

Schema 必须支持版本演进。

历史 DocumentBundle 不应因为 Schema 升级完全不可读取。

---

## NFR-006 Reproducible

相同输入、相同配置、相同 Parser / Model Version 应尽可能产生可复现结果。

---

## NFR-007 Inspectable

Pipeline 每个主要阶段都应该可以独立查看。

开发者必须能够回答：

```text
这个 Paragraph 是怎么来的？
```

而不是只能看到最终 PDF。

---

## NFR-008 Extensible

未来增加：

* 新 Parser；
* 新 Translation Provider；
* 新 Renderer；
* Typst；
* 新 Semantic Node；
* OCR；
* Server；

不应要求重写整个 Pipeline。

---

## 40. Initial Product 验收目标

对于一篇典型 Born-digital 学术论文，用户应能够完成：

```text
导入 PDF
↓
系统自动恢复论文结构
↓
生成 SemanticDocument
↓
通过用户选择的 Translation Provider 完成翻译
↓
生成单栏纯译文 Target PDF
↓
正常阅读论文
↓
点击译文 Paragraph
↓
快速定位 Source PDF Paragraph
↓
点击 Source Paragraph
↓
返回对应译文
```

整个过程中用户无需人工重新整理整篇论文结构。

---

## 41. Golden PDF 验收集

至少建立以下 Golden PDF Cases。

## Case A — 普通单栏论文

验证：

* Paragraph；
* Heading；
* Equation；
* Figure；
* Reference。

---

## Case B — IEEE / Elsevier 类双栏论文

验证：

* Reading Order；
* Column；
* Figure；
* Caption；
* 跨栏元素；
* 最终正确转换为单栏 Target PDF。

---

## Case C — 数学密集型论文

验证：

* Inline Equation；
* Display Equation；
* Equation Number；
* 数学环境。

---

## Case D — Figure / Table 密集型论文

验证：

* Asset；
* Caption；
* Table Structure；
* Cross Reference；
* Figure Asset 保持原样；
* Figure 内部文字不翻译。

---

## Case E — Reference 密集论文

验证：

* Citation；
* Citation → Reference Mapping；
* References 内容保持原文。

---

对于每个 Case，必须同时验证：

```text
PDF Parsing
Semantic Recovery
Translation
Rendering
Source Mapping
Viewer Navigation
```

不能只验证最终 PDF 是否成功生成。

---

## 42. 产品质量优先级

当多个目标产生冲突时，优先级为：

```text
Semantic Correctness
>
Reading Order Correctness
>
Content Fidelity
>
Source Traceability
>
Readable Academic Layout
>
Visual Similarity to Original PDF
```

例如：

如果：

```text
保持原双栏
```

导致目标语言阅读体验明显下降，

Initial Product 应选择：

```text
Readable Single Column
```

如果：

```text
保持原页码
```

导致译文拥挤，

则应允许重新分页。

如果：

```text
完全复制 Publisher Style
```

显著增加 Renderer 复杂度，

则优先使用可组合学术排版体系。

---

## 43. Initial Product 明确决策

截至 v0.2，以下需求已经确定。

| 产品问题                    | Initial Product 决策       |
| ----------------------- | ------------------------ |
| 扫描 PDF                  | 不支持                      |
| Born-digital PDF        | 支持                       |
| Target Layout           | 默认单栏                     |
| 是否继承原双栏                 | 初版不要求                    |
| Target PDF              | 纯译文                      |
| Bilingual PDF           | 后续支持                     |
| Figure Caption          | 翻译                       |
| Figure 内文字              | 不翻译                      |
| Figure Asset            | 保持原图                     |
| Table 内容                | 可翻译                      |
| References              | 不翻译                      |
| Citation Relationship   | 保持                       |
| SemanticDocument 用户编辑   | 初版不支持                    |
| Semantic Edit Extension | 架构预留                     |
| Translation Provider    | Provider Agnostic        |
| 外部 Translation Service  | 支持                       |
| Primary Runtime         | Local                    |
| Server + Web Client     | 后续                       |
| Source / Target Viewer  | 初版双文档联合阅读                |
| Bilingual 模式 Viewer     | 后续可使用单文档模式               |
| Source Mapping          | Paragraph / SemanticNode |
| Character Mapping       | 不要求                      |
| Layout Optimizer        | 不要求                      |
| Renderer                | 初始 LaTeX                 |
| Typst                   | 后续可增加                    |

---

## 44. Post-Initial Product Roadmap

以下能力属于完成初步产品后的候选扩展范围。

注意：

> 本节是 Product Roadmap，不属于当前 Milestone 的强制验收要求。

---

## R1. Scanned PDF / OCR

增加：

```text
Scanned PDF
↓
OCR
↓
Physical Evidence
↓
Semantic Pipeline
```

---

## R2. Layout Profile Selection

允许用户选择：

```text
Readable Single Column
```

或：

```text
Inherit Source Layout
```

---

## R3. Bilingual PDF

支持将：

```text
Source
+
Translation
```

直接排入同一个 PDF。

---

## R4. Viewer Layout Evolution

在 Bilingual PDF 模式下，可以不再使用：

```text
Left Source
+
Right Target
```

Viewer。

---

## R5. SemanticDocument Human Correction

研究用户人工修正：

* Reading Order；
* Semantic Node Type；
* Caption Association；
* Figure/Table Relationship；
* Section Structure。

---

## R6. Figure Internal Translation

研究：

* Figure OCR；
* Axis Label Translation；
* Legend Translation；
* Diagram Text Translation；
* Figure Re-rendering。

当前不承诺实现。

---

## R7. Server + Web Client

将现有 Local Pipeline 扩展为：

```text
Server Processing
+
Web Client
```

---

## R8. Typst Renderer

在 LaTeX Renderer 之外加入 Typst Backend。

---

## 45. 与开发 Milestone 的关系

需求优先于 Milestone。

当前开发方向大体可以映射为：

```text
Milestone 0
Domain / Schema Foundation

Milestone 1
Physical PDF Parsing

Milestone 2
Layout Recovery

Milestone 3
Semantic Recovery

Milestone 4
Equation / Figure / Table / Citation

Milestone 5
Translation Pipeline

Milestone 6
LaTeX Rendering

Milestone 7
Mapping / Viewer

Milestone 8
Product Integration / Quality
```

实际 Milestone 可以根据当前仓库状态调整、拆分或合并。

但不能改变本文档定义的产品行为。

---

## 46. 明确禁止的架构漂移

随着开发推进，项目应避免退化为：

### “高级 OCR”

只恢复文字，没有 SemanticDocument。

### “PDF Translator”

把译文塞回原 bbox。

### “Markdown Converter”

所有论文变成 Markdown，并把 Markdown 当最终产品。

### “Publisher Template Collection”

不断复制：

```text
IEEE.tex
Elsevier.tex
Springer.tex
...
```

### “Parser Wrapper”

内部 Domain Model 完全等同于：

* MinerU；
* Docling；
* GROBID；

某个第三方输出。

### “Coordinate Matching Viewer”

通过 Source Page / Target Page 坐标猜测 Paragraph 对应关系。

### “Provider-specific Translation Application”

整个 Translation Pipeline 直接绑定某一家 LLM API。

### “Desktop-only Domain”

核心 Schema 和 Domain Model 强绑定 Electron / Desktop UI，导致未来无法迁移到 Server。

这些方向均偏离项目核心价值。

---

## 47. 项目核心价值

本项目真正需要建立的不是：

> 一个更好看的 PDF 翻译器。

而是：

> **一个能够把不可编辑的学术 PDF 恢复成具有结构、语义、来源关系和可重新排版能力的中间文档系统，并利用这一中间层完成高质量跨语言学术阅读。**

因此项目最重要的资产不是最终 `.pdf` 文件，而是：

```text
Physical Evidence
↓
SemanticDocument
↓
Source / Translation Mapping
↓
DocumentBundle
```

只要这一层可靠，未来就可以自然扩展：

```text
Translation
LaTeX
Typst
HTML
Web Viewer
Bilingual Reader
Semantic Search
Annotation
LLM Analysis
Reference Navigation
Dataset Export
OCR
Server Processing
```

而无需重新设计整个 PDF 理解系统。

---

## 48. Requirement Change Policy

以后任何新增功能都应首先回答：

> 它解决的是哪个用户问题？

并至少归类为：

```text
Product Requirement
User Experience Requirement
Quality Requirement
Technical Requirement
Implementation Detail
Experiment
```

新的技术组件不应自动成为产品需求。

例如：

```text
“引入新的 Parser”
```

不是用户需求。

真正的需求应类似：

```text
“提升复杂 Table 的结构恢复正确率。”
```

Parser 只是满足这一需求的一种实现。

---

## 49. 文档版本规则

本文档是用户需求的 Source of Truth。

如果未来需求改变，应：

1. 修改本文档；
2. 更新版本号；
3. 在 Git 中提交明确的 Requirements Change；
4. 检查 Architecture / ADR / Milestone 是否受到影响；
5. 必要时同步更新下游开发计划。

Agent 在读取存在冲突的历史需求时：

> **应始终以版本更新、时间更新且明确标记为当前版本的 Product Requirements 为准。**

---

## 50. v0.2 需求变更记录

相对于 v0.1，本版本正式确认：

1. Initial Product 暂不支持扫描 PDF；
2. Initial Product Target PDF 默认采用适合译文阅读的单栏布局；
3. 后续允许用户选择单栏或继承 Source PDF 布局特征；
4. Initial Product Target PDF 默认为纯译文；
5. Bilingual PDF 延后至 Initial Product 完成后；
6. Bilingual PDF 模式下未来无需强制 Source / Target Side-by-Side Viewer；
7. Figure 内部文字 Initial Product 不翻译；
8. Figure Asset 保持原样；
9. References Initial Product 保持原文；
10. SemanticDocument 暂不向用户开放编辑；
11. Semantic Editing 能力在架构上预留；
12. Translation Provider 采用 Provider-Agnostic 设计；
13. 允许接入外部 Translation Service；
14. Initial Product 采用 Local-first 运行模式；
15. Server + Web Client 延后至 Initial Product 完成后。

---

## 51. 最终产品原则

本项目最终遵循：

> **保留语义，而不是像素；保留来源，而不是页码位置；重建论文，而不是复制 PDF 画布。**

对于 Initial Product，还增加一条现实的阶段性原则：

> **先把一篇 Born-digital 学术 PDF 稳定地恢复、翻译、重新排版并建立可追溯关系，再扩展 OCR、双语排版、原布局继承、人工修正与 Server 化。**
