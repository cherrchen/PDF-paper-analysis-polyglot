# Document Architecture v0.1

[中文](./document-architecture.md) | [English](./document-architecture.en.md)

> **Status:** frozen v0.1。后续 parser、renderer、viewer、translation 均以本文档为契约基准开发。

决策记录：[`.agents/notes/implemented/architecture/2026-09-03-document-architecture.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.md)。

## 1. Architecture Goal

系统采用编译器式文档处理架构：

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
RenderComposer
    ↓
RenderDocument
    ↓
LaTeX Backend
    ↓
Target PDF
```

核心原则：

```text
PhysicalDocument
= PDF 客观存在什么

LayoutDocument
= 页面视觉上如何组织

SemanticDocument
= 文档逻辑上是什么

RenderDocument
= 目标文档实际如何被渲染
```

四个模型彼此独立，不共享具体实现类型。

不同层之间通过 Binding / Anchor 建立映射，而不是通过对象继承或者共用 ID 强绑定。

## 2. DocumentBundle

整个论文处理结果以 `DocumentBundle` 作为聚合根。

```python
class DocumentBundle:
    id: BundleID
    schema_version: str

    source: SourceBundle

    mappings: MappingBundle

    derived: DerivedLayers

    renders: dict[RenderDocumentID, RenderDocument]

    provenance: ProvenanceStore
    issues: IssueStore
```

逻辑结构：

```text
DocumentBundle
│
├── source
│   ├── physical
│   ├── layout
│   └── semantic
│
├── mappings
│   ├── physical_layout
│   ├── source_semantic
│   └── render
│
├── derived
│   ├── translations
│   ├── analyses
│   └── annotations
│
├── renders
│
├── provenance
│
└── issues
```

## 3. PhysicalDocument

### 3.1 职责

PhysicalDocument 只记录 PDF 中可以直接观察到的事实。

禁止引入：

```text
paragraph
section
figure semantics
caption semantics
citation
reading order
```

### 3.2 基本结构

```python
class PhysicalDocument:
    id: PhysicalDocumentID

    pages: list[PhysicalPage]

    objects: dict[PhysicalObjectID, PhysicalObject]

    metadata: PhysicalMetadata
```

Page：

```python
class PhysicalPage:
    id: PageID

    index: int

    geometry: PageGeometry

    object_ids: list[PhysicalObjectID]
```

统一坐标：

```text
Canonical Page Space

origin = top-left
x → right
y ↓

unit = PDF point
```

PageGeometry：

```python
class PageGeometry:
    width_pt: float
    height_pt: float

    rotation: int

    raw_to_canonical: Matrix
    canonical_to_raw: Matrix
```

### 3.3 PhysicalObject

第一版：

```text
TextSpan
ImageObject
VectorObject
LinkObject
```

TextSpan：

```python
class TextSpan:
    id: PhysicalObjectID

    page_id: PageID

    text: str

    geometry: Geometry

    font: FontRef | None
    font_size: float | None

    transform: Matrix | None
```

Geometry：

```python
Geometry =
    Rect
    | Quad
    | Polygon
```

v0.1 主要使用 `Rect`，但 schema 不限制未来更高精度。

## 4. Evidence Model

所有第三方 parser 均不得直接生成 LayoutDocument / SemanticDocument。

它们只能生成 Evidence。

这是整个 parser ensemble 最重要的边界。

```python
class Evidence:
    id: EvidenceID

    provider: str
    provider_version: str

    type: EvidenceType

    confidence: float | None

    provenance_id: ProvenanceID
```

例如：

```python
class RegionCandidate(Evidence):
    page_id: PageID

    geometry: Geometry

    normalized_label: LayoutLabel

    provider_label: str
```

```python
class StructureCandidate(Evidence):
    role: StructureRole
    text_preview: str | None
    page_id: PageID | None
```

MinerU：

```text
display_formula
→ FORMULA
```

Docling：

```text
FORMULA
→ FORMULA
```

进入统一 evidence schema。

## 5. LayoutDocument

### 5.1 职责

LayoutDocument 描述：PDF 页面上的视觉结构是什么。

它允许推断，但只推断视觉关系。

允许：

```text
TextRegion
ImageRegion
TableRegion
FormulaRegion

Column
Band

paragraph-like
heading-like
caption-like

ReadingFlowGraph
```

禁止：

```text
Methods Section
Citation relationship
Bibliography semantics
Translation
```

## 6. Layout Region

```python
class LayoutRegion:
    id: LayoutRegionID

    page_id: PageID

    geometry: Geometry

    kind: LayoutRegionKind

    child_ids: list[LayoutRegionID]

    physical_object_ids: list[PhysicalObjectID]

    labels: list[LayoutLabelCandidate]

    confidence: LayoutConfidence

    provenance_ids: list[ProvenanceID]
```

RegionKind：

```text
TEXT
IMAGE
FIGURE
TABLE
FORMULA

FOOTNOTE
HEADER
FOOTER

UNKNOWN
```

这里 `FIGURE` 表示：视觉上像 Figure Region。而不是 Semantic Figure。

## 7. Layout Grouping

除了 Region，还需要：

```text
PageBand
Column
LayoutGroup
```

PageBand 用于表达：

```text
full-width title
↓
two-column main text
↓
full-width figure
↓
two-column text
```

例如：

```python
class PageBand:
    id: BandID

    page_id: PageID

    y_start: float
    y_end: float

    layout_mode:
        FULL_WIDTH
        SINGLE_COLUMN
        MULTI_COLUMN
        SPANNING

    column_ids: list[ColumnID]
```

LayoutGroup 把应保持在一起的视觉区域成组，但不赋予论文语义：

```python
class LayoutGroup:
    id: LayoutGroupID

    kind:
        FIGURE_BLOCK
        TABLE_BLOCK
        LIST_BLOCK
        FOOTNOTE_BLOCK
        OTHER

    member_ids: list[LayoutRegionID]

    page_id: PageID | None
```

这比给整页定义 `page.columns = 2` 更可靠。

## 8. ReadingFlowGraph

Reading Order 不直接保存成一个简单数组。

```python
class ReadingFlowGraph:
    nodes: list[LayoutRegionID]

    edges: list[ReadingEdge]
```

ReadingEdge：

```python
class ReadingEdge:
    source: LayoutRegionID
    target: LayoutRegionID

    confidence: float

    reason: ReadingOrderReason
```

Reason：

```text
SAME_COLUMN
NEXT_COLUMN

AFTER_SPANNING_BLOCK
BEFORE_SPANNING_BLOCK

CAPTION_ASSOCIATION

CONTINUATION

FOOTNOTE_FLOW
```

最终可以生成：

```python
primary_flow: list[LayoutRegionID]
```

但 Graph 是 source of truth。

## 9. Reading Order Recovery Pipeline

推荐算法：

```text
Layout Regions
    ↓
vertical segmentation
    ↓
Page Bands
    ↓
column clustering
    ↓
spanning region detection
    ↓
local region ordering
    ↓
ReadingFlowGraph
    ↓
linearization
```

脚注不直接插入 primary flow。

例如：

```text
PrimaryFlow
P1 → P2 → P3

FootnoteFlow
FN1 → FN2
```

Semantic Recovery 后再通过 reference relation 连接。

## 10. Formula Recovery

公式处理：

```text
Physical glyph/vector
        +
Visual layout evidence
        ↓
Formula Detection
        ↓
FormulaRegion
        ↓
Formula Recognition
        ↓
EquationCandidate
        ↓
Semantic Equation
```

公式区域 geometry 属于 LayoutDocument。公式语义属于 SemanticDocument。

### 10.1 Formula Representation

```python
class EquationContent:
    latex: str | None
    mathml: str | None
    unicode_text: str | None
    raw_text: str | None

    number: str | None

    preview_asset_id: ResourceID | None
```

LaTeX 不可靠时必须保留 fallback：

```text
original PDF fragment
or
raster/vector preview
```

因此 renderer 永远可以做到：

```text
LaTeX confidence high
→ native equation

otherwise
→ source visual fallback
```

## 11. Figure Recovery

Figure 不等于 PDF ImageObject。

FigureRegion 可能由 images、vectors、paths、text labels 共同组成。

所以 Source Resource 可以保存：

```python
class FigureResource:
    pdf_fragment: ResourceID | None
    svg: ResourceID | None
    raster_preview: ResourceID
    embedded_image_ids: list[ResourceID]
```

优先保留 vector / PDF fragment。Raster 只作为 preview/fallback。

## 12. Table Recovery

Table 必须同时维护 Visual Representation 与 Structured Representation。

Semantic Table：

```python
class TableContent:
    rows: int
    columns: int

    cells: list[TableCell]
```

TableCell：

```python
class TableCell:
    row: int
    column: int

    row_span: int
    col_span: int

    content: RichText
```

同时关联 source visual resource。结构识别失败时，renderer 可以 fallback 到原 visual。

## 13. SemanticDocument

### 13.1 职责

SemanticDocument 表示：如果论文被重新排版，其逻辑结构仍然成立的东西。

禁止保存：

```text
page
bbox
column
font size
page break
PDF object ID
```

### 13.2 顶层结构

```python
class SemanticDocument:
    id: SemanticDocumentID

    schema_version: str

    root_id: NodeID

    nodes: dict[NodeID, SemanticNode]

    relations: list[SemanticRelation]

    provenance_ids: list[ProvenanceID]
```

## 14. SemanticNode

```python
class SemanticNode:
    id: NodeID

    kind: NodeKind

    parent_id: NodeID | None

    children: list[NodeID]

    content: NodeContent

    attributes: dict[str, JsonValue]

    confidence: NodeConfidence

    provenance_ids: list[ProvenanceID]
```

第一版 NodeKind：

```text
DOCUMENT

FRONT_MATTER

SECTION
HEADING

PARAGRAPH

LIST
LIST_ITEM

FIGURE
FIGURE_CAPTION

TABLE
TABLE_CAPTION

EQUATION

FOOTNOTE

BIBLIOGRAPHY

BIBLIOGRAPHY_ENTRY

QUOTE

UNKNOWN
```

## 15. Section 和 Heading

必须独立：

```text
Section
├── Heading
├── Paragraph
└── Section
```

Section 是 logical container。Heading 是 semantic block。

因为 Heading 可以翻译、可以 Anchor、可以点击、可以单独分析。

## 16. RichText

Paragraph 不只是 string。

```python
class RichText:
    text: str

    marks: list[InlineMark]
```

InlineMark 第一版：

```text
BOLD
ITALIC

CITATION

FIGURE_REFERENCE
TABLE_REFERENCE
EQUATION_REFERENCE
SECTION_REFERENCE

INLINE_EQUATION

LINK
SUPERSCRIPT
SUBSCRIPT
```

原则：Block semantics → SemanticNode。Inline semantics → RichText Mark。避免创建大量 TextNode。

## 17. SemanticRelation

树结构只能表达 parent-child。其他关系必须进入 graph：

```python
class SemanticRelation:
    id: RelationID

    type: RelationType

    source: NodeID
    target: NodeID

    confidence: float | None

    provenance_ids: list[ProvenanceID]
```

第一版：

```text
CAPTION_OF

CITES

REFERENCES_FIGURE
REFERENCES_TABLE
REFERENCES_EQUATION
REFERENCES_SECTION

FOOTNOTE_OF
```

## 18. Mapping Architecture

不同 layer 不共享 geometry。通过独立 mapping 连接。

```text
PhysicalDocument
        ↓
PhysicalLayoutBinding
        ↓
LayoutDocument
        ↓
SourceAnchor
        ↓
SourceSemanticBinding
        ↓
SemanticDocument
```

## 19. PhysicalLayoutBinding

```python
class PhysicalLayoutBinding:
    layout_region_id: LayoutRegionID

    physical_object_ids: list[PhysicalObjectID]
```

虽然 LayoutRegion 自己可以缓存 physical refs，但 MappingStore 仍是 authoritative mapping。

## 20. SourceAnchor

Anchor 是独立对象。

```python
class SourceAnchor:
    id: SourceAnchorID

    fragments: list[SourceFragment]

    confidence: float | None

    provenance_ids: list[ProvenanceID]
```

v0.1：

```python
SourceFragment =
    LayoutRegionRef
```

未来允许 PhysicalSpanRef、SentenceRef、CharacterRangeRef、PolygonRef，但 v0.1 不实现字符级 mapping。

## 21. SourceSemanticBinding

```python
class SourceSemanticBinding:
    semantic_node_id: NodeID

    source_anchor_ids: list[SourceAnchorID]
```

必须天然支持 N Layout → 1 Semantic、1 Layout → N Semantic、N Layout → N Semantic。

例如跨栏 paragraph：

```text
Layout B1 ─┐
           ├→ Paragraph P18
Layout B2 ─┘
```

## 22. Provenance

Provenance 必须是一等公民。

```python
class ProvenanceRecord:
    id: ProvenanceID

    producer: str
    producer_version: str

    operation: str

    input_refs: list[str]

    parameters_hash: str | None
```

例如 MinerU 2.x layout region detection、Docling table structure recognition、internal reading flow reconstruction、GROBID citation resolution，全部可追踪。

## 23. Origin Semantics

任何推断结果必须区分：

```text
SOURCE
EXTRACTED
INFERRED
GENERATED
USER
```

尤其必须保证 LLM generated content ≠ paper source content。AnalysisLayer 永远不能污染 SemanticDocument 原文。

## 24. TranslationLayer

翻译不是新的 SemanticDocument。

```python
class TranslationLayer:
    id: TranslationLayerID

    semantic_document_id: SemanticDocumentID
    source_locale: str | None
    target_locale: str

    entries: list[TranslationEntry]

class TranslationEntry:
    semantic_node_id: NodeID

    content: NodeContent

    provenance_ids: list[ProvenanceID]

    confidence: float | None
```

因此：

```text
P18
├── original content
├── zh-CN translation
├── ja-JP translation
└── analysis
```

共享稳定 semantic identity。

`entries` 使用列表承载，但 `semantic_node_id` 在同一 TranslationLayer 内必须唯一；消费者按该字段索引，不能靠数组位置与语义节点对齐。规范契约见 [`schemas/translation-layer/schema.json`](../../schemas/translation-layer/schema.json)。

## 25. Render Architecture

Source Layout 与 Target Layout 是非对称关系。

```text
LayoutDocument
= recovered layout

RenderDocument
= generated layout
```

Target renderer 不需要复刻 source page position。Source Layout 是 evidence，不是 rendering contract。

## 26. RenderComposer

之前的 `LayoutPlanner` 正式改成 `RenderComposer`。

它不是优化器。职责：

```text
SemanticDocument
+
TranslationLayer
+
RenderProfile
+
RenderPolicy

↓

RenderDocument / LaTeX IR
```

## 27. RenderProfile

决定长什么样。

```text
page size
column count
margin

font family
font size
line spacing

heading style
caption style

bibliography style
```

例如 generic-academic、dense-two-column、elsevier-like、ieee-like。出版社 profile 只是 preset，不是 renderer。

## 28. SourceDerivedProfile

优先支持：

```text
LayoutDocument
        ↓
Style Extractor
        ↓
SourceDerivedProfile
```

例如恢复 two-column、A4、approximate margins、serif body、caption size、heading hierarchy。

译文保持 academic visual similarity，而不是 pixel similarity。

## 29. RenderPolicy

决定遇到特殊内容如何排版。

例如 wide figure、wide table、table overflow、long equation、float placement、caption placement。

RenderProfile 与 RenderPolicy 不混合。

## 30. Render IR

```python
class RenderDocument:
    id: RenderDocumentID

    semantic_document_id: SemanticDocumentID
    translation_layer_id: TranslationLayerID | None

    profile: RenderProfile
    policy: RenderPolicy

    blocks: list[RenderBlock]
```

每个 RenderBlock 用 `semantic_node_ids` 保留语义身份；实际目标页坐标由编译后的 RenderAnchor / MappingBundle 记录，而不是内嵌在 RenderDocument。规范契约见 [`schemas/render-document/schema.json`](../../schemas/render-document/schema.json)。

RenderBlock：

```text
RenderHeading

RenderParagraph

RenderFigure
RenderWideFigure

RenderTable
RenderWideTable

RenderEquation

RenderFootnote
```

## 31. LaTeX Backend

LaTeX Backend 只处理 Render IR → LaTeX，而不是 SemanticDocument → publisher-specific LaTeX。

例如：

```text
RenderFigure(span=COLUMN)
↓
\begin{figure}

RenderFigure(span=PAGE)
↓
\begin{figure*}
```

未来 Typst Backend 直接复用 RenderDocument。

## 32. RenderAnchor

LaTeX 自然 reflow 后，再建立实际 geometry。

```python
class RenderAnchor:
    id: RenderAnchorID

    semantic_node_id: NodeID

    fragments: list[RenderFragment]
```

PDF：

```python
class PDFRenderFragment:
    page_index: int
    geometry: Geometry
```

SemanticNode 可以对应多个 fragment，例如 P18 → page 3 bottom、page 4 top，完全合法。

## 33. 双向跳转

Source：

```text
PDF coordinate
↓
Spatial Index
↓
LayoutRegion
↓
SourceAnchor
↓
SemanticNode
```

Target：

```text
SemanticNode
↓
RenderAnchor
↓
Target PDF coordinate
```

反向完全对称。

跳转单位：Heading、Paragraph、Figure、Caption、Table、Equation、Footnote。不以 Section 为主要几何跳转单位。

## 34. Parser Capability Architecture

第三方 parser 通过 Adapter 接入：

```text
parser-adapters/

├── pdfium
├── pymupdf
├── mineru
├── docling
└── grobid
```

但它们没有同等职责。

## 35. Capability Registry

```yaml
physical:
  text:
    primary: pdfium

  geometry:
    primary: pdfium

  graphics:
    primary: pdfium

layout:
  region:
    primary: mineru
    challenger: docling

  reading_order:
    primary: internal

  column_detection:
    primary: internal

table:
  detection:
    primary: mineru
    challenger: docling

  structure:
    primary: docling
    fallback: mineru

formula:
  detection:
    primary: mineru

  recognition:
    primary: mineru

scholarly:
  metadata:
    primary: grobid

  bibliography:
    primary: grobid

  citation:
    primary: grobid

semantic:
  document:
    primary: internal
```

最后一项必须永远成立：`SemanticDocument ownership = internal`。

## 36. PDFium

定位：Canonical Physical Backend。

负责 PDF load、page render、page geometry、text extraction、image/vector object extraction、object bounds。

输出 PhysicalDocument。

## 37. PyMuPDF

定位：Optional Physical Backend、Diagnostic Backend、Validation Backend。

不应该成为 v0.1 必需依赖。主要用于 debug、cross validation、benchmark、fallback experiment。

## 38. MinerU

定位：Primary Scientific Layout Specialist。

负责 Evidence：text regions、formula regions、figure regions、table regions、caption-like、footnote、heading-like，以及 Formula LaTeX candidate。

输出永远是 MinerUEvidence，而不是 LayoutDocument。

## 39. Docling

定位：Layout Challenger、Table Specialist。

尤其负责 table structure、rows、columns、cells、rowspan、colspan。必要时挑战 MinerU 的 layout region classification。

## 40. GROBID

定位：Scholarly Semantic Specialist。

主要 Evidence：title、authors、affiliations、abstract、section structure evidence、bibliography、citation contexts、reference resolution。

它不拥有页面 layout。

## 41. DocumentProbe

不应该每次运行所有 parser。第一阶段运行轻量：

```python
class DocumentProbe:
    native_text_ratio: float

    scanned_page_ratio: float

    math_density: float
    table_density: float
    image_density: float

    estimated_columns: int | None

    layout_complexity: float
```

根据结果动态 route。

## 42. Adaptive Parser Routing

普通 scientific paper：

```text
PDFium
+
MinerU
+
GROBID
```

复杂 table：+ Docling Table。MinerU layout confidence low：+ Docling challenger。扫描 PDF：PDFium render + OCR/Vision path。大量公式：formula specialist pipeline。

不是 every parser always runs。

## 43. Evidence Fusion

禁止简单 majority voting。采用 Capability Ownership + Confidence + Cross-source Evidence + Internal Rules。

例如：

```text
Physical geometry
→ PDFium authority

Table structure
→ Docling authority

Bibliography
→ GROBID authority

Layout region
→ MinerU primary

Reading order
→ internal authority
```

第三方模型是 evidence provider，而不是 document authority。

## 44. Package Architecture

第一版建议：

```text
packages/

├── document-model/
│   ├── physical/
│   ├── layout/
│   ├── semantic/
│   ├── render/
│   ├── mapping/
│   ├── provenance/
│   └── resources/
│
├── pdf-backend/
│   └── pdfium/
│
├── evidence-model/
│
├── parser-adapters/
│   ├── mineru/
│   ├── docling/
│   ├── grobid/
│   └── pymupdf/
│
├── document-probe/
│
├── layout-recovery/
│   ├── bands/
│   ├── columns/
│   ├── reading-order/
│   ├── region-fusion/
│   └── continuations/
│
├── semantic-recovery/
│   ├── sections/
│   ├── paragraphs/
│   ├── figures/
│   ├── tables/
│   ├── equations/
│   ├── citations/
│   └── bibliography/
│
├── translation/
│
├── render-core/
│   ├── composer/
│   ├── profiles/
│   ├── policies/
│   └── anchors/
│
├── latex-renderer/
│
└── typst-renderer/       # future
```

应用：

```text
apps/

├── api/
├── worker/
└── web/
```

## 45. Language Allocation

建议 v0.1：

```text
Python

document model
evidence
parser adapters
layout recovery
semantic recovery
translation
render composer

TypeScript

viewer
annotation UI
original/translated PDF synchronization
document inspector

LaTeX

target PDF rendering
```

Rust v0.1 不强制使用。只有 profiling 明确证明 geometry、spatial index、PDF extraction、graph processing 成为性能瓶颈后，再迁移。

## 46. Schema Compatibility

所有核心 schema：

```text
PhysicalDocument
LayoutDocument
SemanticDocument
RenderDocument
Evidence
Mapping
```

必须 versioned、serializable、language-neutral。

建议 JSON Schema 作为 canonical schema contract。

Python：Pydantic models。TypeScript：generated types。Rust：generated / serde types。

原则：Schema first, Implementation second。

## 47. ID Strategy

所有核心实体使用 opaque persistent IDs。建议 UUIDv7 / ULID。

禁止 `paragraph_1`、`paragraph_2` 作为持久 identity。

另外保存 `source_fingerprint` 用于重新解析时进行 reconciliation。ID 自己不负责语义匹配。

## 48. v0.1 Non-Goals

第一阶段明确不做：

```text
character-level source mapping

pixel-perfect PDF reproduction

publisher submission compatibility

perfect formula reconstruction

perfect table reconstruction

all parsers always running

semantic ontology for:
  theorem
  contribution
  limitation
  dataset
  experiment
```

这些都可以未来扩展。

## 49. v0.1 Required Capabilities

必须完成：

```text
PDF
↓
PhysicalDocument

PhysicalDocument + parser evidence
↓
LayoutDocument

LayoutDocument
↓
SemanticDocument

SemanticDocument
↓
TranslationLayer

SemanticDocument + Translation
↓
LaTeX PDF

Source PDF paragraph
↔
SemanticNode
↔
Translated PDF paragraph
```

至少支持：

```text
single-column paper
two-column paper

heading
paragraph

figure + caption

table + caption

display equation

footnote

bibliography

citation
```

## 50. 最终架构

```text
                              PDF
                               │
                               ▼
                         PDFium Backend
                               │
                               ▼
                       PhysicalDocument
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
             MinerU         Docling         GROBID
                │              │              │
                └─────── Evidence ────────────┘
                               │
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
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
          Translation       Analysis       Annotation
                │
                ▼
          RenderComposer
                │
       ┌────────┴─────────┐
       │                  │
 RenderProfile       RenderPolicy
       │                  │
       └────────┬─────────┘
                ▼
          RenderDocument
                │
                ▼
          LaTeX Backend
                │
                ▼
          Translated PDF
                │
                ▼
          RenderAnchors


Original PDF
     │
SourceAnchor
     │
     ▼
SemanticNode
     │
RenderAnchor
     │
     ▼
Translated PDF
```

## Architecture Principle

整个系统最重要的长期原则：

**Third-party parsers provide evidence; they do not define our document model.**

Physical objects represent what exists, layout objects represent what is visually grouped, semantic nodes represent what the document means, and render objects represent how that meaning is presented.

Source layout is evidence, not a rendering contract.

Semantic identity is the stable bridge between source, translation, analysis, and rendered output.

## 下一步

本文是 `Document Architecture v0.1` 的冻结基准。下一步进入工程化：把设计落成具体 schema 文件与 package API，优先冻结 `PhysicalDocument`、`LayoutDocument`、`SemanticDocument`、`Mapping`、`Evidence` 五套 Pydantic + JSON Schema，再写 parser adapter。
