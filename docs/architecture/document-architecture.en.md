# Document Architecture v0.1

[中文](./document-architecture.md) | [English](./document-architecture.en.md)

> **Status:** frozen v0.1. Parser, renderer, viewer, and translation development use this document as the contract baseline.

Decision record: [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md).

## 1. Architecture Goal

The system uses a compiler-style document processing architecture:

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

Core principles:

```text
PhysicalDocument
= what objectively exists in the PDF

LayoutDocument
= how the page is visually organized

SemanticDocument
= what the document logically is

RenderDocument
= how the target document is actually rendered
```

The four models are independent and do not share concrete implementation types.

Layers connect through Binding / Anchor mappings, not object inheritance or shared IDs.

## 2. DocumentBundle

The full paper processing result uses `DocumentBundle` as the aggregate root.

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

Logical structure:

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

### 3.1 Responsibility

PhysicalDocument records only facts directly observable in the PDF.

Forbidden concepts:

```text
paragraph
section
figure semantics
caption semantics
citation
reading order
```

### 3.2 Basic structure

```python
class PhysicalDocument:
    id: PhysicalDocumentID

    pages: list[PhysicalPage]

    objects: dict[PhysicalObjectID, PhysicalObject]

    metadata: PhysicalMetadata
```

Page:

```python
class PhysicalPage:
    id: PageID

    index: int

    geometry: PageGeometry

    object_ids: list[PhysicalObjectID]
```

Canonical coordinates:

```text
Canonical Page Space

origin = top-left
x → right
y ↓

unit = PDF point
```

PageGeometry:

```python
class PageGeometry:
    width_pt: float
    height_pt: float

    rotation: int

    raw_to_canonical: Matrix
    canonical_to_raw: Matrix
```

### 3.3 PhysicalObject

v0.1 types:

```text
TextSpan
ImageObject
VectorObject
LinkObject
```

TextSpan:

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

Geometry:

```python
Geometry =
    Rect
    | Quad
    | Polygon
```

v0.1 primarily uses `Rect`, but the schema does not limit future higher precision.

## 4. Evidence Model

Third-party parsers must not generate LayoutDocument or SemanticDocument directly.

They may only generate Evidence.

This is the most important boundary in the parser ensemble.

```python
class Evidence:
    id: EvidenceID

    provider: str
    provider_version: str

    type: EvidenceType

    confidence: float | None

    provenance_id: ProvenanceID
```

Example:

```python
class RegionCandidate(Evidence):
    page_id: PageID

    geometry: Geometry

    normalized_label: LayoutLabel

    provider_label: str
```

MinerU:

```text
display_formula
→ FORMULA
```

Docling:

```text
FORMULA
→ FORMULA
```

Both normalize into the unified evidence schema.

## 5. LayoutDocument

### 5.1 Responsibility

LayoutDocument describes the visual structure on PDF pages.

It may infer, but only visual relationships.

Allowed:

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

Forbidden:

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

RegionKind:

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

Here `FIGURE` means a visually figure-like region, not a semantic Figure.

## 7. Layout Grouping

In addition to regions:

```text
PageBand
Column
LayoutGroup
```

PageBand expresses:

```text
full-width title
↓
two-column main text
↓
full-width figure
↓
two-column text
```

Example:

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

This is more reliable than defining `page.columns = 2` for the whole page.

## 8. ReadingFlowGraph

Reading order is not stored as a simple array.

```python
class ReadingFlowGraph:
    nodes: list[LayoutRegionID]

    edges: list[ReadingEdge]
```

ReadingEdge:

```python
class ReadingEdge:
    source: LayoutRegionID
    target: LayoutRegionID

    confidence: float

    reason: ReadingOrderReason
```

Reasons:

```text
SAME_COLUMN
NEXT_COLUMN

AFTER_SPANNING_BLOCK
BEFORE_SPANNING_BLOCK

CAPTION_ASSOCIATION

CONTINUATION

FOOTNOTE_FLOW
```

A derived:

```python
primary_flow: list[LayoutRegionID]
```

may be generated, but the graph is the source of truth.

## 9. Reading Order Recovery Pipeline

Recommended algorithm:

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

Footnotes are not inserted directly into the primary flow.

Example:

```text
PrimaryFlow
P1 → P2 → P3

FootnoteFlow
FN1 → FN2
```

Semantic recovery connects them later through reference relations.

## 10. Formula Recovery

Formula processing:

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

Formula region geometry belongs to LayoutDocument. Formula semantics belong to SemanticDocument.

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

When LaTeX is unreliable, retain fallback:

```text
original PDF fragment
or
raster/vector preview
```

So the renderer can always:

```text
LaTeX confidence high
→ native equation

otherwise
→ source visual fallback
```

## 11. Figure Recovery

Figure is not the same as a PDF ImageObject.

A FigureRegion may combine images, vectors, paths, and text labels.

Source resources may store:

```python
class FigureResource:
    pdf_fragment: ResourceID | None
    svg: ResourceID | None
    raster_preview: ResourceID
    embedded_image_ids: list[ResourceID]
```

Prefer vector / PDF fragment. Raster is preview/fallback only.

## 12. Table Recovery

Tables must maintain both visual representation and structured representation.

Semantic table:

```python
class TableContent:
    rows: int
    columns: int

    cells: list[TableCell]
```

TableCell:

```python
class TableCell:
    row: int
    column: int

    row_span: int
    col_span: int

    content: RichText
```

Also link a source visual resource. When structure recognition fails, the renderer can fall back to the original visual.

## 13. SemanticDocument

### 13.1 Responsibility

SemanticDocument represents what remains valid if the paper is re-typeset.

Forbidden:

```text
page
bbox
column
font size
page break
PDF object ID
```

### 13.2 Top-level structure

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

v0.1 NodeKind:

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

## 15. Section and Heading

These must be separate:

```text
Section
├── Heading
├── Paragraph
└── Section
```

Section is a logical container. Heading is a semantic block.

Because headings can be translated, anchored, clicked, and analyzed independently.

## 16. RichText

A paragraph is not just a string.

```python
class RichText:
    text: str

    marks: list[InlineMark]
```

v0.1 InlineMark:

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

Principle: block semantics → SemanticNode; inline semantics → RichText mark. Avoid creating many TextNodes.

## 17. SemanticRelation

Tree structure only expresses parent-child. Other relations go in a graph:

```python
class SemanticRelation:
    id: RelationID

    type: RelationType

    source: NodeID
    target: NodeID

    confidence: float | None

    provenance_ids: list[ProvenanceID]
```

v0.1 types:

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

Layers do not share geometry. Independent mappings connect them.

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

LayoutRegion may cache physical refs, but MappingStore remains the authoritative mapping.

## 20. SourceAnchor

Anchors are independent objects.

```python
class SourceAnchor:
    id: SourceAnchorID

    fragments: list[SourceFragment]

    confidence: float | None

    provenance_ids: list[ProvenanceID]
```

v0.1:

```python
SourceFragment =
    LayoutRegionRef
```

Future: PhysicalSpanRef, SentenceRef, CharacterRangeRef, PolygonRef. v0.1 does not implement character-level mapping.

## 21. SourceSemanticBinding

```python
class SourceSemanticBinding:
    semantic_node_id: NodeID

    source_anchor_ids: list[SourceAnchorID]
```

Must natively support N Layout → 1 Semantic, 1 Layout → N Semantic, and N Layout → N Semantic.

Example cross-column paragraph:

```text
Layout B1 ─┐
           ├→ Paragraph P18
Layout B2 ─┘
```

## 22. Provenance

Provenance is a first-class citizen.

```python
class ProvenanceRecord:
    id: ProvenanceID

    producer: str
    producer_version: str

    operation: str

    input_refs: list[str]

    parameters_hash: str | None
```

Examples: MinerU 2.x layout region detection, Docling table structure recognition, internal reading flow reconstruction, GROBID citation resolution — all traceable.

## 23. Origin Semantics

Every inferred result must distinguish:

```text
SOURCE
EXTRACTED
INFERRED
GENERATED
USER
```

Especially: LLM generated content ≠ paper source content. AnalysisLayer must never pollute SemanticDocument source text.

## 24. TranslationLayer

Translation is not a new SemanticDocument.

```python
class TranslationLayer:
    id: TranslationLayerID

    locale: str

    entries: dict[NodeID, TranslationEntry]

class TranslationEntry:
    semantic_node_id: NodeID

    content: NodeContent

    provenance_ids: list[ProvenanceID]

    confidence: float | None
```

So:

```text
P18
├── original content
├── zh-CN translation
├── ja-JP translation
└── analysis
```

share stable semantic identity.

## 25. Render Architecture

Source layout and target layout are asymmetric.

```text
LayoutDocument
= recovered layout

RenderDocument
= generated layout
```

The target renderer need not replicate source page positions. Source layout is evidence, not a rendering contract.

## 26. RenderComposer

The former `LayoutPlanner` is renamed `RenderComposer`.

It is not an optimizer. Responsibility:

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

Defines appearance:

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

Examples: generic-academic, dense-two-column, elsevier-like, ieee-like. Publisher profiles are presets, not renderers.

## 28. SourceDerivedProfile

Preferred path:

```text
LayoutDocument
        ↓
Style Extractor
        ↓
SourceDerivedProfile
```

Recover two-column layout, A4, approximate margins, serif body, caption size, heading hierarchy.

Translations preserve academic visual similarity, not pixel similarity.

## 29. RenderPolicy

Defines how special content is typeset: wide figure, wide table, table overflow, long equation, float placement, caption placement.

RenderProfile and RenderPolicy are not mixed.

## 30. Render IR

```python
class RenderDocument:
    id: RenderDocumentID

    profile_id: RenderProfileID

    blocks: list[RenderBlock]

    anchors: dict[NodeID, RenderAnchor]
```

RenderBlock:

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

LaTeX Backend handles only Render IR → LaTeX, not SemanticDocument → publisher-specific LaTeX.

Examples:

```text
RenderFigure(span=COLUMN)
↓
\begin{figure}

RenderFigure(span=PAGE)
↓
\begin{figure*}
```

Future Typst Backend reuses RenderDocument directly.

## 32. RenderAnchor

After LaTeX naturally reflows, establish actual geometry.

```python
class RenderAnchor:
    id: RenderAnchorID

    semantic_node_id: NodeID

    fragments: list[RenderFragment]
```

PDF:

```python
class PDFRenderFragment:
    page_index: int
    geometry: Geometry
```

A SemanticNode may map to multiple fragments, e.g. P18 → page 3 bottom and page 4 top — fully valid.

## 33. Bidirectional navigation

Source:

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

Target:

```text
SemanticNode
↓
RenderAnchor
↓
Target PDF coordinate
```

Fully symmetric in reverse.

Navigation units: Heading, Paragraph, Figure, Caption, Table, Equation, Footnote. Section is not the primary geometric navigation unit.

## 34. Parser Capability Architecture

Third-party parsers connect through adapters:

```text
parser-adapters/

├── pdfium
├── pymupdf
├── mineru
├── docling
└── grobid
```

They do not have equal responsibility.

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

This must always hold: `SemanticDocument ownership = internal`.

## 36. PDFium

Role: Canonical Physical Backend.

Responsibilities: PDF load, page render, page geometry, text extraction, image/vector object extraction, object bounds.

Output: PhysicalDocument.

## 37. PyMuPDF

Role: Optional Physical Backend, Diagnostic Backend, Validation Backend.

Not a v0.1 required dependency. Mainly for debug, cross validation, benchmark, and fallback experiments.

## 38. MinerU

Role: Primary Scientific Layout Specialist.

Evidence: text regions, formula regions, figure regions, table regions, caption-like, footnote, heading-like, and Formula LaTeX candidates.

Output is always MinerUEvidence, never LayoutDocument.

## 39. Docling

Role: Layout Challenger, Table Specialist.

Especially table structure, rows, columns, cells, rowspan, colspan. May challenge MinerU layout region classification when needed.

## 40. GROBID

Role: Scholarly Semantic Specialist.

Evidence: title, authors, affiliations, abstract, section structure evidence, bibliography, citation contexts, reference resolution.

It does not own page layout.

## 41. DocumentProbe

Not every parser should run every time. First stage runs lightweight:

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

Route dynamically from results.

## 42. Adaptive Parser Routing

Typical scientific paper:

```text
PDFium
+
MinerU
+
GROBID
```

Complex tables: + Docling Table. Low MinerU layout confidence: + Docling challenger. Scanned PDF: PDFium render + OCR/Vision path. Heavy math: formula specialist pipeline.

Not every parser always runs.

## 43. Evidence Fusion

No simple majority voting. Use Capability Ownership + Confidence + Cross-source Evidence + Internal Rules.

Examples:

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

Third-party models are evidence providers, not document authorities.

## 44. Package Architecture

v0.1 suggestion:

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

Applications:

```text
apps/

├── api/
├── worker/
└── web/
```

## 45. Language Allocation

v0.1 suggestion:

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

Rust is not required in v0.1. Migrate only when profiling shows geometry, spatial index, PDF extraction, or graph processing as bottlenecks.

## 46. Schema Compatibility

Core schemas:

```text
PhysicalDocument
LayoutDocument
SemanticDocument
RenderDocument
Evidence
Mapping
```

must be versioned, serializable, and language-neutral.

JSON Schema is the suggested canonical contract.

Python: Pydantic models. TypeScript: generated types. Rust: generated / serde types.

Principle: Schema first, Implementation second.

## 47. ID Strategy

All core entities use opaque persistent IDs. Prefer UUIDv7 / ULID.

Forbidden: `paragraph_1`, `paragraph_2` as persistent identity.

Also store `source_fingerprint` for reconciliation on re-parse. IDs do not perform semantic matching.

## 48. v0.1 Non-Goals

Explicitly out of scope for phase one:

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

All may be extended later.

## 49. v0.1 Required Capabilities

Must deliver:

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

Minimum support:

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

## 50. Final architecture

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

The system's most important long-term principle:

**Third-party parsers provide evidence; they do not define our document model.**

Physical objects represent what exists, layout objects represent what is visually grouped, semantic nodes represent what the document means, and render objects represent how that meaning is presented.

Source layout is evidence, not a rendering contract.

Semantic identity is the stable bridge between source, translation, analysis, and rendered output.

## Next steps

This document is the frozen baseline for Document Architecture v0.1. The next engineering step is concrete schema files and package APIs: freeze `PhysicalDocument`, `LayoutDocument`, `SemanticDocument`, `Mapping`, and `Evidence` as Pydantic + JSON Schema first, then write parser adapters.
