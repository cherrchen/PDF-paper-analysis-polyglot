# PDF Paper Semantic Analysis, Translation, and Reflow Tool — Product Requirements Document

[中文](./requirements.md) | [English](./requirements.en.md)

> Document Type: Product / User Requirements
> Status: Draft v0.2
> Supersedes: v0.1
> Scope: Product Requirements Source of Truth
> Language: en

---

## 1. Document Purpose

This document defines the problems this project must solve for end users, core usage scenarios, functional requirements, interaction requirements, quality requirements, product boundaries, phased scope, and acceptance criteria.

This document answers:

> **“What should this product do for users?”**

Not:

> “Which Parser, Schema, framework, algorithm, or language should be used for implementation?”

The following project documents must treat this document as an upstream requirements constraint:

* Architecture;
* Schema;
* ADR;
* Implementation Plan;
* Milestone;
* Phase Plan.

When a technical approach conflicts with the product requirements in this document, the technical approach should be re-examined first—not the product requirements silently revised.

---

## 2. Product Definition

This project is a processing system for academic papers:

```text
PDF
↓
Structure and Semantic Recovery
↓
Semantic Document
↓
Translation
↓
Academic Document Reflow
↓
Target PDF
```

The product’s core goal is not simply extracting text from a PDF, nor overlaying translated text directly on the original PDF pages. Rather:

> **Recover the reading structure, semantic structure, formulas, tables, figures, citation relationships, and source locations from the PDF, and on that basis generate a structurally correct, re-typesettable, traceable target-language paper that can establish semantic correspondence with the original PDF.**

What end users see should not be a collection of isolated text blocks, but a paper that can still be read normally as an academic article.

---

## 3. Product Background

Traditional PDF translation typically uses one of the following approaches:

1. Extract PDF text and output plain text or Markdown;
2. Replace text directly within the original PDF bounding boxes;
3. OCR and reassemble by page coordinates;
4. Convert PDF to HTML and typeset in a browser;
5. Translate each text block individually and overlay it back onto the original page.

These approaches have clear problems for academic papers.

Because text length differs across languages, simple bbox replacement often causes:

* Text overflow;
* Forced font-size reduction;
* Abnormal line spacing;
* Multi-column misalignment;
* Figures/Tables overlapping body text;
* Incorrect footnote placement;
* Page layouts that become increasingly hard to maintain.

On the other hand, if paper structure is abandoned entirely and only Markdown is produced, a great deal of information contained in the PDF is lost, for example:

* Heading hierarchy;
* Authors and affiliations;
* Two-column reading order;
* Mathematical formulas;
* Figures;
* Tables;
* Captions;
* Footnotes;
* Citations;
* References;
* Section hierarchy;
* Page source locations.

Therefore, this project adopts a different product approach:

> **Do not replicate the pixel layout of the PDF; recover the paper’s semantic structure and reading flow, then regenerate the target-language academic document.**

---

## 4. Product Core Principles

This project follows three core principles:

> **Preserve semantics, not pixels.**

Preserve semantics, not pixels.

> **Preserve provenance, not page positions.**

Preserve provenance, not page positions.

> **Reconstruct the paper, not the PDF canvas.**

Reconstruct the paper, not the PDF canvas.

---

## 5. Product Goals

### G1. Recover the Paper, Not Just the Text

The system must understand which content in a PDF belongs to:

* Title;
* Author;
* Affiliation;
* Abstract;
* Section;
* Subsection;
* Paragraph;
* Equation;
* Figure;
* Table;
* Caption;
* Footnote;
* Citation;
* References;
* Other necessary academic document structures.

Users should ultimately receive a target-language document with normal paper structure.

---

### G2. Preserve Traceable Source Provenance

Major semantic units in the target-language document must be traceable back to the original PDF.

Users should be able to know:

> “Which passage in the original PDF does this translated passage correspond to?”

And:

> “Which translated passage corresponds to this passage in the original PDF?”

This relationship must not break because of repagination or re-typesetting.

---

### G3. Handle Language-Length Changes Correctly

Text-length changes caused by translation must be resolved through normal document reflow—not through:

* Forcibly constraining text box size;
* Extreme font shrinking;
* Overlapping adjacent content;
* Forcing preservation of source PDF page numbers.

The target-language paper may be repaginated.

---

### G4. Preserve the Academic Reading Experience

The generated target-language PDF should still read like a formal paper—not:

* A web screenshot;
* A Markdown printout;
* An OCR text dump;
* A PDF assembled from many text boxes.

It must preserve as far as possible:

* Clear structural hierarchy;
* Correct Figures/Tables;
* Mathematical formulas;
* Captions;
* Citations;
* References;
* Normal pagination;
* Academic typesetting.

---

### G5. Support Joint Reading of Source and Translation

In the initial product, the Target PDF contains only the translation by default.

Therefore, when reading the translation, users still need to consult the Source PDF at any time.

The product must support rapid bidirectional semantic positioning between:

```text
Source PDF ↔ Target PDF
```

---

### G6. Local First

The initial product runs primarily as a local application.

PDF:

* Parsing;
* Intermediate structures;
* Cache;
* Rendering;
* Project state;

are in principle all managed by the local application.

Translation services may be invoked through external Providers.

Later expansion to:

```text
Server + Web Client
```

is planned.

---

## 6. Current-Phase Product Scope

This document divides requirements into:

```text
Initial Product
```

and:

```text
Post-Initial Product
```

The Initial Product is the primary target of current development work.

---

## 7. Initial Product Definition

The first usable product must at minimum satisfy:

```text
Born-digital Academic PDF
        ↓
Structure Recovery
        ↓
SemanticDocument
        ↓
External Translation Provider
        ↓
Single-Column Translation-Only PDF
        ↓
Source / Target Dual-Panel Viewer
        ↓
Paragraph / SemanticNode Bidirectional Positioning
```

Currently confirmed:

* Scanned PDFs are not supported;
* Target PDF defaults to single column;
* Target PDF defaults to translation-only;
* Text inside Figure images is not translated;
* References are not translated;
* SemanticDocument is not user-editable for now;
* Translation Provider is replaceable;
* The product runs locally.

---

## 8. Non-Goals

### NG1. Initial Version Does Not Support Scanned PDFs

The first formal release only requires support for:

> **Born-digital PDF**

That is, PDFs with a normal digital text layer, font information, and page object structure.

The following are not part of the Initial Product:

* Scanned papers;
* Image-only PDFs;
* Full-document OCR;
* OCR Reading Order Recovery.

Scanned PDF support is a future extension capability.

---

### NG2. No Pixel-Level Replication of the Original PDF

The Target PDF does not need to satisfy:

```text
Source Element Coordinates
=
Target Element Coordinates
```

A passage on page 4 of the source may perfectly well appear on page 5 of the target document after translation.

---

### NG3. No Requirement for One-to-One Source Page ↔ Target Page Mapping

Pagination is a Renderer outcome, not document semantics.

Therefore:

```text
Source Page 5
↓
Target Page 5
```

is not a core relationship the system must maintain.

What must be maintained is:

```text
Source Semantic Node
↕
Translated Semantic Node
```

---

### NG4. No Character-Level Source Mapping

The current product only requires stable mapping at least at:

> **Paragraph / SemanticNode Level**

It does not require:

```text
source character 125
↔
translated character 218
```

Nor word-level alignment.

---

### NG5. Markdown Is Not the Final Product Form

Markdown may serve as:

* Debug output;
* Intermediate representation;
* Development aid;
* Optional export format.

But Markdown must not replace the formal target-language PDF.

---

### NG6. No Separate Renderer per Publisher

The product must support different paper styles, but should not evolve into a set of fully independent template systems such as:

```text
ElsevierRenderer
IEEERenderer
SpringerRenderer
ACMRenderer
...
```

Template and layout capabilities should be composable and reusable as far as possible.

---

### NG7. Initial Version Does Not Provide SemanticDocument Manual Editing

In the initial product, SemanticDocument is an internal system document model.

Users cannot currently use the UI to:

* Move Paragraph;
* Change Node Type;
* Relink Figure;
* Modify Reading Order;
* Modify the Semantic Tree.

But internal Schema, Identity, Provenance, and Pipeline design must not prevent future human-correction capabilities.

---

## 9. Core Users

The product primarily serves users who need to read academic papers in foreign languages, including:

* Students;
* Researchers;
* Engineers;
* Academic readers;
* Anyone who needs cross-language paper reading.

The core scenario is:

> The user already has a born-digital PDF academic paper and wants a high-quality PDF suited for reading in the target language, while being able to locate the original at any time.

The product is not currently:

* Publisher DTP software;
* OCR software;
* A PDF editor;
* A general-purpose document editor.

---

## 10. Core User Flow

The user’s primary workflow is:

```text
Select PDF
↓
Select target language
↓
Select Translation Provider / Model
↓
Analyze paper
↓
Check processing status
↓
Translate
↓
Generate Target PDF
↓
Read / Export
```

Internally this appears as:

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

Complex processes such as Parser, Layout Detection, and Semantic Recovery should be hidden inside the product as far as possible.

---

## 11. PDF Input Requirements

### FR-PDF-001 PDF Import

The system must allow users to import born-digital academic PDFs.

After import, a unique Document Identity must be established.

---

### FR-PDF-002 Input Capability Detection

The system should be able to determine whether the input PDF satisfies the basic processing conditions of the Initial Product.

If the input clearly belongs to:

* Scanned PDF;
* No valid text layer;
* A document that cannot currently be parsed reliably;

the system should clearly tell the user that the current version does not support it, rather than silently producing low-quality results.

---

### FR-PDF-003 Page Information

The system must preserve from the original PDF:

* Page Number;
* Page Size;
* Coordinate System;
* Source locations of page elements.

This information is used for Source Mapping and Viewer positioning.

---

### FR-PDF-004 Raw Evidence Must Not Be Lost

Structural analysis must not overwrite raw parsing results.

Even if the system ultimately classifies content as a Paragraph, it must still be able to trace which raw PDF elements that judgment came from.

---

## 12. Reading Order

Reading Order is one of the system’s most critical capabilities.

### FR-READ-001 Multi-Column Reading Order

For common two-column papers:

```text
LEFT COLUMN        RIGHT COLUMN

A                   D
B                   E
C                   F
```

The system must recover:

```text
A → B → C → D → E → F
```

It cannot rely only on full-page coordinate sorting.

---

### FR-READ-002 Cross-Column Elements

The system must correctly handle:

* Cross-column headings;
* Cross-column Figures;
* Cross-column Tables;
* Abstract;
* Cross-column content at the top/bottom of a page.

Cross-column elements must not break body reading flow.

---

### FR-READ-003 Footnote

The system must distinguish:

```text
Body Paragraph
```

from:

```text
Footnote
```

Footnotes must not be incorrectly inserted into the body Reading Flow.

---

### FR-READ-004 Header / Footer

Repeated page elements such as headers, footers, and page numbers must not be misidentified as paper body text.

---

## 13. Semantic Document

PDF page layout cannot directly become the core data structure of the downstream translation system.

The system must establish a Semantic Document independent of PDF page layout.

A Semantic Document should express:

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

Not:

```text
Page
└── Block
    └── Span
```

The PDF Page Model and Semantic Document Model must be conceptually separate.

---

## 14. Paragraph

### FR-PARA-001 Paragraph Recovery

The system must recover true Paragraphs from PDF:

* Line;
* Span;
* Glyph;
* Layout Evidence.

It cannot simply equate:

```text
PDF Text Block
```

with:

```text
Semantic Paragraph
```

---

### FR-PARA-002 Cross-Page Paragraph

A semantic Paragraph may span multiple PDF pages.

Source Mapping must therefore be able to correspond to multiple Source Geometries.

---

## 15. Mathematical Formulas

Mathematical formulas are paper content, not ordinary text.

The system must at minimum distinguish:

```text
Inline Equation
```

from:

```text
Display Equation
```

---

### FR-EQ-001 Equation Detection

The system must be able to identify mathematical formula regions in the PDF.

---

### FR-EQ-002 Equation Semantic Recovery

The system should recover mathematical expressions in the PDF into re-typesettable mathematical representations as far as possible.

The goal is not to preserve original glyph coordinates, but to recover the formula itself.

---

### FR-EQ-003 Source Geometry

Formulas must still retain the source bbox corresponding to the original PDF.

---

### FR-EQ-004 Equation Translation Strategy

Mathematical expressions themselves must not be arbitrarily rewritten by natural-language translation models.

Explanatory text around formulas may be translated normally.

---

### FR-EQ-005 Equation Number

If the original paper has Equation Numbers such as:

```text
(1)
(2)
(3)
```

the system should preserve their logical numbering as far as possible.

---

## 16. Figure

A Figure must be treated as a first-class semantic object.

A Figure contains at minimum:

```text
Figure
├── Asset
├── Caption
├── Label
├── Source Geometry
└── References
```

---

### FR-FIG-001 Figure Asset

The system must be able to recover or crop Figure assets from the PDF.

---

### FR-FIG-002 Figure Caption

The Caption must have an explicit relationship to the Figure—not merely be treated as an adjacent Paragraph.

---

### FR-FIG-003 Figure Reference

References in body text such as:

```text
Figure 2
Fig. 3
```

must be able to link to the corresponding Figure.

---

### FR-FIG-004 Figure Caption Translation

Figure Captions are translatable content.

---

### FR-FIG-005 Figure Internal Text

In the Initial Product, content inside Figure images remains unchanged.

Including:

* Axis Label;
* Legend;
* Flowchart Text;
* Diagram Annotation;
* Other text embedded in the image.

Currently not required:

* OCR;
* Translation of text inside Figures;
* Figure redrawing;
* Translated overlay.

That is:

```text
Figure Image
→ Preserve Original Asset
```

---

## 17. Table

A Table cannot be handled only as a screenshot.

The system must recover Table structure as far as possible:

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

### FR-TABLE-001 Table Structure

The system should recover:

* Row;
* Column;
* Cell;
* Cell Span.

---

### FR-TABLE-002 Table Caption

The Table Caption must be explicitly associated with the Table.

---

### FR-TABLE-003 Table Translation

Natural-language content in tables should in principle be translated.

Numerical values, formulas, and symbols must not be incorrectly modified during translation.

---

### FR-TABLE-004 Table Reference

References in body text such as:

```text
Table 1
Table II
```

must remain linked to the target table.

---

## 18. Citation and References

Academic citations are part of document structure.

The system must distinguish:

```text
Citation
```

from numbers in ordinary text.

---

### FR-CITE-001 Citation

Body Citations should preserve the original paper’s citation relationships as far as possible.

---

### FR-CITE-002 Reference Entry

Each entry in References must be an independent Semantic Node.

---

### FR-CITE-003 Citation Linking

If it can be parsed:

```text
[12]
```

the system should establish:

```text
Citation → Reference Entry
```

relationship.

---

### FR-CITE-004 References Translation

In the Initial Product:

> **References are not translated.**

For example:

```text
Smith et al. (2024), "Asset Pricing..."
```

should remain in the original language.

The system must not automatically translate paper titles, author names, journal names, or other Reference Entry content.

References may be re-typeset, but their content remains unchanged.

---

## 19. Translation Requirements

Translation must occur at the Semantic Document layer, not the PDF Glyph layer.

---

### FR-TRANS-001 Semantic Translation

Translation input should be in units of semantic content such as:

* Paragraph;
* Heading;
* Caption;
* Table Cell;
* Footnote.

---

### FR-TRANS-002 Structure Preservation

Translation must not break structural relationships among:

* Section;
* Figure;
* Table;
* Equation;
* Citation;
* Reference;
* Footnote.

---

### FR-TRANS-003 Translation Identity

Each translatable Semantic Node should have a stable identity so that:

```text
Source Node
↔
Translated Node
```

relationship can exist independently of final page layout.

---

### FR-TRANS-004 Translation Re-run

Re-translating a single Paragraph must not require re-parsing the entire PDF.

---

### FR-TRANS-005 Partial Translation

The architecture should allow regenerating individually:

* Paragraph;
* Section;
* Caption;
* Table;

rather than only re-translating the entire document.

---

## 20. Translation Provider

Translation Provider must be a replaceable capability.

The system cannot bind the entire translation Pipeline to a single:

* LLM;
* Company;
* API;
* Model.

Conceptually it should appear as:

```text
Translation Pipeline
        ↓
Translation Provider Interface
        ↓
Provider A / Provider B / Provider C
```

---

### FR-PROVIDER-001 External Services

The Initial Product allows integration with external Translation / LLM services.

---

### FR-PROVIDER-002 Provider Adapter

Different Providers should interact with the Domain layer through a unified Provider Adapter.

---

### FR-PROVIDER-003 Provider Configuration

The product should allow users to configure the information required by external services, for example:

* Endpoint;
* API Key;
* Model;
* Necessary Provider Parameters.

The specific UI depends on implementation stage.

---

### FR-PROVIDER-004 Domain Independence

SemanticDocument, TranslationMapping, and RenderDocument must not be directly bound to any single Provider’s API Response Schema.

---

## 21. Layout Reflow

This is one of the main differences between this product and a “PDF text-overlay translator.”

After translation:

```text
Source Paragraph Length
≠
Target Paragraph Length
```

is normal.

The system must allow the Renderer to reflow naturally.

---

### FR-LAYOUT-001 Natural Reflow

When content grows longer, the system should allow:

* Paragraphs to grow taller;
* Subsequent content to move downward;
* Figures/Tables to adjust position;
* Page breaks to change;
* Total page count to change.

---

### FR-LAYOUT-002 Do Not Force Original Page Numbers

For example, if the source has 10 pages, a translation with:

```text
11 pages
12 pages
13 pages
```

is all acceptable.

---

### FR-LAYOUT-003 No Complex Layout Optimizer Required

The current product does not require a complex optimization algorithm to:

> Reposition target elements as closely as possible to the corresponding coordinates in the source PDF.

Natural reflow from a normal academic document typesetting system is the expected behavior.

---

## 22. Initial Product Target Layout

This is a product decision confirmed for the current phase.

The Initial Product target-language PDF:

> **Defaults to a single-column layout suited for reading the translation.**

Even if the Source PDF is:

```text
Two Column
```

the Target PDF is not required to remain two-column.

---

### FR-LAYOUT-004 Default Single Column

The Initial Product defaults to:

```text
Source PDF
Two Column / Single Column / Complex Academic Layout
        ↓
SemanticDocument
        ↓
Target PDF
Readable Single Column Layout
```

Single-column translation prioritizes:

* Reading comfort;
* Text-length changes after translation;
* Mathematical formula readability;
* Figure/Table typesetting;
* On-screen reading experience;

rather than copying the Source Column Layout.

---

## 23. Future Layout Profiles

After the initial product is complete, user-selectable Layout Profile capability may be added.

Targets include:

```text
Readable Single Column
```

and:

```text
Inherit Source Layout Characteristics
```

“Inherit source PDF” means preserving as far as possible:

* Single / Double Column;
* Paper Size;
* Margin Style;
* Typography Characteristics;
* Heading;
* Caption;
* Equation;
* Reference Style.

It still does not mean pixel-level replication.

---

## 24. Target PDF Content Mode

The Initial Product defaults to generating:

> **A translation-only target-language PDF.**

It does not require source and translation to be typeset in the same PDF.

---

### FR-OUTPUT-001 Translation Only

In the Initial Product:

```text
Target PDF
=
Translated Academic Document
```

With the following exceptions:

* Figure Assets remain original images;
* Text inside Figures remains in the original language;
* References remain in the original language;
* Mathematical expressions preserve mathematical semantics;
* Non-translatable proprietary structures are preserved per the corresponding policy.

---

## 25. Bilingual PDF

Bilingual PDF is not part of the Initial Product.

After the initial product is complete, support for:

```text
Bilingual PDF
```

may be added.

Possible layouts include:

* Source / translation in continuous layout;
* Paragraph Pair;
* Section Pair;
* Other bilingual reading designs.

Specific design is to be determined in a later requirements phase.

---

## 26. Renderer

The first phase adopts:

> **LaTeX**

as the formal PDF Rendering Backend.

Later additions may include:

> **Typst**

or other Renderers.

At the user-requirements layer, the requirement for Renderer is:

```text
SemanticDocument
↓
Render Model
↓
Renderer Backend
↓
PDF
```

Not having business logic directly depend on a specific `.tex` file.

---

### FR-RENDER-001 Renderer Independence

Semantic Document must not be directly bound to LaTeX.

---

### FR-RENDER-002 Style Composition

Paper style should be composed of composable properties, not a complete per-Publisher template copy.

Conceptually it should be possible to express:

```text
RenderProfile
+
RenderPolicy
+
Backend
```

to reuse capabilities such as:

* Typography;
* Spacing;
* Columns;
* Heading;
* Caption;
* Equation;
* Bibliography.

---

## 27. Source / Target Bidirectional Positioning

In the Initial Product:

* Source PDF is the original paper;
* Target PDF is translation-only;
* They are different PDFs.

Therefore bidirectional positioning is a core product capability.

---

### FR-SYNC-001 Source → Target

When the user selects or double-clicks a Paragraph in the Source PDF, the system should locate the corresponding Paragraph in the Target PDF.

---

### FR-SYNC-002 Target → Source

When the user selects or double-clicks a Paragraph in the Target PDF, the system should locate the corresponding position in the Source PDF.

---

### FR-SYNC-003 Highlight

After positioning, the corresponding content should be highlighted.

---

### FR-SYNC-004 Semantic Mapping

Sync relationships must be based on:

```text
SemanticNode ID
```

or an equivalent stable Identity.

They cannot depend on:

```text
source page == target page
```

or:

```text
source bbox ≈ target bbox
```

---

### FR-SYNC-005 Mapping Granularity

The current sync granularity is:

> **Paragraph / SemanticNode Level**

Character-level SyncTeX is not required.

---

## 28. Viewer

The Initial Product Viewer primarily supports Source / Target joint reading.

Default conceptual layout:

```text
┌─────────────────────┬─────────────────────┐
│                     │                     │
│     Source PDF      │     Target PDF      │
│                     │                     │
│                     │                     │
└─────────────────────┴─────────────────────┘
```

Users can navigate semantically via:

```text
Source → Target
Target → Source
```

---

### FR-VIEW-001 Dual Document Layout

The Initial Product must support joint viewing of Source PDF and Target PDF.

---

### FR-VIEW-002 Semantic Navigation

Users should complete jumps through Paragraph / SemanticNode correspondence.

---

### FR-VIEW-003 Mapping Debug

During development, it should be possible to inspect an element’s:

```text
Semantic ID
Source Geometry
Translation Mapping
Render Geometry
```

to diagnose structure-recovery issues.

The production user interface may hide this information.

---

## 29. Viewer Evolution After Bilingual Mode

When Bilingual PDF is supported in the future:

```text
Original + Translation
```

can already exist within the same Rendered Document.

In that mode, the following is no longer required:

```text
Left Source PDF
+
Right Target PDF
```

dual-panel front-end layout.

The Viewer can switch according to Document Mode.

For example:

```text
Translation-only Mode
→ Source / Target Dual Viewer
```

```text
Bilingual PDF Mode
→ Single Document Viewer
```

Therefore the Source/Target side-by-side Viewer is core interaction for the Initial Product, but must not become the only permanently irreplaceable Viewer layout in Viewer architecture.

---

## 30. Source Mapping

Source Mapping must at minimum express:

```text
Semantic Node
↓
Source PDF
↓
Page + Geometry
```

A Semantic Node may have:

```text
1 → N
```

Source Geometries.

For example, a cross-page Paragraph.

The target side may similarly maintain:

```text
Translated Semantic Node
↓
Rendered Geometry
```

But the core logical identity for Source → Target remains the Semantic Node, not Geometry Matching.

---

## 31. DocumentBundle

The system should retain a document-level intermediate layer capable of holding both Source and Target.

Its purposes include:

* Two-sided document association;
* Source Mapping;
* Translation Mapping;
* Schema evolution;
* Renderer data exchange;
* Viewer data exchange;
* Pipeline Cache;
* Future extension.

DocumentBundle is not a UI concept; it is the logical container for a complete processing result.

---

## 32. SemanticDocument Editing Policy

In the Initial Product:

> SemanticDocument is not exposed to end users for direct editing.

This is a confirmed product decision.

But internal design must not make SemanticDocument a non-evolving temporary object.

Future work may add Human-in-the-loop correction such as:

```text
Incorrect Reading Order
→ Correct Order

Wrong Caption Association
→ Relink Figure

Wrong Semantic Type
→ Change Node Type
```

Therefore the current design should:

* Preserve Stable ID;
* Preserve Provenance;
* Preserve Schema Version;
* Avoid having Parser Output directly serve as the sole Domain Model.

But a full Semantic Editor is not required in the Initial Product.

---

## 33. Intermediate Results and Diagnosability

PDF parsing has inherent uncertainty.

Therefore the system cannot only output:

```text
Success
```

or:

```text
Failure
```

It must be able to express localized problems, for example:

```text
Equation confidence low
Table structure ambiguous
Caption association uncertain
Reading order conflict
```

A single localized parsing issue should in principle not cause the entire paper to become unprocessable.

---

## 34. Parser Ensemble Product Constraints

The product does not require:

> Every Parser fully parses the entire paper, then majority voting is performed.

Third-party Parsers should be treated as different types of Evidence Providers.

Currently established responsibility tendencies are:

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

Ultimately:

```text
LayoutDocument
SemanticDocument
```

must be owned by this project’s own data models.

Third-party Parsers must not be the sole source of truth for the internal Domain Model.

---

## 35. Core Domain Pipeline

The current logical processing chain is:

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

With:

```text
Mapping
DocumentBundle
```

maintaining relationships between stages.

These models each serve:

| Model | User Requirement |
| --- | --- |
| PhysicalDocument | Preserve raw physical PDF evidence |
| Evidence | Support collaboration among multiple Parsers |
| LayoutDocument | Recover page layout relationships |
| SemanticDocument | Recover paper logical structure |
| TranslationLayer | Preserve Source ↔ Translation |
| Mapping | Bidirectional positioning |
| RenderDocument | Decouple from specific Renderer |
| DocumentBundle | Manage complete processing results |

---

## 36. Parser Error Isolation

Third-party Parser failure must not break the complete Pipeline.

For example:

```text
Docling Table Parser Failed
```

must not automatically mean:

```text
Entire Document Failed
```

The system should as far as possible:

* Degrade gracefully;
* Preserve existing Evidence;
* Mark Issues;
* Continue processing other Semantic Nodes.

---

## 37. Local Application

The primary runtime form of the Initial Product is:

> **Local Application**

Core product state is stored locally first.

Including:

* Imported PDF;
* Parsed Data;
* SemanticDocument;
* DocumentBundle;
* Translation Cache;
* Render Artifacts;
* Mapping;
* Project Metadata.

---

### FR-LOCAL-001 Local Project

After a user imports a paper, they should be able to form a recoverable local Project / Document Workspace—not a one-off conversion task.

---

### FR-LOCAL-002 Pipeline Cache

Completed parsing and intermediate results should be persistable.

When the user opens a paper again, the full Pipeline should not be re-executed every time.

---

### FR-LOCAL-003 External Translation Exception

Local First does not mean all computation must be offline.

After the user selects an external Translation Provider:

```text
Semantic Content
→ External Translation Service
```

is allowed behavior.

The product should clearly distinguish:

```text
Local Document Processing
```

from:

```text
External Translation Request
```

---

## 38. Server + Web Client

Server + Web Client is not part of the Initial Product.

After the initial product is complete, expansion to:

```text
Client
↓
Server
↓
Document Processing / Translation / Storage
```

is possible.

But the Initial Product Domain Model and DocumentBundle must not depend on desktop-only state.

When migrating to a Server in the future, the following should be reused as far as possible:

* SemanticDocument;
* Parser Adapter;
* Translation Provider;
* Render Pipeline;
* Mapping;
* Schema.

---

## 39. Non-Functional Requirements

### NFR-001 Deterministic Identity

Stable content from the same PDF should as far as possible receive stable Semantic Identity.

Otherwise:

* Translation Cache;
* Mapping;
* Incremental Processing;

cannot be implemented reliably.

---

### NFR-002 Provenance

Any important Semantic Object produced by inference must be traceable to its source.

---

### NFR-003 Incremental Processing

Changing Renderer, translation, or a post-processing step must not force re-execution of expensive PDF Parsing.

---

### NFR-004 Serializable

Major intermediate models must be stably serializable and deserializable.

---

### NFR-005 Versionable

Schema must support version evolution.

Historical DocumentBundles must not become completely unreadable because of Schema upgrades.

---

### NFR-006 Reproducible

The same input, same configuration, and same Parser / Model Version should as far as possible produce reproducible results.

---

### NFR-007 Inspectable

Every major stage of the Pipeline should be independently inspectable.

Developers must be able to answer:

```text
How did this Paragraph come to be?
```

Not only see the final PDF.

---

### NFR-008 Extensible

Future additions of:

* New Parser;
* New Translation Provider;
* New Renderer;
* Typst;
* New Semantic Node;
* OCR;
* Server;

must not require rewriting the entire Pipeline.

---

## 40. Initial Product Acceptance Goals

For a typical born-digital academic paper, users should be able to complete:

```text
Import PDF
↓
System automatically recovers paper structure
↓
Generate SemanticDocument
↓
Complete translation through user-selected Translation Provider
↓
Generate single-column translation-only Target PDF
↓
Read the paper normally
↓
Click translated Paragraph
↓
Quickly locate Source PDF Paragraph
↓
Click Source Paragraph
↓
Return to corresponding translation
```

Throughout this process, users do not need to manually reorganize the entire paper structure.

---

## 41. Golden PDF Acceptance Set

Establish at least the following Golden PDF Cases.

### Case A — Ordinary Single-Column Paper

Verify:

* Paragraph;
* Heading;
* Equation;
* Figure;
* Reference.

---

### Case B — IEEE / Elsevier-Style Two-Column Paper

Verify:

* Reading Order;
* Column;
* Figure;
* Caption;
* Cross-column elements;
* Final correct conversion to single-column Target PDF.

---

### Case C — Math-Heavy Paper

Verify:

* Inline Equation;
* Display Equation;
* Equation Number;
* Math environments.

---

### Case D — Figure / Table-Heavy Paper

Verify:

* Asset;
* Caption;
* Table Structure;
* Cross Reference;
* Figure Asset preserved unchanged;
* Text inside Figures not translated.

---

### Case E — Reference-Heavy Paper

Verify:

* Citation;
* Citation → Reference Mapping;
* References content remains in the original language.

---

For each Case, verify simultaneously:

```text
PDF Parsing
Semantic Recovery
Translation
Rendering
Source Mapping
Viewer Navigation
```

Not only whether the final PDF was generated successfully.

---

## 42. Product Quality Priorities

When multiple goals conflict, priority is:

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

For example:

If:

```text
Preserving original two-column layout
```

would significantly degrade target-language reading experience,

the Initial Product should choose:

```text
Readable Single Column
```

If:

```text
Preserving original page numbers
```

would cause crowded translated text,

then repagination is allowed.

If:

```text
Fully copying Publisher Style
```

would greatly increase Renderer complexity,

then a composable academic typesetting system should be preferred.

---

## 43. Initial Product Confirmed Decisions

As of v0.2, the following requirements are confirmed.

| Product Question | Initial Product Decision |
| --- | --- |
| Scanned PDF | Not supported |
| Born-digital PDF | Supported |
| Target Layout | Default single column |
| Inherit original two-column | Not required in initial version |
| Target PDF | Translation-only |
| Bilingual PDF | Supported later |
| Figure Caption | Translated |
| Text inside Figure | Not translated |
| Figure Asset | Preserve original image |
| Table content | Translatable |
| References | Not translated |
| Citation Relationship | Preserved |
| SemanticDocument user editing | Not supported in initial version |
| Semantic Edit Extension | Reserved in architecture |
| Translation Provider | Provider Agnostic |
| External Translation Service | Supported |
| Primary Runtime | Local |
| Server + Web Client | Later |
| Source / Target Viewer | Dual-document joint reading in initial version |
| Bilingual-mode Viewer | Single-document mode available later |
| Source Mapping | Paragraph / SemanticNode |
| Character Mapping | Not required |
| Layout Optimizer | Not required |
| Renderer | Initial LaTeX |
| Typst | May be added later |

---

## 44. Post-Initial Product Roadmap

The following capabilities are candidate extensions after the initial product is complete.

Note:

> This section is a Product Roadmap, not a mandatory acceptance requirement for the current Milestone.

---

### R1. Scanned PDF / OCR

Add:

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

### R2. Layout Profile Selection

Allow users to choose:

```text
Readable Single Column
```

or:

```text
Inherit Source Layout
```

---

### R3. Bilingual PDF

Support typesetting:

```text
Source
+
Translation
```

directly into the same PDF.

---

### R4. Viewer Layout Evolution

In Bilingual PDF mode, the following may no longer be required:

```text
Left Source
+
Right Target
```

Viewer.

---

### R5. SemanticDocument Human Correction

Study user manual correction of:

* Reading Order;
* Semantic Node Type;
* Caption Association;
* Figure/Table Relationship;
* Section Structure.

---

### R6. Figure Internal Translation

Study:

* Figure OCR;
* Axis Label Translation;
* Legend Translation;
* Diagram Text Translation;
* Figure Re-rendering.

Not committed for implementation at present.

---

### R7. Server + Web Client

Extend the existing Local Pipeline to:

```text
Server Processing
+
Web Client
```

---

### R8. Typst Renderer

Add Typst Backend alongside the LaTeX Renderer.

---

## 45. Relationship to Development Milestones

Requirements take precedence over Milestones.

The current development direction can be roughly mapped as:

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

Actual Milestones may be adjusted, split, or merged according to the current repository state.

They cannot change the product behavior defined in this document.

See the development roadmap at [`docs/development/roadmap.en.md`](../development/roadmap.en.md). Architecture contracts are at [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md).

---

## 46. Explicitly Forbidden Architectural Drift

As development proceeds, the project should avoid degenerating into:

### “Advanced OCR”

Recovering only text, with no SemanticDocument.

### “PDF Translator”

Stuffing translated text back into original bboxes.

### “Markdown Converter”

Turning all papers into Markdown and treating Markdown as the final product.

### “Publisher Template Collection”

Continuously copying:

```text
IEEE.tex
Elsevier.tex
Springer.tex
...
```

### “Parser Wrapper”

Internal Domain Model completely identical to output from:

* MinerU;
* Docling;
* GROBID;

or some other third party.

### “Coordinate Matching Viewer”

Guessing Paragraph correspondence through Source Page / Target Page coordinates.

### “Provider-specific Translation Application”

Binding the entire Translation Pipeline directly to a single LLM API.

### “Desktop-only Domain”

Core Schema and Domain Model strongly bound to Electron / Desktop UI, preventing future migration to Server.

These directions all diverge from this project’s core value.

---

## 47. Core Project Value

What this project truly needs to build is not:

> A better-looking PDF translator.

But:

> **A system that can restore non-editable academic PDFs into an intermediate document layer with structure, semantics, provenance relationships, and re-typesetting capability, and use that intermediate layer to deliver high-quality cross-language academic reading.**

Therefore the project’s most important assets are not the final `.pdf` files, but:

```text
Physical Evidence
↓
SemanticDocument
↓
Source / Translation Mapping
↓
DocumentBundle
```

As long as this layer is reliable, the following can be extended naturally:

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

Without redesigning the entire PDF understanding system.

---

## 48. Requirement Change Policy

Any future new capability should first answer:

> Which user problem does it solve?

And be classified at least as one of:

```text
Product Requirement
User Experience Requirement
Quality Requirement
Technical Requirement
Implementation Detail
Experiment
```

New technical components must not automatically become product requirements.

For example:

```text
“Introduce a new Parser”
```

is not a user requirement.

A real requirement should be similar to:

```text
“Improve structure-recovery accuracy for complex Tables.”
```

A Parser is only one implementation to satisfy that requirement.

---

## 49. Document Versioning Rules

This document is the Source of Truth for user requirements.

If requirements change in the future:

1. Update this document;
2. Update the version number;
3. Commit an explicit Requirements Change in Git;
4. Check whether Architecture / ADR / Milestone are affected;
5. Update downstream development plans when necessary.

When Agents read historical requirements that conflict:

> **Always prefer the Product Requirements that are version-updated, time-updated, and explicitly marked as the current version.**

---

## 50. v0.2 Requirements Change Log

Relative to v0.1, this version formally confirms:

1. Initial Product does not support scanned PDFs for now;
2. Initial Product Target PDF defaults to a single-column layout suited for reading the translation;
3. Users may later choose single-column or inherit Source PDF layout characteristics;
4. Initial Product Target PDF defaults to translation-only;
5. Bilingual PDF is deferred until after Initial Product completion;
6. In Bilingual PDF mode, Source / Target side-by-side Viewer is not mandatory in the future;
7. Text inside Figures is not translated in the Initial Product;
8. Figure Assets are preserved unchanged;
9. References remain in the original language in the Initial Product;
10. SemanticDocument is not exposed to users for editing for now;
11. Semantic Editing capability is reserved in architecture;
12. Translation Provider uses a Provider-Agnostic design;
13. External Translation Service integration is allowed;
14. Initial Product adopts a Local-first runtime mode;
15. Server + Web Client is deferred until after Initial Product completion.

---

## 51. Final Product Principles

This project ultimately follows:

> **Preserve semantics, not pixels. Preserve provenance, not page positions. Reconstruct the paper, not the PDF canvas.**

In Chinese:

> **保留语义，而不是像素；保留来源，而不是页码位置；重建论文，而不是复制 PDF 画布。**

For the Initial Product, an additional pragmatic phased principle applies:

> **First stably recover, translate, re-typeset, and establish traceable relationships for a born-digital academic PDF—then extend to OCR, bilingual typesetting, inherited source layout, human correction, and server deployment.**
