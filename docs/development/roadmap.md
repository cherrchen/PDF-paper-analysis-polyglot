# 开发总路线图 v0.1

[中文](./roadmap.md) | [English](./roadmap.en.md)

## PDF 论文语义解析与翻译系统

状态：架构冻结后的开发总路线
适用范围：项目从初始化、核心 IR、PDF Recovery、Semantic Recovery、Translation、LaTeX Rendering、双向 PDF Viewer，直到生产化
目标读者：项目维护者、开发者、Coding Agent、Reviewer

权威架构契约：[`docs/architecture/document-architecture.md`](../architecture/document-architecture.md)（Document Architecture v0.1，已冻结）。

## 当前进度追踪

**最后更新：** 2026-09-04
**当前位置：** M2 已完成；进入 M3（Layout Recovery Engine）

README 状态：工程脚手架 + 核心文档契约 + Walking Skeleton 端到端管线。

### Milestone 总览

| Milestone | 状态 | 说明 |
| --- | --- | --- |
| M0 Engineering Foundation | 已完成 | 0.1–0.3 全部完成；Tier 1 语料已建立 |
| M1 Core Document Contracts | 已完成 | 六套 schema `0.1.0`；生成绑定 + 跨语言 roundtrip |
| M2 Walking Skeleton | 已完成 | PDFium→Physical→Layout→Semantic→Translation→LaTeX→Target PDF→双向导航全链成立 |
| M3 Layout Recovery Engine | 未开始 | — |
| M4 Semantic Recovery Engine | 未开始 | — |
| M5 Translation & Rendering | 未开始 | — |
| M6 Bidirectional Reader | 未开始 | — |
| M7 Parser Ensemble & Quality | 未开始 | — |
| M8 Productionization | 未开始 | — |

### M0 明细

| Phase | 状态 | 证据 |
| --- | --- | --- |
| 0.1 Repository Baseline | 已完成 | monorepo 结构、`just` 命令界面、CI 在 clean checkout 可运行 |
| 0.2 Architecture Governance | 已完成 | `docs/architecture/`、`docs/contracts/`、`docs/decisions/` 与 Agent Note ADR |
| 0.3 Test Corpus Foundation | 已完成 | 10 篇 Tier 1 LaTeX fixture + 元数据；Tier 4 扫描 PDF 占位 |

**M0 Exit Gate：** 已达成

### M1 明细

| Phase | 状态 | 证据 |
| --- | --- | --- |
| 1.1 Identity / Provenance / Resource | 已完成 | `schemas/common/schema.json`；Pydantic/TS 生成模型；ID 唯一性与 provenance 测试 |
| 1.2 PhysicalDocument Schema | 已完成 | `schemas/physical-document/schema.json`；JSON 反序列化后坐标稳定 / ID reconciliation 测试（PDF 重复解析见 M2.1） |
| 1.3 Evidence Schema | 已完成 | `schemas/evidence/schema.json`（含 StructureCandidate）；FakeMinerU / FakeDocling adapter 测试 |
| 1.4 LayoutDocument Schema | 已完成 | `schemas/layout-document/schema.json`（含 LayoutGroup）；双栏 + 跨栏 Figure + Footnote fixture 与测试 |
| 1.5 SemanticDocument Schema | 已完成 | `schemas/semantic-document/schema.json`（RichText + TextNodeContent 别名）；结构独立性测试 |
| 1.6 Mapping Schema | 已完成 | `schemas/mapping/schema.json`；N→1 / 1→N / N→N 与跨页 paragraph fixture 与测试 |
| 1.7 Schema Generation & Compatibility | 已完成 | `scripts/generate.py`；TS + Pydantic 生成物与 JSON Schema 等价约束；`tests/integration/` 跨语言 roundtrip |

**M1 Exit Gate：** 已达成（见 [`.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.md`](../../.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.md)）

### M2 明细

| Phase | 状态 | 证据 |
| --- | --- | --- |
| 2.1 Minimal PDF Backend | 已完成 | `pdf_pipeline.physical`（pypdfium2）；3 篇真实论文验证 + 确定性测试 |
| 2.2 Minimal Layout | 已完成 | `pdf_pipeline.layout`；双栏/单栏真实论文检测 + region/flow 测试 |
| 2.3 Minimal Semantic Recovery | 已完成 | `pdf_pipeline.semantic`；四类节点 + CAPTION_OF；层分离与 bundle 校验全绿 |
| 2.4 Dummy Translation | 已完成 | `paper_llm.translation`；身份保持测试 |
| 2.5 Minimal LaTeX Renderer | 已完成 | `templates/latex/generic-academic.tex` + `pdf_pipeline.render_latex`；编译测试 |
| 2.6 Minimal RenderAnchor | 已完成 | `pdf_pipeline.render_anchor`；hypertarget 恢复 + MappingBundle 校验 |
| 2.7 Minimal Viewer | 已完成 | `apps/web` + pdfjs-dist 双画布；Playwright 映射/加载 e2e |

**M2 Exit Gate：** 已达成（见 [`.agents/notes/implemented/architecture/2026-09-04-m2-walking-skeleton.md`](../../.agents/notes/implemented/architecture/2026-09-04-m2-walking-skeleton.md)）

### 建议下一步

1. 进入 M3：Layout Recovery Engine——真实 band/column 分割、MinerU Evidence 接入、caption/heading 启发式升级

### 维护说明

Phase 完成并经过 Exit Gate 审查后，更新本节的对应行。不要仅因代码合并就标为完成；须满足下文 §5 Definition of Done。

---

## 1. 文档目的

本项目不是一个简单的：

```text
PDF → Markdown → LLM → PDF
```

工具。

系统目标是建立一套稳定、可追踪、可扩展的文档处理流水线：

```text
Source PDF
    ↓
PhysicalDocument
    ↓
Evidence Pipeline
    ↓
LayoutDocument
    ↓
SemanticDocument
    ↓
Derived Layers
    ├── Translation
    ├── Analysis
    └── Annotation
    ↓
RenderDocument
    ↓
LaTeX / Future Typst
    ↓
Translated PDF
```

并通过统一 Semantic Identity 实现：

```text
Original PDF
      ↕
SemanticDocument
      ↕
Translated PDF
```

本路线图的目标不是定义某一个模块如何编码，而是回答：

1. 整个项目应该按照什么顺序开发；
2. 每个 Milestone 需要解决什么问题；
3. 每个 Milestone 内包含哪些 Phase；
4. 每个 Phase 有哪些 Requirement；
5. 每个 Phase 达成什么 Goal；
6. 如何判断 Phase 是否完成；
7. 什么时候允许进入下一阶段；
8. 哪些架构原则任何阶段都不得破坏。

---

## 2. 总体开发原则

### 2.1 Compiler Pipeline Principle

项目始终按照“文档编译器”而不是“PDF 转换脚本”设计：

```text
PDF
 ↓
Physical IR
 ↓
Layout IR
 ↓
Semantic IR
 ↓
Derived IR
 ↓
Render IR
 ↓
PDF / HTML / Future Typst
```

每层只解决自己的问题。

---

### 2.2 Layer Ownership Principle

职责固定为：

```text
PhysicalDocument
= PDF 客观存在什么

LayoutDocument
= 页面视觉如何组织

SemanticDocument
= 文档逻辑是什么

RenderDocument
= 目标内容实际如何呈现
```

任何模块都不得为了开发方便跨层污染。

例如：

禁止：

```text
SemanticParagraph.bbox
SemanticParagraph.page
SemanticParagraph.column
```

也禁止：

```text
LayoutRegion.method_section = true
```

---

### 2.3 Evidence Ownership Principle

所有第三方工具：

```text
MinerU
Docling
GROBID
PyMuPDF
未来其他模型
```

只能：

```text
provide evidence
```

不能拥有：

```text
LayoutDocument
SemanticDocument
```

因此：

```text
Third-party parser output
        ↓
Adapter
        ↓
Evidence
        ↓
Internal Recovery
        ↓
Our Document Model
```

是永久架构约束。

---

### 2.4 Semantic Identity Principle

跨 representation 的稳定身份是：

```text
SemanticNodeID
```

不是：

```text
page number
bbox
paragraph index
```

所有：

```text
translation
analysis
annotation
render
source anchor
```

均围绕 SemanticNodeID 建立。

---

### 2.5 Source Layout Is Evidence

原 PDF 的 layout：

```text
是理解 source document 的证据
```

不是：

```text
target PDF 的硬性排版合同
```

译文 PDF 根据 Semantic Reading Flow 由 LaTeX 自然 reflow。

不追求：

```text
source page 5
≈
target page 5
```

而追求：

```text
source P18
↔
target P18
```

---

### 2.6 Walking Skeleton Principle

项目不得采用：

```text
先开发全部 Parser
→ 再开发全部 Semantic
→ 最后第一次端到端运行
```

而应该尽早建立一条最薄但完整的：

```text
PDF
↓
Physical
↓
Layout
↓
Semantic
↓
Dummy Translation
↓
LaTeX
↓
Translated PDF
↓
Bidirectional Navigation
```

然后不断扩充能力。

任何较大的架构设计都应该尽快通过真实 E2E pipeline 验证。

---

## 3. Milestone 总览

整个开发过程划分为九个主要 Milestone：

```text
M0  Engineering Foundation

M1  Core Document Contracts

M2  Walking Skeleton / End-to-End Prototype

M3  Layout Recovery Engine

M4  Semantic Recovery Engine

M5  Translation & Rendering Pipeline

M6  Bidirectional Reader

M7  Parser Ensemble & Quality System

M8  Productionization & Extensibility
```

依赖关系：

```text
M0
 ↓
M1
 ↓
M2
 ↓
┌───────────────┐
│               │
M3              │
 ↓              │
M4              │
 ↓              │
M5 ←────────────┘
 ↓
M6
 ↓
M7
 ↓
M8
```

注意：

M2 并不是完成版系统。

M2 的作用是尽早验证：

```text
架构闭环是否成立
```

---

## Milestone 0

## Engineering Foundation

目标：

> 在任何核心算法开发之前，建立长期可维护的工程基础。

---

### Phase 0.1 Repository Baseline

#### Requirements

建立正式 monorepo：

```text
apps/
packages/
docs/
examples/
fixtures/
scripts/
.agents/
```

确定：

```text
Python
TypeScript
LaTeX
Future Rust
```

的 package ownership。

建立统一：

```text
format
lint
type check
test
build
docs check
```

流程。

#### Goal

任何提交进入主开发分支前，都可以自动验证：

```text
代码质量
Schema compatibility
测试
文档
构建
```

#### Validation

必须通过：

```text
Python lint
Python type check
Python tests

TS lint
TS type check
TS tests

Schema validation

docs link/check

LaTeX smoke build
```

#### Exit Gate

CI 在 clean checkout 中可以完全成功运行。

---

### Phase 0.2 Architecture Governance

#### Requirements

建立：

```text
docs/architecture/
docs/decisions/
docs/contracts/
docs/development/
```

至少包含：

```text
Document Architecture
Layer Responsibility
Parser Adapter Contract
Schema Evolution Policy
Provenance Policy
ID Policy
```

采用 ADR：

```text
Architecture Decision Record
```

记录重要架构决策。

#### Goal

任何 Coding Agent 或新开发者都可以通过文档理解：

```text
为什么系统这样设计
哪些边界不能突破
```

#### Validation

随机选择一个核心模块，例如 `SemanticDocument`：

开发者只阅读 docs 后，应能够回答：

```text
它能包含什么
不能包含什么
输入来自哪里
输出给谁
```

---

### Phase 0.3 Test Corpus Foundation

#### Requirements

创建：

```text
fixtures/pdf/
```

第一批测试论文必须覆盖：

```text
单栏

普通双栏

跨栏 Figure

Table

Equation

Footnote

Bibliography

跨页 Paragraph

扫描 PDF

复杂 Vector Figure
```

建议至少建立：

```text
10–20 篇小型 benchmark documents
```

同时保留少量人工标注页面。

#### Goal

项目从第一天开始就拥有 Regression Corpus。

#### Validation

测试文件：

```text
有明确来源
有用途说明
有 expected behavior
```

---

## Milestone 1

## Core Document Contracts

目标：

> 冻结项目内部语言。

Parser 和 Renderer 可以不断替换，但核心 Document Contract 必须稳定。

---

### Phase 1.1 Identity / Provenance / Resource

#### Requirements

实现：

```text
NodeID
RegionID
AnchorID
EvidenceID
ResourceID
DocumentID
```

实现：

```text
ProvenanceRecord
OriginKind
ResourceStore
IssueStore
```

#### Goal

任何后续对象都可以：

```text
被唯一识别
追踪来源
关联资源
报告问题
```

#### Validation

完成：

```text
serialization test
deserialization test
ID uniqueness test
provenance chain test
```

---

### Phase 1.2 PhysicalDocument Schema

#### Requirements

实现：

```text
PhysicalDocument
PhysicalPage
TextSpan
ImageObject
VectorObject
LinkObject
PageGeometry
Geometry
```

统一：

```text
Canonical Page Space
```

#### Goal

任何 PDF backend 都可以输出同一种 PhysicalDocument。

#### Validation

M1 验证同一 PhysicalDocument JSON 多次反序列化：

```text
Page geometry stable
Text coordinates stable
IDs reconcilable
```

同一 PDF 字节多次解析属于 M2 Phase 2.1（Physical backend）。

---

### Phase 1.3 Evidence Schema

#### Requirements

实现统一：

```text
Evidence
RegionCandidate
TableCandidate
FormulaCandidate
StructureCandidate
MetadataCandidate
```

#### Goal

MinerU / Docling / GROBID 的原始 schema 不得泄漏到 Recovery Engine。

#### Validation

编写 Mock：

```text
FakeMinerUAdapter
FakeDoclingAdapter
```

证明 Recovery module 不需要知道 provider-specific schema。

---

### Phase 1.4 LayoutDocument Schema

#### Requirements

实现：

```text
LayoutDocument

LayoutPage
LayoutRegion
PageBand
Column
LayoutGroup

ReadingFlowGraph
ReadingEdge
```

#### Goal

能够完整描述：

```text
视觉区域
栏结构
跨栏区域
阅读顺序
```

但不包含论文语义。

#### Validation

手写构造一个：

```text
双栏 + 跨栏 Figure + Footnote
```

LayoutDocument，并成功 serialization。

---

### Phase 1.5 SemanticDocument Schema

#### Requirements

实现：

```text
SemanticDocument
SemanticNode
SemanticRelation
RichText
InlineMark
```

第一版至少：

```text
DOCUMENT
SECTION
HEADING
PARAGRAPH

FIGURE
FIGURE_CAPTION

TABLE
TABLE_CAPTION

EQUATION

FOOTNOTE

BIBLIOGRAPHY_ENTRY
```

#### Goal

能够描述论文逻辑结构而完全不知道页面 geometry。

#### Validation

将 SemanticDocument 独立导出后删除所有 PDF 信息，仍然可以正确理解文章结构。

---

### Phase 1.6 Mapping Schema

#### Requirements

实现：

```text
PhysicalLayoutBinding

SourceAnchor
SourceSemanticBinding

RenderAnchor
RenderBinding
```

#### Goal

支持：

```text
N Layout → 1 Semantic

1 Layout → N Semantic

N Layout → N Semantic
```

#### Validation

必须覆盖：

```text
跨栏 paragraph

跨页 paragraph

一个 layout block 拆 heading + paragraph
```

三个 fixture。

---

### Phase 1.7 Schema Generation & Compatibility

#### Requirements

Canonical contract 使用：

```text
JSON Schema
```

Python：

```text
Pydantic
```

TypeScript：

```text
generated types
```

Future Rust：

```text
serde/generated
```

#### Validation

建立 cross-language roundtrip：

```text
Python serialize
→ JSON
→ TS deserialize
→ JSON
→ Python deserialize
```

结果语义一致。

---

### Milestone 1 Exit Gate

只有下面条件全部成立才进入 M2：

```text
核心 Schema versioned

Schema roundtrip stable

第三方 parser schema 不泄漏

Physical/Layout/Semantic 层职责测试完成

Mapping many-to-many 验证完成
```

---

## Milestone 2

## Walking Skeleton

目标：

> 尽快建立第一条真正的端到端闭环。

这一阶段故意不追求解析质量。

---

### Phase 2.1 Minimal PDF Backend

#### Requirements

接入 PDFium。

仅实现：

```text
Page
TextSpan
Page rendering
Basic images
Geometry
```

#### Goal

真实 PDF 可以生成 PhysicalDocument。

#### Validation

选 3 篇普通论文：

```text
页面数量正确
文本基本完整
坐标正确
```

---

### Phase 2.2 Minimal Layout

#### Requirements

只支持：

```text
TextRegion
Heading-like Region
Figure Region
```

允许使用简单 MinerU Evidence。

暂不做复杂 fusion。

#### Goal

普通双栏页面可以得到基本 LayoutDocument。

---

### Phase 2.3 Minimal Semantic Recovery

#### Requirements

只支持：

```text
Heading
Paragraph
Figure
FigureCaption
```

#### Goal

第一次从真实 PDF 得到 SemanticDocument。

---

### Phase 2.4 Dummy Translation

#### Requirements

TranslationLayer 实现最小接口。

例如：

```text
[TRANSLATED] original text
```

#### Goal

验证 TranslationLayer 与 SemanticNode identity 是否正确。

---

### Phase 2.5 Minimal LaTeX Renderer

#### Requirements

建立一个：

```text
generic-academic
```

模板。

支持：

```text
heading
paragraph
figure
caption
```

#### Goal

第一次生成 Target PDF。

---

### Phase 2.6 Minimal RenderAnchor

#### Requirements

在 LaTeX 中嵌入 SemanticNode marker。

恢复：

```text
SemanticNode
→ Target PDF region
```

#### Goal

建立第一版：

```text
SourceAnchor
↔ SemanticNode
↔ RenderAnchor
```

---

### Phase 2.7 Minimal Viewer

#### Requirements

两个 PDF Viewer：

```text
Source
Target
```

点击 source paragraph：

```text
→ target paragraph
```

反向同样成立。

#### Validation

至少完成：

```text
Heading 双向跳转
Paragraph 双向跳转
Figure Caption 双向跳转
```

---

### Milestone 2 Exit Gate

必须完成真正的：

```text
PDF
↓
Physical
↓
Layout
↓
Semantic
↓
Translation
↓
LaTeX
↓
Target PDF
↓
Bidirectional Navigation
```

哪怕解析质量不高，也必须端到端成立。

这是项目第一次真正 Architecture Validation。

---

## Milestone 3

## Layout Recovery Engine

目标：

> 从“能恢复”提升为“可靠恢复页面结构”。

---

### Phase 3.1 Evidence Normalization

#### Requirements

实现：

```text
label normalization

coordinate normalization

candidate matching

provider provenance
```

#### Goal

不同 parser 的 evidence 可统一比较。

---

### Phase 3.2 Region Fusion

#### Requirements

实现：

```text
IoU matching
geometry overlap
text overlap
region type similarity
confidence weighting
```

#### Goal

将多个 candidate 收敛为 Internal LayoutRegion。

#### Validation

人工标注页面进行：

```text
Region Recall
Region Precision
```

评估。

---

### Phase 3.3 Page Band Detection

#### Requirements

识别：

```text
full-width

single-column

multi-column

spanning region
```

#### Goal

支持：

```text
Title
↓
2 columns
↓
wide Figure
↓
2 columns
```

这种真实论文 layout。

---

### Phase 3.4 Column Recovery

#### Requirements

实现：

```text
column clustering
column boundaries
column transitions
```

#### Validation

Benchmark：

```text
1-column
2-column
mixed-band
```

必须稳定。

---

### Phase 3.5 ReadingFlowGraph

#### Requirements

建立：

```text
ReadingEdge
reason
confidence
```

处理：

```text
same-column

next-column

spanning region

caption

footnote flow
```

#### Goal

不依赖：

```text
sort(y, x)
```

恢复阅读顺序。

#### Validation

建立人工 reading-order benchmark。

主要指标：

```text
pairwise ordering accuracy

sequence accuracy
```

---

### Phase 3.6 Paragraph Continuation Detection

#### Requirements

处理：

```text
column break

page break

figure interruption
```

后的 text continuation。

#### Goal

Layout 层能够提供：

```text
continuation evidence
```

给 Semantic Recovery。

---

### Phase 3.7 Caption Association

#### Requirements

恢复：

```text
FigureRegion
↔ CaptionLikeRegion

TableRegion
↔ CaptionLikeRegion
```

依据：

```text
distance
alignment
font
prefix
region width
```

---

### Phase 3.8 Footnote Recovery

#### Requirements

识别：

```text
FootnoteRegion
Footnote flow
Reference evidence
```

Footnote 不直接污染 main reading flow。

---

### Milestone 3 Exit Gate

至少对 benchmark corpus：

```text
Band Detection 稳定

Column Detection 稳定

Reading Order 达标

Caption Association 达标

跨页/跨栏 continuation 可用
```

并且 LayoutDocument 无严重结构错误。

---

## Milestone 4

## Semantic Recovery Engine

目标：

> 将视觉结构真正恢复成论文结构。

---

### Phase 4.1 Paragraph Recovery

#### Requirements

支持：

```text
1 Layout → 1 Paragraph

N Layout → 1 Paragraph

1 Layout → N Semantic
```

#### Goal

paragraph identity 与视觉 block 解耦。

---

### Phase 4.2 Heading & Section Recovery

#### Requirements

结合：

```text
font/layout evidence

MinerU

GROBID

numbering pattern
```

建立：

```text
Heading hierarchy
Section tree
```

#### Validation

检查：

```text
section nesting

heading order

orphan heading
```

---

### Phase 4.3 Figure Recovery

#### Requirements

Semantic Figure：

```text
Figure
Asset
Caption
Subfigure optional
```

资源支持：

```text
PDF fragment
SVG
raster preview
embedded images
```

---

### Phase 4.4 Table Recovery

#### Requirements

保留：

```text
Visual Table
+
Structured Table
```

支持：

```text
row
column
cell
rowspan
colspan
```

结构识别失败允许 fallback。

---

### Phase 4.5 Equation Recovery

#### Requirements

支持：

```text
display equation
inline equation

LaTeX candidate
MathML optional
raw glyph
source visual fallback
```

#### Goal

公式识别失败不能导致内容丢失。

---

### Phase 4.6 Footnote Semantic Recovery

恢复：

```text
FootnoteNode

FootnoteReference
↔
Footnote
```

---

### Phase 4.7 Bibliography & Citation

GROBID 作为 primary specialist。

恢复：

```text
BibliographyEntry
CitationMark
CitationRelation
```

#### Validation

检查：

```text
dangling citation
duplicate entry
unresolved reference
```

---

### Phase 4.8 Source Anchoring

Semantic Recovery 时同步生成：

```text
SourceAnchor
SourceSemanticBinding
```

#### Goal

任何主要 block SemanticNode 都可以返回 source region。

---

### Phase 4.9 Semantic Validation

建立：

```text
SemanticValidator
```

检测：

```text
orphan node

unbound semantic node

dangling reference

invalid section tree

missing caption target

semantic coverage
```

---

### Milestone 4 Exit Gate

一篇标准 academic paper 必须可以恢复：

```text
Title
Abstract
Sections
Paragraphs
Figures
Tables
Equations
Footnotes
Bibliography
Citations
```

并生成完整 Source Mapping。

---

## Milestone 5

## Translation & Rendering Pipeline

目标：

> 从占位翻译升级成真正可靠的学术论文翻译与自然重排。

---

### Phase 5.1 Structured Translation Protocol

#### Requirements

Translation 不直接接收纯字符串。

保护：

```text
CitationMark

FigureReference

TableReference

EquationReference

InlineEquation
```

#### Goal

翻译后 RichText semantic marks 不丢失。

---

### Phase 5.2 Translation Context

支持：

```text
document metadata

section context

neighbor paragraphs

terminology
```

#### Goal

避免每个 paragraph 完全孤立翻译。

---

### Phase 5.3 Terminology System

建立：

```text
Term
PreferredTranslation
Source
Confidence
Scope
```

支持论文内术语一致性。

---

### Phase 5.4 Translation Cache

cache key 至少考虑：

```text
Node content

target locale

translation model

translation configuration

terminology revision
```

---

### Phase 5.5 RenderProfile

实现：

```text
generic-academic

source-derived

dense-two-column
```

后续才加入：

```text
IEEE-like
Elsevier-like
```

---

### Phase 5.6 RenderPolicy

处理：

```text
wide figure

wide table

table overflow

long equation

caption behavior

float behavior
```

---

### Phase 5.7 LaTeX Backend

Render IR：

```text
Heading

Paragraph

Figure
WideFigure

Table
WideTable

Equation

Footnote

Bibliography
```

映射到 LaTeX。

#### Goal

LaTeX 自然完成：

```text
line breaking
column breaking
page breaking
float placement
```

系统自身不实现 layout optimizer。

---

### Phase 5.8 RenderAnchor Extraction

渲染完成后生成：

```text
SemanticNode
→ rendered fragments
```

并覆盖：

```text
跨页 paragraph

跨栏 paragraph

multi-fragment render
```

---

### Milestone 5 Exit Gate

必须做到：

```text
真实翻译
+
完整 academic content
+
自然 LaTeX reflow
+
所有主要节点 RenderAnchor
```

---

## Milestone 6

## Bidirectional Reader

目标：

> 把底层 Document Architecture 转化成真正具有产品差异化的阅读体验。

---

### Phase 6.1 Source Spatial Index

按页面建立：

```text
geometry
→ SourceAnchor
→ SemanticNode
```

可以使用 R-tree 或其他 spatial index。

---

### Phase 6.2 Target Spatial Index

建立：

```text
target geometry
→ RenderAnchor
→ SemanticNode
```

---

### Phase 6.3 Bidirectional Navigation

支持：

```text
Source → Target

Target → Source
```

行为：

```text
scroll
highlight
focus
```

---

### Phase 6.4 Multi-Fragment Highlight

一个 Node 对应多个 region 时：

```text
highlight all fragments
```

例如跨页 paragraph。

---

### Phase 6.5 Semantic Inspector

Viewer 可展示：

```text
SemanticNodeID

Node Kind

Source Anchor

Translation

Relations

Confidence

Provenance
```

作为开发和高级用户工具。

---

### Phase 6.6 Translation Interaction

支持：

```text
查看原文

查看译文

重新翻译 Node

查看术语

查看引用
```

---

### Milestone 6 Exit Gate

用户阅读论文时可以完全不依赖：

```text
source page ≈ target page
```

完成原文与译文定位。

---

## Milestone 7

## Parser Ensemble & Quality System

目标：

> 从“功能完整”升级成“解析质量稳定、问题可以度量和修复”。

---

### Phase 7.1 DocumentProbe

实现轻量探测：

```text
native text ratio

scan ratio

math density

table density

image density

layout complexity

estimated columns
```

---

### Phase 7.2 Capability Registry

明确：

```text
physical.text
→ PDFium

layout.region
→ MinerU

layout.challenge
→ Docling

table.structure
→ Docling

formula
→ MinerU

bibliography
→ GROBID

reading_order
→ Internal
```

---

### Phase 7.3 Adaptive Routing

不允许所有文档默认：

```text
run everything
```

根据 Probe：

```text
普通论文
→ minimum pipeline

复杂 table
→ enable Docling table

低 layout confidence
→ challenger

扫描 PDF
→ OCR path
```

---

### Phase 7.4 Conflict Resolution

禁止简单 majority vote。

采用：

```text
Capability Authority

Confidence

Geometry Consistency

Cross-source Evidence

Internal Rules
```

---

### Phase 7.5 Confidence Calibration

系统 confidence 不能只是 arbitrary number。

建立 benchmark 后做：

```text
confidence calibration
```

使：

```text
0.9 confidence
```

真正具有可解释意义。

---

### Phase 7.6 Quality Metrics

建立长期 dashboard：

```text
Physical text coverage

Layout region recall

Reading order accuracy

Paragraph recovery accuracy

Section hierarchy accuracy

Table structure accuracy

Formula recovery accuracy

Citation resolution rate

Source mapping coverage

Render mapping coverage
```

---

### Phase 7.7 Regression Benchmark

任何 parser/model 升级必须运行：

```text
benchmark corpus
```

报告：

```text
improved

unchanged

regressed
```

禁止只因为：

```text
新版本发布
```

就直接替换 production provider。

---

### Milestone 7 Exit Gate

Parser 升级开始变成：

```text
可量化工程决策
```

而不是：

```text
主观觉得效果更好
```

---

## Milestone 8

## Productionization & Extensibility

目标：

> 从研究型 pipeline 升级成可以长期维护、扩展和部署的产品系统。

---

### Phase 8.1 Pipeline Orchestration

每个阶段定义明确 Job：

```text
INGEST

PHYSICAL

EVIDENCE

LAYOUT

SEMANTIC

TRANSLATE

RENDER

INDEX
```

允许：

```text
retry
resume
cache
partial rerun
```

---

### Phase 8.2 Incremental Reprocessing

修改 translation：

不应重新运行：

```text
PDF parsing
Layout Recovery
Semantic Recovery
```

修改 parser：

不应重新运行不相关 rendering config。

建立 dependency graph。

---

### Phase 8.3 Artifact Cache

缓存：

```text
PhysicalDocument

Evidence

LayoutDocument

SemanticDocument

TranslationLayer

RenderDocument

PDF
```

使用 content-addressed identity。

---

### Phase 8.4 Failure Isolation

例如：

```text
Table recovery failed
```

不能导致整个论文：

```text
parse failed
```

允许：

```text
issue
+
fallback
+
continue
```

---

### Phase 8.5 Schema Migration

核心 Schema 发生 breaking change：

必须提供：

```text
migration

compatibility test

migration fixtures
```

禁止：

```text
直接修改 JSON field
```

导致已有 DocumentBundle 无法读取。

---

### Phase 8.6 Parser Plugin Expansion

Adapter 通过统一 Capability Contract 注册。

未来新增：

```text
NewLayoutModel

NewFormulaModel

NewOCR

NewTableModel
```

不修改核心 IR。

---

### Phase 8.7 Renderer Expansion

增加：

```text
Typst Backend
HTML Backend
```

必须复用：

```text
SemanticDocument
TranslationLayer
RenderDocument / Render abstraction
```

---

### Phase 8.8 Analysis Layer

最后才扩展：

```text
summary

RAG

paper QA

concept extraction

contribution

limitations

method explanation
```

这些属于：

```text
AnalysisLayer
```

绝不修改 Source SemanticDocument。

---

### Milestone 8 Exit Gate

达到：

```text
Pipeline 可恢复

任务可重跑

中间产物可缓存

Schema 可迁移

Parser 可替换

Renderer 可扩展

问题可追踪
```

项目进入长期维护阶段。

---

## 4. 每个 Phase 的标准开发流程

所有 Phase 都应遵循同样流程。

---

### Step 1 — Problem Definition

必须先回答：

```text
这个 Phase 解决什么问题？

输入是什么？

输出是什么？

谁消费这个输出？

哪些问题明确不解决？
```

---

### Step 2 — Contract First

先写：

```text
Model

Schema

Protocol

Interface
```

再写实现。

禁止：

```text
先把算法写出来
再围绕实现反推 interface
```

---

### Step 3 — Fixtures First

每个核心 Phase 至少先准备：

```text
normal fixture

edge fixture

failure fixture
```

例如 Reading Order：

```text
simple two-column

spanning figure

footnote + multi-column
```

---

### Step 4 — Minimal Implementation

先实现 deterministic baseline。

例如：

```text
Column Recovery
```

先做：

```text
geometry clustering
```

再考虑复杂模型。

不要第一版直接引入：

```text
LLM
optimizer
复杂 ML ensemble
```

---

### Step 5 — Observability

任何 Recovery Engine 都必须输出：

```text
confidence

provenance

reason

issues
```

例如 ReadingEdge：

```text
A → B

reason = SAME_COLUMN

confidence = 0.94
```

---

### Step 6 — Unit Validation

检查：

```text
schema

algorithm

edge cases
```

---

### Step 7 — Fixture Validation

在 benchmark fixture 上检查。

---

### Step 8 — E2E Regression

任何核心 Phase 合并前，都必须确保：

```text
PDF → Target PDF
```

核心 Walking Skeleton 不被破坏。

---

### Step 9 — Documentation

更新：

```text
architecture docs

contract docs

ADR

development notes
```

---

### Step 10 — Exit Review

确认：

```text
Requirements 完成

Goal 达成

Validation 通过

Non-goals 没有偷偷扩张
```

才允许 Phase 完成。

---

## 5. Definition of Done

任何 Phase 不应该因为：

```text
代码写完了
```

就被认为完成。

统一 DoD：

```text
Implementation complete

Tests complete

Fixtures complete

Validation metrics available

Errors observable

Provenance available where relevant

Docs updated

CI green

E2E regression green

No unresolved architecture violation
```

---

## 6. Benchmark Policy

Benchmark 必须从 M0 开始持续存在。

建议分层：

```text
Tier 1
Synthetic / manually crafted

Tier 2
Simple academic papers

Tier 3
Complex real-world academic papers

Tier 4
Pathological PDFs
```

Tier 4 包括：

```text
broken Unicode mapping

scanned PDF

complex vectors

mixed columns

huge tables

rotated elements

unusual footnotes
```

任何新的：

```text
parser
model
layout algorithm
```

都必须报告 benchmark delta。

---

## 7. Error Taxonomy

长期维护中统一 Issue 分类：

```text
PHYSICAL_EXTRACTION

LAYOUT_REGION

READING_ORDER

PARAGRAPH_BOUNDARY

SECTION_STRUCTURE

FIGURE_RECOVERY

TABLE_RECOVERY

FORMULA_RECOVERY

CITATION_RESOLUTION

SOURCE_MAPPING

TRANSLATION

RENDERING

RENDER_MAPPING
```

每个 Issue：

```text
severity

affected IDs

producer

message

recoverable

fallback
```

---

## 8. Quality Priority

项目开发时质量优先级：

```text
1. Content completeness

2. Semantic correctness

3. Reading order correctness

4. Source/target mapping correctness

5. Equation/Table/Figure fidelity

6. Translation quality

7. Visual similarity

8. Pixel similarity
```

尤其注意：

```text
Pixel similarity
```

永远不是最高目标。

---

## 9. Architecture Change Policy

以下修改必须写 ADR：

```text
新增核心 IR layer

修改 SemanticNode identity

修改 Anchor 架构

修改坐标系统

修改 Schema compatibility policy

更改 third-party parser ownership

引入新的 canonical backend

更改 Translation identity

修改 Render pipeline
```

普通 implementation detail 不需要 ADR。

---

## 10. Schema Change Policy

Schema 修改分为：

```text
PATCH
添加 optional field / bug fix

MINOR
添加 backward-compatible capability

MAJOR
breaking structural change
```

任何 MAJOR：

必须：

```text
migration

fixture

compatibility test

ADR
```

---

## 11. 第三方依赖升级政策

MinerU / Docling / GROBID 等升级时：

不能：

```text
发现新版本
→ 更新 dependency
→ merge
```

必须：

```text
Upgrade branch

↓
Adapter compatibility

↓
Benchmark

↓
Regression report

↓
Decision
```

---

## 12. 开发优先级原则

如果同时存在多个任务，优先：

```text
P0
Pipeline correctness / data loss

P1
Semantic or mapping correctness

P2
Layout recovery quality

P3
Translation/rendering quality

P4
Performance

P5
Visual polish
```

---

## 13. 推荐 Release 里程碑

开发版本可以映射：

```text
0.1.x
M0–M2
Walking Skeleton

0.2.x
M3
Layout Recovery

0.3.x
M4
Semantic Recovery

0.4.x
M5
Translation + Rendering

0.5.x
M6
Bidirectional Reader

0.6.x
M7
Quality / Ensemble

0.7.x+
M8
Productionization
```

不要求严格按照这个版本号，但建议版本意义对应 capability maturity，而不是开发时间。

---

## 14. 最重要的中期检查点

项目开发过程中建议设置四个 Architecture Review。

### Review A — IR Review

发生在 M1 后。

检查：

```text
核心 Models 是否真正解耦
Schema 是否稳定
Mapping 是否支持 many-to-many
```

---

### Review B — Walking Skeleton Review

发生在 M2 后。

检查：

```text
端到端架构是否真实成立

是否存在某个层必须绕过 IR 才能工作
```

如果存在，应优先修架构。

---

### Review C — Recovery Review

发生在 M4 后。

检查：

```text
LayoutDocument 是否真正属于内部

SemanticDocument 是否真正 parser-independent

Source Anchoring 是否完整
```

---

### Review D — Product Architecture Review

发生在 M6 后。

检查：

```text
用户是否真的可以依靠 semantic identity 阅读

是否仍然错误依赖 page correspondence
```

---

## 15. 项目最终成熟形态

最终系统应该形成：

```text
                       Source PDF
                           │
                           ▼
                    PhysicalDocument
                           │
                           ▼
                    Evidence Pipeline
             ┌─────────────┼─────────────┐
             │             │             │
          MinerU        Docling        GROBID
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    Layout Recovery
                           │
                           ▼
                     LayoutDocument
                           │
                           ▼
                   Semantic Recovery
                           │
                           ▼
                    SemanticDocument
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
     Translation       Analysis        Annotation
          │
          ▼
     RenderComposer
          │
          ▼
     RenderDocument
          │
     ┌────┴─────┐
     ▼          ▼
   LaTeX       Typst
     │
     ▼
Translated PDF


Original PDF
     │
SourceAnchor
     ▼
SemanticNode
     ▲
RenderAnchor
     │
Translated PDF
```

---

## 16. 项目长期铁律

如果未来开发规模扩大，只需要坚持下面这些原则，就不容易把架构做坏。

第一：

```text
Parser 输出永远不是我们的 Document Model。
```

第二：

```text
Physical、Layout、Semantic、Render 永远分层。
```

第三：

```text
SemanticNodeID 是跨 representation 的稳定身份。
```

第四：

```text
Source geometry 与 target geometry 永远通过 Anchor 关联。
```

第五：

```text
Source layout 是 evidence，不是 target rendering contract。
```

第六：

```text
Translation / Analysis 是 Derived Layer，不污染 Source SemanticDocument。
```

第七：

```text
新 parser 优先接入 Evidence Layer，而不是修改核心 schema。
```

第八：

```text
新 renderer 复用 Semantic / Render IR，而不是重新理解 PDF。
```

第九：

```text
任何复杂算法之前都应该存在 deterministic baseline。
```

第十：

```text
任何大规模纵向开发之前，都必须保持一条端到端 Walking Skeleton 可以运行。
```

---

## 17. 一句话开发路线

整个项目后续开发可以始终记住：

```text
先冻结语言
→ 再打通闭环
→ 再提升 Recovery
→ 再完善 Semantic
→ 再提升 Translation / Rendering
→ 再完成 Reader
→ 最后提升 Ensemble、质量和生产能力
```

而不是：

```text
不断增加 parser
→ 不断增加 AI model
→ 最后尝试把所有输出拼起来
```

这个区别决定了项目最后会成为一个真正稳定的 Document Infrastructure，还是一个越来越难维护的 PDF processing pipeline。
