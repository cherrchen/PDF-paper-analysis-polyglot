# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""End-to-end pipeline orchestration (Physical through render + mapping).

PDF -> Physical -> Evidence -> Layout -> Semantic + Translation ->
RenderDocument -> LaTeX -> Target PDF -> RenderAnchor MappingBundle.

Run as a module: ``python -m pdf_pipeline run <input.pdf> <outdir>``.
Outputs seven canonical JSON documents plus the compiled target PDF and
page previews for the viewer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
from document_model import dump_document, validate_bundle_references
from document_model.generated import schema_models as generated
from paper_llm import translate_document
from paper_llm.cache import TranslationCache
from paper_llm.config import TranslationConfig, load_translation_config
from paper_llm.translation import create_provider

from pdf_pipeline.evidence.providers import MockLayoutEvidenceProvider
from pdf_pipeline.fusion import RegionLine
from pdf_pipeline.geometry import as_rect
from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document, probe_input_capability
from pdf_pipeline.render_anchor import (
    build_mapping_bundle,
    recover_render_anchors,
)
from pdf_pipeline.render_composer import DEFAULT_POLICY, DEFAULT_PROFILE, compose_render_document
from pdf_pipeline.render_latex import (
    compile_latex,
    project_to_latex,
    render_target_document_id,
)
from pdf_pipeline.resource_store import bind_figure_image_resources, extract_resource_document
from pdf_pipeline.sem_validate import validate_semantic_recovery
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated.schema_models import (
        LayoutDocument,
        PhysicalDocument,
        SemanticDocument,
    )

PIPELINE_VERSION = "0.1.0"


def region_texts_from(physical: PhysicalDocument, layout: LayoutDocument) -> dict[str, str]:
    """Join text of the physical spans behind each text-carrying region."""
    spans = {obj.id: obj for obj in physical.objects if obj.objectType == "textSpan"}
    texts: dict[str, str] = {}
    for region in layout.regions:
        if region.kind not in {"TEXT", "FOOTNOTE", "TABLE", "FORMULA"}:
            continue
        texts[region.id] = " ".join(
            spans[object_id].text for object_id in region.physicalObjectIds if object_id in spans
        )
    return texts


def region_lines_from(
    physical: PhysicalDocument, layout: LayoutDocument
) -> dict[str, list[RegionLine]]:
    """Physical spans behind each text-carrying region as per-span lines.

    Semantic recovery needs the line granularity the joined text loses:
    table rows are one span each, and font size separates titles from
    authors. Regions outside :func:`region_texts_from` carry no lines.
    """
    spans = {obj.id: obj for obj in physical.objects if obj.objectType == "textSpan"}
    lines: dict[str, list[RegionLine]] = {}
    for region in layout.regions:
        if region.kind not in {"TEXT", "FOOTNOTE", "TABLE", "FORMULA"}:
            continue
        region_lines: list[RegionLine] = []
        for object_id in region.physicalObjectIds:
            span = spans.get(object_id)
            if span is None:  # pragma: no cover - defensive; ids come from layout
                continue
            region_lines.append(
                RegionLine(
                    text=span.text,
                    rect=as_rect(span.geometry),
                    font_size=span.fontSize or as_rect(span.geometry).height,
                )
            )
        if region_lines:
            lines[region.id] = region_lines
    return lines


def build_source_anchors(
    physical: PhysicalDocument,
    layout: LayoutDocument,
    semantic: SemanticDocument,
) -> tuple[
    list[generated.PhysicalLayoutBinding],
    list[generated.SourceAnchor],
    list[generated.SourceSemanticBinding],
]:
    """PhysicalLayoutBindings + SourceAnchors + SourceSemanticBindings.

    Layout regions carry the physical object ids; each semantic node records
    its source regions in ``attributes.layoutRegionIds`` at recovery time, so
    anchor pairing is identity-based instead of positional and a merged
    paragraph anchors to every region it was recovered from (N -> 1).
    """
    physical_layout_bindings = [
        generated.PhysicalLayoutBinding(
            id=stable_uuid(layout.id, "plb", region.id),
            layoutRegionId=region.id,
            physicalObjectIds=list(region.physicalObjectIds),
        )
        for region in layout.regions
    ]

    source_anchors: list[generated.SourceAnchor] = []
    source_semantic_bindings: list[generated.SourceSemanticBinding] = []
    for node in semantic.nodes[1:]:
        raw = node.attributes.get("layoutRegionIds")
        region_ids: list[str] = [item for item in raw if isinstance(item, str)] if raw else []
        if not region_ids:
            continue
        anchor = generated.SourceAnchor(
            id=stable_uuid(semantic.id, "source-anchor", node.id),
            fragments=[
                generated.LayoutRegionRef(fragmentType="layoutRegion", layoutRegionId=region_id)
                for region_id in region_ids
            ],
            confidence=0.7,
        )
        source_anchors.append(anchor)
        source_semantic_bindings.append(
            generated.SourceSemanticBinding(
                id=stable_uuid(semantic.id, "ssb", node.id),
                semanticNodeId=node.id,
                sourceAnchorIds=[anchor.id],
            )
        )
    del physical
    return physical_layout_bindings, source_anchors, source_semantic_bindings


def _write_viewer_assets(
    *,
    data_dir: Path,
    source_pdf: bytes,
    target_pdf: Path,
    mapping: generated.MappingBundle,
    render_anchors: list[generated.RenderAnchor],
    physical: PhysicalDocument,
    layout: LayoutDocument,
    semantic: SemanticDocument,
) -> None:
    """Emit the static fetch targets for the web viewer (Phase 2.7)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "source.pdf").write_bytes(source_pdf)
    (data_dir / "target.pdf").write_bytes(target_pdf.read_bytes())
    page_index_by_id = {page.id: page.index for page in physical.pages}
    source_regions = [
        {
            "id": region.id,
            "pageIndex": page_index_by_id[region.pageId],
            "geometry": dump_document(region.geometry),
        }
        for region in layout.regions
    ]
    (data_dir / "mapping.json").write_text(
        json.dumps(
            {
                "viewerDataVersion": 1,
                **dump_document(mapping),
                "semanticNodes": [
                    {"id": node.id, "kind": node.kind} for node in semantic.nodes[1:]
                ],
                "sourceRegions": source_regions,
                "renderAnchors": [dump_document(a) for a in render_anchors],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    source_page = physical.pages[0].geometry
    target_doc = pdfium.PdfDocument(str(target_pdf))
    try:
        target_page_count = len(target_doc)
        target_width, target_height = target_doc[0].get_size()
    finally:
        target_doc.close()
    meta = {
        "sourcePageCount": len(physical.pages),
        "targetPageCount": target_page_count,
        "sourcePageSize": {"widthPt": source_page.widthPt, "heightPt": source_page.heightPt},
        "targetPageSize": {"widthPt": target_width, "heightPt": target_height},
    }
    (data_dir / "viewer-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def run_pipeline(
    source_pdf: Path,
    out_dir: Path,
    *,
    viewer_data_dir: Path | None = None,
    translation_config: TranslationConfig | None = None,
) -> dict[str, Path]:
    """Run the full Walking Skeleton pipeline; return produced artifact paths."""
    data = source_pdf.read_bytes()
    out_dir.mkdir(parents=True, exist_ok=True)
    config = translation_config or load_translation_config()
    cache = None
    if config.cache_dir is not None:
        cache = TranslationCache(config.cache_dir / "translation-cache.jsonl")

    capability = probe_input_capability(data)
    if not capability.usable:
        # FR-PDF-002: fail loudly at the entry point rather than silently
        # producing low-quality recovery output for scanned documents.
        raise ValueError(f"unsupported input PDF: {capability.reason}")

    physical = extract_physical_document(data)
    evidence = MockLayoutEvidenceProvider().collect(physical)
    layout = recover_layout_document(physical, evidence=evidence)
    region_texts = region_texts_from(physical, layout)
    semantic = recover_semantic_document(
        layout,
        region_texts,
        lines=region_lines_from(physical, layout),
        evidence=evidence,
    )
    recovery_issues = validate_semantic_recovery(semantic, layout, region_texts)
    if recovery_issues:
        store = semantic.issues or generated.IssueStore(issues=[])
        semantic = semantic.model_copy(
            update={
                "issues": store.model_copy(update={"issues": [*store.issues, *recovery_issues]})
            }
        )
    provider = None
    provider_model = "dummy"
    provider_endpoint = ""
    if config.provider is not None:
        provider = create_provider(
            provider_model="openai-compat",
            provider_config=config.provider,
        )
        provider_model = f"openai-compat:{config.provider.model}"
        provider_endpoint = config.provider.endpoint
    translation = translate_document(
        semantic,
        provider,
        target_locale=config.target_locale,
        source_locale=config.source_locale,
        terminology_file=config.terminology_file,
        provider_model=provider_model,
        provider_endpoint=provider_endpoint,
        cache=cache,
    )
    resource_dir = out_dir / "resources"
    resources = extract_resource_document(data, resource_dir=resource_dir)
    semantic = bind_figure_image_resources(semantic, layout, resources.resources)
    render = compose_render_document(
        semantic,
        translation,
        profile=DEFAULT_PROFILE,
        policy=DEFAULT_POLICY,
        resources=resources.resources,
    )

    tex = project_to_latex(render, resource_dir=resource_dir)
    target_pdf = compile_latex(tex, out_dir / "build")

    render_anchors = recover_render_anchors(target_pdf, semantic)
    plb, source_anchors, ssb = build_source_anchors(physical, layout, semantic)
    mapping = build_mapping_bundle(
        semantic,
        source_anchors=source_anchors,
        source_semantic_bindings=ssb,
        physical_layout_bindings=plb,
        render_anchors=render_anchors,
        render_document_id=render_target_document_id(render),
    )

    outputs = {
        "physical.json": physical,
        "evidence.json": evidence,
        "layout.json": layout,
        "semantic.json": semantic,
        "translation.json": translation,
        "render.json": render,
        "mapping.json": mapping,
        "resources.json": resources,
    }
    paths: dict[str, Path] = {}
    for name, document in outputs.items():
        path = out_dir / name
        dump_document(document, path=path)
        paths[name] = path

    # Cross-layer integrity: every id reference in the bundle resolves.
    bundle = {
        "physical": dump_document(physical),
        "evidence": dump_document(evidence),
        "layout": dump_document(layout),
        "semantic": dump_document(semantic),
        "translation": dump_document(translation),
        "render": dump_document(render),
        "mappings": dump_document(mapping),
    }
    issues = validate_bundle_references(bundle)
    if issues:
        raise RuntimeError(f"bundle reference issues: {issues}")

    paths["target.pdf"] = target_pdf

    data_dir = viewer_data_dir or out_dir / "viewer" / "data"
    _write_viewer_assets(
        data_dir=data_dir,
        source_pdf=data,
        target_pdf=target_pdf,
        mapping=mapping,
        render_anchors=render_anchors,
        physical=physical,
        layout=layout,
        semantic=semantic,
    )
    paths["viewer-data"] = data_dir
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PDF paper analysis pipeline")
    parser.add_argument("input", type=Path, help="source PDF")
    parser.add_argument("outdir", type=Path, help="output directory")
    parser.add_argument(
        "--viewer-data-dir",
        type=Path,
        help="optional Vite public/data output directory for viewer assets",
    )
    args = parser.parse_args(argv)
    paths = run_pipeline(args.input, args.outdir, viewer_data_dir=args.viewer_data_dir)
    sys.stdout.write(json.dumps({name: str(path) for name, path in paths.items()}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
