# Master Development Roadmap v0.1

[中文](./roadmap.md) | [English](./roadmap.en.md)

**PDF Paper Semantic Parsing and Translation System**

Status: Master development roadmap after architecture freeze
Scope: From project initialization through core IR, PDF Recovery, Semantic Recovery, Translation, LaTeX Rendering, bidirectional PDF Viewer, to productionization
Audience: Project maintainers, developers, coding agents, reviewers

Authoritative architecture contract: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) (Document Architecture v0.1, frozen).

## Current Progress

**Last updated:** 2026-09-04
**Current position:** M1 complete; entering M2 (Walking Skeleton)

README status: engineering bootstrap plus core document contracts. Product pipelines are not implemented yet.

### Milestone overview

| Milestone | Status | Notes |
| --- | --- | --- |
| M0 Engineering Foundation | Done | Phases 0.1–0.3 complete; Tier 1 corpus established |
| M1 Core Document Contracts | Done | Six schemas at `0.1.0`; generated bindings + cross-language roundtrip |
| M2 Walking Skeleton | Not started | LaTeX smoke and web smoke page exist |
| M3 Layout Recovery Engine | Not started | — |
| M4 Semantic Recovery Engine | Not started | — |
| M5 Translation & Rendering | Not started | — |
| M6 Bidirectional Reader | Not started | — |
| M7 Parser Ensemble & Quality | Not started | — |
| M8 Productionization | Not started | — |

### M0 detail

| Phase | Status | Evidence |
| --- | --- | --- |
| 0.1 Repository Baseline | Done | Monorepo layout, `just` command surface, CI passes on clean checkout |
| 0.2 Architecture Governance | Done | `docs/architecture/`, `docs/contracts/`, `docs/decisions/`, and Agent Note ADRs |
| 0.3 Test Corpus Foundation | Done | 10 Tier 1 LaTeX fixtures + metadata; Tier 4 scanned PDF placeholder |

**M0 exit gate:** Met

### M1 detail

| Phase | Status | Evidence |
| --- | --- | --- |
| 1.1 Identity / Provenance / Resource | Done | `schemas/common/schema.json`; generated Pydantic/TS models; ID uniqueness and provenance tests |
| 1.2 PhysicalDocument Schema | Done | `schemas/physical-document/schema.json`; geometry stability / ID reconciliation tests |
| 1.3 Evidence Schema | Done | `schemas/evidence/schema.json`; FakeMinerU / FakeDocling adapter tests |
| 1.4 LayoutDocument Schema | Done | `schemas/layout-document/schema.json`; two-column + spanning figure + footnote fixture and tests |
| 1.5 SemanticDocument Schema | Done | `schemas/semantic-document/schema.json` (replaces placeholder); structure independence tests |
| 1.6 Mapping Schema | Done | `schemas/mapping/schema.json`; N→1 / 1→N / N→N scenario fixtures and tests |
| 1.7 Schema Generation & Compatibility | Done | `scripts/generate.py`; TS + Pydantic generated bindings; cross-language roundtrip under `tests/integration/` |

**M1 exit gate:** Met (see [`.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.en.md`](../../.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.en.md))

### M2 detail

| Phase | Status | Evidence |
| --- | --- | --- |
| 2.1 Minimal PDF Backend | Not started | No PDFium integration |
| 2.2 Minimal Layout | Not started | No layout recovery implementation |
| 2.3 Minimal Semantic Recovery | Not started | No semantic recovery implementation |
| 2.4 Dummy Translation | Not started | `packages/python/llm` is a stub |
| 2.5 Minimal LaTeX Renderer | Partial | `templates/latex/smoke.tex` + `just latex-smoke` |
| 2.6 Minimal RenderAnchor | Not started | No RenderAnchor extraction |
| 2.7 Minimal Viewer | Partial | `apps/web` smoke page; no bidirectional PDF navigation |

**M2 exit gate:** Not met

### Recommended next steps

1. Enter M2: Walking Skeleton — minimal PDFium backend, minimal layout/semantic recovery, dummy translation, LaTeX renderer, bidirectional navigation

### Maintenance

Update the rows in this section after a phase passes its exit gate review. Do not mark a phase done on merge alone; it must satisfy §5 Definition of Done below.

---

## 1. Document Purpose

This project is not a simple:

```text
PDF → Markdown → LLM → PDF
```

tool.

The system goal is to build a stable, traceable, extensible document processing pipeline:

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

And achieve, through unified Semantic Identity:

```text
Original PDF
      ↕
SemanticDocument
      ↕
Translated PDF
```

This roadmap does not define how any single module is coded. It answers:

1. In what order should the entire project be developed;
2. What problem does each Milestone need to solve;
3. Which Phases does each Milestone contain;
4. What Requirements does each Phase have;
5. What Goal does each Phase achieve;
6. How to determine whether a Phase is complete;
7. When is it allowed to enter the next phase;
8. Which architectural principles must not be broken at any stage.

---

## 2. Overall Development Principles

### 2.1 Compiler Pipeline Principle

The project is always designed as a "document compiler," not a "PDF conversion script":

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

Each layer solves only its own problem.

---

### 2.2 Layer Ownership Principle

Responsibilities are fixed as:

```text
PhysicalDocument
= What objectively exists in the PDF

LayoutDocument
= How the page is visually organized

SemanticDocument
= What the document logic is

RenderDocument
= How target content is actually presented
```

No module may cross layers for development convenience.

For example:

Forbidden:

```text
SemanticParagraph.bbox
SemanticParagraph.page
SemanticParagraph.column
```

Also forbidden:

```text
LayoutRegion.method_section = true
```

---

### 2.3 Evidence Ownership Principle

All third-party tools:

```text
MinerU
Docling
GROBID
PyMuPDF
Future other models
```

may only:

```text
provide evidence
```

They must not own:

```text
LayoutDocument
SemanticDocument
```

Therefore:

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

is a permanent architectural constraint.

---

### 2.4 Semantic Identity Principle

The stable identity across representations is:

```text
SemanticNodeID
```

Not:

```text
page number
bbox
paragraph index
```

All of:

```text
translation
analysis
annotation
render
source anchor
```

are built around SemanticNodeID.

---

### 2.5 Source Layout Is Evidence

The layout of the original PDF:

```text
is evidence for understanding the source document
```

Not:

```text
a hard layout contract for the target PDF
```

The translated PDF is naturally reflowed by LaTeX according to Semantic Reading Flow.

We do not pursue:

```text
source page 5
≈
target page 5
```

We pursue:

```text
source P18
↔
target P18
```

---

### 2.6 Walking Skeleton Principle

The project must not adopt:

```text
Develop all Parsers first
→ Then develop all Semantic
→ Finally run end-to-end for the first time
```

Instead, establish as early as possible a thinnest but complete:

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

Then continuously expand capability.

Any significant architectural design should be validated through a real E2E pipeline as soon as possible.

---

## 3. Milestone Overview

The entire development process is divided into nine main Milestones:

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

Dependencies:

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

Note:

M2 is not a finished system.

The role of M2 is to validate as early as possible:

```text
Whether the architectural loop holds
```

---

## Milestone 0

## Engineering Foundation

Goal:

> Before any core algorithm development, establish a long-term maintainable engineering foundation.

---

### Phase 0.1 Repository Baseline

#### Requirements

Establish a formal monorepo:

```text
apps/
packages/
docs/
examples/
fixtures/
scripts/
.agents/
```

Determine package ownership for:

```text
Python
TypeScript
LaTeX
Future Rust
```

Establish unified:

```text
format
lint
type check
test
build
docs check
```

workflows.

#### Goal

Before any commit enters the main development branch, it can be automatically verified for:

```text
code quality
Schema compatibility
tests
documentation
build
```

#### Validation

Must pass:

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

CI runs successfully on a clean checkout.

---

### Phase 0.2 Architecture Governance

#### Requirements

Establish:

```text
docs/architecture/
docs/decisions/
docs/contracts/
docs/development/
```

Must include at least:

```text
Document Architecture
Layer Responsibility
Parser Adapter Contract
Schema Evolution Policy
Provenance Policy
ID Policy
```

Adopt ADR:

```text
Architecture Decision Record
```

to record important architectural decisions.

#### Goal

Any coding agent or new developer can understand through documentation:

```text
Why the system is designed this way
Which boundaries must not be crossed
```

#### Validation

Randomly select a core module, for example `SemanticDocument`:

After reading only the docs, a developer should be able to answer:

```text
What it can contain
What it cannot contain
Where its input comes from
Who consumes its output
```

---

### Phase 0.3 Test Corpus Foundation

#### Requirements

Create:

```text
fixtures/pdf/
```

The first batch of test papers must cover:

```text
Single column

Standard two-column

Spanning Figure

Table

Equation

Footnote

Bibliography

Cross-page Paragraph

Scanned PDF

Complex Vector Figure
```

Recommend establishing at least:

```text
10–20 small benchmark documents
```

While retaining a small number of manually annotated pages.

#### Goal

The project has a Regression Corpus from day one.

#### Validation

Test files must have:

```text
clear provenance
usage description
expected behavior
```

---

## Milestone 1

## Core Document Contracts

Goal:

> Freeze the project's internal language.

Parsers and renderers can be replaced continuously, but core Document Contracts must remain stable.

---

### Phase 1.1 Identity / Provenance / Resource

#### Requirements

Implement:

```text
NodeID
RegionID
AnchorID
EvidenceID
ResourceID
DocumentID
```

Implement:

```text
ProvenanceRecord
OriginKind
ResourceStore
IssueStore
```

#### Goal

Any subsequent object can:

```text
be uniquely identified
trace provenance
associate resources
report issues
```

#### Validation

Complete:

```text
serialization test
deserialization test
ID uniqueness test
provenance chain test
```

---

### Phase 1.2 PhysicalDocument Schema

#### Requirements

Implement:

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

Unify:

```text
Canonical Page Space
```

#### Goal

Any PDF backend can output the same PhysicalDocument.

#### Validation

Parse the same PDF multiple times:

```text
Page geometry stable
Text coordinates stable
IDs reconcilable
```

---

### Phase 1.3 Evidence Schema

#### Requirements

Implement unified:

```text
Evidence
RegionCandidate
TableCandidate
FormulaCandidate
StructureCandidate
MetadataCandidate
```

#### Goal

Raw schemas from MinerU / Docling / GROBID must not leak into the Recovery Engine.

#### Validation

Write mocks:

```text
FakeMinerUAdapter
FakeDoclingAdapter
```

Prove the Recovery module does not need to know provider-specific schema.

---

### Phase 1.4 LayoutDocument Schema

#### Requirements

Implement:

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

Fully describe:

```text
visual regions
column structure
spanning regions
reading order
```

Without containing paper semantics.

#### Validation

Hand-construct a:

```text
two-column + spanning Figure + Footnote
```

LayoutDocument and successfully serialize it.

---

### Phase 1.5 SemanticDocument Schema

#### Requirements

Implement:

```text
SemanticDocument
SemanticNode
SemanticRelation
RichText
InlineMark
```

First version at minimum:

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

Describe paper logical structure while knowing nothing about page geometry.

#### Validation

Export SemanticDocument independently, delete all PDF information, and still correctly understand article structure.

---

### Phase 1.6 Mapping Schema

#### Requirements

Implement:

```text
PhysicalLayoutBinding

SourceAnchor
SourceSemanticBinding

RenderAnchor
RenderBinding
```

#### Goal

Support:

```text
N Layout → 1 Semantic

1 Layout → N Semantic

N Layout → N Semantic
```

#### Validation

Must cover three fixtures:

```text
spanning-column paragraph

cross-page paragraph

one layout block split into heading + paragraph
```

---

### Phase 1.7 Schema Generation & Compatibility

#### Requirements

Canonical contract uses:

```text
JSON Schema
```

Python:

```text
Pydantic
```

TypeScript:

```text
generated types
```

Future Rust:

```text
serde/generated
```

#### Validation

Establish cross-language roundtrip:

```text
Python serialize
→ JSON
→ TS deserialize
→ JSON
→ Python deserialize
```

Results are semantically consistent.

---

### Milestone 1 Exit Gate

Only enter M2 when all of the following hold:

```text
Core Schema versioned

Schema roundtrip stable

Third-party parser schema does not leak

Physical/Layout/Semantic layer responsibility tests complete

Mapping many-to-many validation complete
```

---

## Milestone 2

## Walking Skeleton

Goal:

> Establish the first real end-to-end loop as soon as possible.

This phase deliberately does not pursue parsing quality.

---

### Phase 2.1 Minimal PDF Backend

#### Requirements

Integrate PDFium.

Implement only:

```text
Page
TextSpan
Page rendering
Basic images
Geometry
```

#### Goal

A real PDF can generate PhysicalDocument.

#### Validation

Select 3 ordinary papers:

```text
page count correct
text largely complete
coordinates correct
```

---

### Phase 2.2 Minimal Layout

#### Requirements

Support only:

```text
TextRegion
Heading-like Region
Figure Region
```

May use simple MinerU Evidence.

No complex fusion yet.

#### Goal

An ordinary two-column page can produce a basic LayoutDocument.

---

### Phase 2.3 Minimal Semantic Recovery

#### Requirements

Support only:

```text
Heading
Paragraph
Figure
FigureCaption
```

#### Goal

Obtain SemanticDocument from a real PDF for the first time.

---

### Phase 2.4 Dummy Translation

#### Requirements

TranslationLayer implements minimal interface.

For example:

```text
[TRANSLATED] original text
```

#### Goal

Verify TranslationLayer and SemanticNode identity are correct.

---

### Phase 2.5 Minimal LaTeX Renderer

#### Requirements

Establish a:

```text
generic-academic
```

template.

Support:

```text
heading
paragraph
figure
caption
```

#### Goal

Generate Target PDF for the first time.

---

### Phase 2.6 Minimal RenderAnchor

#### Requirements

Embed SemanticNode markers in LaTeX.

Recover:

```text
SemanticNode
→ Target PDF region
```

#### Goal

Establish first version of:

```text
SourceAnchor
↔ SemanticNode
↔ RenderAnchor
```

---

### Phase 2.7 Minimal Viewer

#### Requirements

Two PDF Viewers:

```text
Source
Target
```

Click source paragraph:

```text
→ target paragraph
```

Reverse also works.

#### Validation

Complete at least:

```text
Heading bidirectional navigation
Paragraph bidirectional navigation
Figure Caption bidirectional navigation
```

---

### Milestone 2 Exit Gate

Must complete a real:

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

Even if parsing quality is low, end-to-end must hold.

This is the project's first true Architecture Validation.

---

## Milestone 3

## Layout Recovery Engine

Goal:

> Upgrade from "can recover" to "reliably recover page structure."

---

### Phase 3.1 Evidence Normalization

#### Requirements

Implement:

```text
label normalization

coordinate normalization

candidate matching

provider provenance
```

#### Goal

Evidence from different parsers can be uniformly compared.

---

### Phase 3.2 Region Fusion

#### Requirements

Implement:

```text
IoU matching
geometry overlap
text overlap
region type similarity
confidence weighting
```

#### Goal

Converge multiple candidates into Internal LayoutRegion.

#### Validation

Evaluate on manually annotated pages:

```text
Region Recall
Region Precision
```

---

### Phase 3.3 Page Band Detection

#### Requirements

Identify:

```text
full-width

single-column

multi-column

spanning region
```

#### Goal

Support real paper layouts such as:

```text
Title
↓
2 columns
↓
wide Figure
↓
2 columns
```

---

### Phase 3.4 Column Recovery

#### Requirements

Implement:

```text
column clustering
column boundaries
column transitions
```

#### Validation

Benchmark:

```text
1-column
2-column
mixed-band
```

must be stable.

---

### Phase 3.5 ReadingFlowGraph

#### Requirements

Establish:

```text
ReadingEdge
reason
confidence
```

Handle:

```text
same-column

next-column

spanning region

caption

footnote flow
```

#### Goal

Recover reading order without relying on:

```text
sort(y, x)
```

#### Validation

Establish manual reading-order benchmark.

Primary metrics:

```text
pairwise ordering accuracy

sequence accuracy
```

---

### Phase 3.6 Paragraph Continuation Detection

#### Requirements

Handle text continuation after:

```text
column break

page break

figure interruption
```

#### Goal

Layout layer can provide:

```text
continuation evidence
```

to Semantic Recovery.

---

### Phase 3.7 Caption Association

#### Requirements

Recover:

```text
FigureRegion
↔ CaptionLikeRegion

TableRegion
↔ CaptionLikeRegion
```

Based on:

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

Identify:

```text
FootnoteRegion
Footnote flow
Reference evidence
```

Footnotes do not directly pollute main reading flow.

---

### Milestone 3 Exit Gate

At least for the benchmark corpus:

```text
Band Detection stable

Column Detection stable

Reading Order meets target

Caption Association meets target

Cross-page/spanning-column continuation usable
```

And LayoutDocument has no serious structural errors.

---

## Milestone 4

## Semantic Recovery Engine

Goal:

> Truly recover visual structure into paper structure.

---

### Phase 4.1 Paragraph Recovery

#### Requirements

Support:

```text
1 Layout → 1 Paragraph

N Layout → 1 Paragraph

1 Layout → N Semantic
```

#### Goal

Paragraph identity is decoupled from visual blocks.

---

### Phase 4.2 Heading & Section Recovery

#### Requirements

Combine:

```text
font/layout evidence

MinerU

GROBID

numbering pattern
```

To establish:

```text
Heading hierarchy
Section tree
```

#### Validation

Check:

```text
section nesting

heading order

orphan heading
```

---

### Phase 4.3 Figure Recovery

#### Requirements

Semantic Figure:

```text
Figure
Asset
Caption
Subfigure optional
```

Resources support:

```text
PDF fragment
SVG
raster preview
embedded images
```

---

### Phase 4.4 Table Recovery

#### Requirements

Preserve:

```text
Visual Table
+
Structured Table
```

Support:

```text
row
column
cell
rowspan
colspan
```

Structure recognition failure may fallback.

---

### Phase 4.5 Equation Recovery

#### Requirements

Support:

```text
display equation
inline equation

LaTeX candidate
MathML optional
raw glyph
source visual fallback
```

#### Goal

Equation recognition failure must not cause content loss.

---

### Phase 4.6 Footnote Semantic Recovery

Recover:

```text
FootnoteNode

FootnoteReference
↔
Footnote
```

---

### Phase 4.7 Bibliography & Citation

GROBID as primary specialist.

Recover:

```text
BibliographyEntry
CitationMark
CitationRelation
```

#### Validation

Check:

```text
dangling citation
duplicate entry
unresolved reference
```

---

### Phase 4.8 Source Anchoring

During Semantic Recovery, simultaneously generate:

```text
SourceAnchor
SourceSemanticBinding
```

#### Goal

Any major block SemanticNode can return its source region.

---

### Phase 4.9 Semantic Validation

Establish:

```text
SemanticValidator
```

Detect:

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

A standard academic paper must be recoverable as:

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

And generate complete Source Mapping.

---

## Milestone 5

## Translation & Rendering Pipeline

Goal:

> Upgrade from placeholder translation to truly reliable academic paper translation and natural reflow.

---

### Phase 5.1 Structured Translation Protocol

#### Requirements

Translation does not directly receive plain strings.

Protect:

```text
CitationMark

FigureReference

TableReference

EquationReference

InlineEquation
```

#### Goal

RichText semantic marks are not lost after translation.

---

### Phase 5.2 Translation Context

Support:

```text
document metadata

section context

neighbor paragraphs

terminology
```

#### Goal

Avoid each paragraph being translated in complete isolation.

---

### Phase 5.3 Terminology System

Establish:

```text
Term
PreferredTranslation
Source
Confidence
Scope
```

Support in-paper terminology consistency.

---

### Phase 5.4 Translation Cache

Cache key must consider at least:

```text
Node content

target locale

translation model

translation configuration

terminology revision
```

---

### Phase 5.5 RenderProfile

Implement:

```text
generic-academic

source-derived

dense-two-column
```

Add later:

```text
IEEE-like
Elsevier-like
```

---

### Phase 5.6 RenderPolicy

Handle:

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

Render IR:

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

maps to LaTeX.

#### Goal

LaTeX naturally handles:

```text
line breaking
column breaking
page breaking
float placement
```

The system itself does not implement a layout optimizer.

---

### Phase 5.8 RenderAnchor Extraction

After rendering completes, generate:

```text
SemanticNode
→ rendered fragments
```

And cover:

```text
cross-page paragraph

spanning-column paragraph

multi-fragment render
```

---

### Milestone 5 Exit Gate

Must achieve:

```text
real translation
+
complete academic content
+
natural LaTeX reflow
+
RenderAnchor for all major nodes
```

---

## Milestone 6

## Bidirectional Reader

Goal:

> Transform the underlying Document Architecture into a reading experience with real product differentiation.

---

### Phase 6.1 Source Spatial Index

Per page, establish:

```text
geometry
→ SourceAnchor
→ SemanticNode
```

May use R-tree or other spatial index.

---

### Phase 6.2 Target Spatial Index

Establish:

```text
target geometry
→ RenderAnchor
→ SemanticNode
```

---

### Phase 6.3 Bidirectional Navigation

Support:

```text
Source → Target

Target → Source
```

Behavior:

```text
scroll
highlight
focus
```

---

### Phase 6.4 Multi-Fragment Highlight

When one Node corresponds to multiple regions:

```text
highlight all fragments
```

For example, cross-page paragraph.

---

### Phase 6.5 Semantic Inspector

Viewer can display:

```text
SemanticNodeID

Node Kind

Source Anchor

Translation

Relations

Confidence

Provenance
```

As a tool for developers and advanced users.

---

### Phase 6.6 Translation Interaction

Support:

```text
view original text

view translation

re-translate Node

view terminology

view references
```

---

### Milestone 6 Exit Gate

When reading a paper, users can locate original and translated text without relying on:

```text
source page ≈ target page
```

---

## Milestone 7

## Parser Ensemble & Quality System

Goal:

> Upgrade from "functionally complete" to "parsing quality is stable and problems can be measured and fixed."

---

### Phase 7.1 DocumentProbe

Implement lightweight probing:

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

Define clearly:

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

Do not default all documents to:

```text
run everything
```

Based on Probe:

```text
ordinary paper
→ minimum pipeline

complex table
→ enable Docling table

low layout confidence
→ challenger

scanned PDF
→ OCR path
```

---

### Phase 7.4 Conflict Resolution

Simple majority vote is forbidden.

Adopt:

```text
Capability Authority

Confidence

Geometry Consistency

Cross-source Evidence

Internal Rules
```

---

### Phase 7.5 Confidence Calibration

System confidence cannot be merely an arbitrary number.

After establishing benchmark, perform:

```text
confidence calibration
```

So that:

```text
0.9 confidence
```

truly has interpretable meaning.

---

### Phase 7.6 Quality Metrics

Establish long-term dashboard:

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

Any parser/model upgrade must run:

```text
benchmark corpus
```

And report:

```text
improved

unchanged

regressed
```

Forbidden to replace production provider just because:

```text
new version released
```

---

### Milestone 7 Exit Gate

Parser upgrades become:

```text
quantifiable engineering decisions
```

Rather than:

```text
subjective feeling that it works better
```

---

## Milestone 8

## Productionization & Extensibility

Goal:

> Upgrade from a research pipeline to a product system that can be maintained, extended, and deployed long-term.

---

### Phase 8.1 Pipeline Orchestration

Each stage defines explicit Jobs:

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

Allow:

```text
retry
resume
cache
partial rerun
```

---

### Phase 8.2 Incremental Reprocessing

Changing translation:

must not re-run:

```text
PDF parsing
Layout Recovery
Semantic Recovery
```

Changing parser:

must not re-run unrelated rendering config.

Establish dependency graph.

---

### Phase 8.3 Artifact Cache

Cache:

```text
PhysicalDocument

Evidence

LayoutDocument

SemanticDocument

TranslationLayer

RenderDocument

PDF
```

Using content-addressed identity.

---

### Phase 8.4 Failure Isolation

For example:

```text
Table recovery failed
```

must not cause the entire paper to:

```text
parse failed
```

Allow:

```text
issue
+
fallback
+
continue
```

---

### Phase 8.5 Schema Migration

When core Schema has breaking change:

must provide:

```text
migration

compatibility test

migration fixtures
```

Forbidden:

```text
directly modify JSON field
```

causing existing DocumentBundle to become unreadable.

---

### Phase 8.6 Parser Plugin Expansion

Adapters register through unified Capability Contract.

Future additions:

```text
NewLayoutModel

NewFormulaModel

NewOCR

NewTableModel
```

without modifying core IR.

---

### Phase 8.7 Renderer Expansion

Add:

```text
Typst Backend
HTML Backend
```

Must reuse:

```text
SemanticDocument
TranslationLayer
RenderDocument / Render abstraction
```

---

### Phase 8.8 Analysis Layer

Extend only at the end:

```text
summary

RAG

paper QA

concept extraction

contribution

limitations

method explanation
```

These belong to:

```text
AnalysisLayer
```

Never modify Source SemanticDocument.

---

### Milestone 8 Exit Gate

Achieve:

```text
Pipeline recoverable

Tasks rerunnable

Intermediate artifacts cacheable

Schema migratable

Parser replaceable

Renderer extensible

Issues traceable
```

Project enters long-term maintenance phase.

---

## 4. Standard Development Process for Each Phase

All Phases should follow the same process.

---

### Step 1 — Problem Definition

Must first answer:

```text
What problem does this Phase solve?

What is the input?

What is the output?

Who consumes this output?

What problems are explicitly out of scope?
```

---

### Step 2 — Contract First

Write first:

```text
Model

Schema

Protocol

Interface
```

Then write implementation.

Forbidden:

```text
write the algorithm first
then reverse-engineer interface around the implementation
```

---

### Step 3 — Fixtures First

Each core Phase should prepare at least:

```text
normal fixture

edge fixture

failure fixture
```

For example, Reading Order:

```text
simple two-column

spanning figure

footnote + multi-column
```

---

### Step 4 — Minimal Implementation

Implement deterministic baseline first.

For example:

```text
Column Recovery
```

Start with:

```text
geometry clustering
```

Then consider complex models.

Do not introduce in the first version:

```text
LLM
optimizer
complex ML ensemble
```

---

### Step 5 — Observability

Any Recovery Engine must output:

```text
confidence

provenance

reason

issues
```

For example ReadingEdge:

```text
A → B

reason = SAME_COLUMN

confidence = 0.94
```

---

### Step 6 — Unit Validation

Check:

```text
schema

algorithm

edge cases
```

---

### Step 7 — Fixture Validation

Check on benchmark fixtures.

---

### Step 8 — E2E Regression

Before merging any core Phase, ensure:

```text
PDF → Target PDF
```

core Walking Skeleton is not broken.

---

### Step 9 — Documentation

Update:

```text
architecture docs

contract docs

ADR

development notes
```

---

### Step 10 — Exit Review

Confirm:

```text
Requirements complete

Goal achieved

Validation passed

Non-goals not secretly expanded
```

Only then may the Phase be considered complete.

---

## 5. Definition of Done

No Phase should be considered complete just because:

```text
code is written
```

Unified DoD:

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

Benchmark must exist continuously from M0.

Recommended tiers:

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

Tier 4 includes:

```text
broken Unicode mapping

scanned PDF

complex vectors

mixed columns

huge tables

rotated elements

unusual footnotes
```

Any new:

```text
parser
model
layout algorithm
```

must report benchmark delta.

---

## 7. Error Taxonomy

Unified Issue classification for long-term maintenance:

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

Each Issue:

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

Quality priority during development:

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

Especially note:

```text
Pixel similarity
```

is never the highest goal.

---

## 9. Architecture Change Policy

The following changes require an ADR:

```text
Add new core IR layer

Modify SemanticNode identity

Modify Anchor architecture

Modify coordinate system

Modify Schema compatibility policy

Change third-party parser ownership

Introduce new canonical backend

Change Translation identity

Modify Render pipeline
```

Ordinary implementation details do not require an ADR.

---

## 10. Schema Change Policy

Schema changes are classified as:

```text
PATCH
Add optional field / bug fix

MINOR
Add backward-compatible capability

MAJOR
Breaking structural change
```

Any MAJOR:

must have:

```text
migration

fixture

compatibility test

ADR
```

---

## 11. Third-Party Dependency Upgrade Policy

When upgrading MinerU / Docling / GROBID, etc.:

Cannot:

```text
discover new version
→ update dependency
→ merge
```

Must:

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

## 12. Development Priority Principles

When multiple tasks exist simultaneously, prioritize:

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

## 13. Recommended Release Milestones

Development versions can map to:

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

Strict version alignment is not required, but version meaning should correspond to capability maturity, not development time.

---

## 14. Most Important Mid-Term Checkpoints

Four Architecture Reviews are recommended during development.

### Review A — IR Review

Occurs after M1.

Check:

```text
Core Models truly decoupled
Schema stable
Mapping supports many-to-many
```

---

### Review B — Walking Skeleton Review

Occurs after M2.

Check:

```text
End-to-end architecture truly holds

Whether any layer must bypass IR to work
```

If so, fix architecture first.

---

### Review C — Recovery Review

Occurs after M4.

Check:

```text
LayoutDocument truly internal

SemanticDocument truly parser-independent

Source Anchoring complete
```

---

### Review D — Product Architecture Review

Occurs after M6.

Check:

```text
Users can truly read relying on semantic identity

Whether still incorrectly relying on page correspondence
```

---

## 15. Final Mature Form of the Project

The final system should form:

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

## 16. Project Long-Term Iron Rules

If future development scales up, adhering to these principles makes it hard to break the architecture.

First:

```text
Parser output is never our Document Model.
```

Second:

```text
Physical, Layout, Semantic, Render are always layered.
```

Third:

```text
SemanticNodeID is the stable identity across representations.
```

Fourth:

```text
Source geometry and target geometry are always linked through Anchors.
```

Fifth:

```text
Source layout is evidence, not a target rendering contract.
```

Sixth:

```text
Translation / Analysis are Derived Layers; they do not pollute Source SemanticDocument.
```

Seventh:

```text
New parsers integrate into the Evidence Layer first, not by modifying core schema.
```

Eighth:

```text
New renderers reuse Semantic / Render IR, not by re-understanding PDF.
```

Ninth:

```text
Any complex algorithm should have a deterministic baseline first.
```

Tenth:

```text
Before any large-scale vertical development, an end-to-end Walking Skeleton must remain runnable.
```

---

## 17. One-Sentence Development Path

For all subsequent development, always remember:

```text
Freeze the language first
→ Then close the loop
→ Then improve Recovery
→ Then complete Semantic
→ Then improve Translation / Rendering
→ Then complete Reader
→ Finally improve Ensemble, quality, and production capability
```

Rather than:

```text
Keep adding parsers
→ Keep adding AI models
→ Finally try to stitch all outputs together
```

This distinction determines whether the project becomes truly stable Document Infrastructure, or an increasingly hard-to-maintain PDF processing pipeline.
