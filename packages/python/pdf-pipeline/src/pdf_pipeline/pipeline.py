"""End-to-end Walking Skeleton pipeline orchestration (M2 Exit Gate).

PDF -> Physical -> Layout -> Semantic -> Dummy Translation -> LaTeX ->
Target PDF -> RenderAnchor MappingBundle.

Run as a module: ``python -m pdf_pipeline run <input.pdf> <outdir>``.
Outputs five canonical JSON documents plus the compiled target PDF and
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

from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.render_anchor import (
    build_mapping_bundle,
    recover_render_anchors,
)
from pdf_pipeline.render_latex import (
    compile_latex,
    project_to_latex,
    render_target_document_id,
)
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated import (
        LayoutDocument,
        PhysicalDocument,
        SemanticDocument,
    )

PIPELINE_VERSION = "0.1.0"


def region_texts_from(physical: PhysicalDocument, layout: LayoutDocument) -> dict[str, str]:
    """Join text of the physical spans behind each TEXT region."""
    spans = {obj.id: obj for obj in physical.objects if obj.objectType == "textSpan"}
    texts: dict[str, str] = {}
    for region in layout.regions:
        if region.kind != "TEXT":
            continue
        texts[region.id] = " ".join(
            spans[object_id].text for object_id in region.physicalObjectIds if object_id in spans
        )
    return texts


def build_source_anchors(
    physical: PhysicalDocument,
    layout: LayoutDocument,
    semantic: SemanticDocument,
) -> tuple[list, list, list]:
    """PhysicalLayoutBindings + SourceAnchors + SourceSemanticBindings.

    Layout regions carry the physical object ids; each semantic node records
    which region(s) it came from via the region order used at recovery time.
    The Walking Skeleton pairs the i-th non-root semantic node with the i-th
    reading-flow region, mirroring the recovery-time walk.
    """
    del physical
    physical_layout_bindings = [
        generated.PhysicalLayoutBinding(
            id=stable_uuid(layout.id, "plb", region.id),
            layoutRegionId=region.id,
            physicalObjectIds=list(region.physicalObjectIds),
        )
        for region in layout.regions
    ]

    region_by_id = {region.id: region for region in layout.regions}
    node_ids = [node.id for node in semantic.nodes[1:]]
    body_regions = [region_by_id[rid] for rid in layout.primaryFlow if rid in region_by_id]

    source_anchors: list[generated.SourceAnchor] = []
    source_semantic_bindings: list[generated.SourceSemanticBinding] = []
    for index, node_id in enumerate(node_ids):
        if index >= len(body_regions):
            break
        region = body_regions[index]
        anchor = generated.SourceAnchor(
            id=stable_uuid(semantic.id, "source-anchor", node_id),
            fragments=[
                generated.LayoutRegionRef(fragmentType="layoutRegion", layoutRegionId=region.id)
            ],
            confidence=0.7,
        )
        source_anchors.append(anchor)
        source_semantic_bindings.append(
            generated.SourceSemanticBinding(
                id=stable_uuid(semantic.id, "ssb", node_id),
                semanticNodeId=node_id,
                sourceAnchorIds=[anchor.id],
            )
        )
    return physical_layout_bindings, source_anchors, source_semantic_bindings


def _write_viewer_assets(
    *,
    data_dir: Path,
    source_pdf: bytes,
    target_pdf: Path,
    mapping: generated.MappingBundle,
    render_anchors: list,
    physical: PhysicalDocument,
) -> None:
    """Emit the static fetch targets for the web viewer (Phase 2.7)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "source.pdf").write_bytes(source_pdf)
    (data_dir / "target.pdf").write_bytes(target_pdf.read_bytes())
    (data_dir / "mapping.json").write_text(
        json.dumps(
            {**dump_document(mapping), "renderAnchors": [dump_document(a) for a in render_anchors]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    source_page = physical.pages[0].geometry
    target_doc = pdfium.PdfDocument(str(target_pdf))
    try:
        target_width, target_height = target_doc[0].get_size()
    finally:
        target_doc.close()
    meta = {
        "sourcePageCount": len(physical.pages),
        "targetPageCount": len(physical.pages),
        "sourcePageSize": {"widthPt": source_page.widthPt, "heightPt": source_page.heightPt},
        "targetPageSize": {"widthPt": target_width, "heightPt": target_height},
    }
    (data_dir / "viewer-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def run_pipeline(source_pdf: Path, out_dir: Path) -> dict[str, Path]:
    """Run the full Walking Skeleton pipeline; return produced artifact paths."""
    data = source_pdf.read_bytes()
    out_dir.mkdir(parents=True, exist_ok=True)

    physical = extract_physical_document(data)
    layout = recover_layout_document(physical)
    semantic = recover_semantic_document(layout, region_texts_from(physical, layout))
    translated = translate_document(semantic)

    tex = project_to_latex(translated)
    target_pdf = compile_latex(tex, out_dir / "build")

    render_anchors = recover_render_anchors(target_pdf, semantic)
    plb, source_anchors, ssb = build_source_anchors(physical, layout, semantic)
    mapping = build_mapping_bundle(
        semantic,
        source_anchors=source_anchors,
        source_semantic_bindings=ssb,
        physical_layout_bindings=plb,
        render_anchors=render_anchors,
        render_document_id=render_target_document_id(semantic),
    )

    outputs = {
        "physical.json": physical,
        "layout.json": layout,
        "semantic.json": semantic,
        "translated.json": translated,
        "mapping.json": mapping,
    }
    paths: dict[str, Path] = {}
    for name, document in outputs.items():
        path = out_dir / name
        dump_document(document, path=path)
        paths[name] = path

    # Cross-layer integrity: every id reference in the bundle resolves.
    bundle = {
        "physical": dump_document(physical),
        "layout": dump_document(layout),
        "semantic": dump_document(semantic),
        "mappings": dump_document(mapping),
    }
    issues = validate_bundle_references(bundle)
    if issues:
        raise RuntimeError(f"bundle reference issues: {issues}")

    paths["target.pdf"] = target_pdf

    data_dir = out_dir / "viewer" / "data"
    _write_viewer_assets(
        data_dir=data_dir,
        source_pdf=data,
        target_pdf=target_pdf,
        mapping=mapping,
        render_anchors=render_anchors,
        physical=physical,
    )
    paths["viewer-data"] = data_dir
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M2 Walking Skeleton pipeline")
    parser.add_argument("input", type=Path, help="source PDF")
    parser.add_argument("outdir", type=Path, help="output directory")
    args = parser.parse_args(argv)
    paths = run_pipeline(args.input, args.outdir)
    sys.stdout.write(json.dumps({name: str(path) for name, path in paths.items()}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
