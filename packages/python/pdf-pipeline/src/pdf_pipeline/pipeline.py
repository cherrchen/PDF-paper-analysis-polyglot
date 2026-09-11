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
import shutil
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pypdfium2 as pdfium
from document_model import dump_document, load_document, validate_bundle_references
from document_model.generated import schema_models as generated
from paper_llm import translate_document
from paper_llm.cache import TranslationCache
from paper_llm.config import TranslationConfig, load_translation_config
from paper_llm.translation import (
    DUMMY_PROVIDER_MODEL,
    TranslationProviderNotConfiguredError,
    create_provider,
    retranslate_nodes,
    translation_requires_provider,
)

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
    from paper_llm.types import TranslationProvider

PIPELINE_VERSION = "0.1.0"

# Workspace file -> canonical document kind (document_model.serialize._ROOT_MODELS).
_WORKSPACE_KINDS = {
    "physical.json": "physical-document",
    "layout.json": "layout-document",
    "semantic.json": "semantic-document",
    "translation.json": "translation-layer",
    "mapping.json": "mapping",
    "resources.json": "resources",
}


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


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via sibling temp + replace so a reader never sees a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write binary via sibling temp + replace."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _atomic_write_json(path: Path, data: object) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _viewer_revision_id() -> str:
    return uuid.uuid4().hex


def _read_viewer_manifest(data_dir: Path) -> dict[str, str] | None:
    path = data_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    revision = payload.get("revision")
    if not isinstance(revision, str) or not revision:
        return None
    return {str(key): str(value) for key, value in payload.items()}


def _prune_viewer_revisions(data_dir: Path, keep: set[str]) -> None:
    root = data_dir / "revisions"
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child, ignore_errors=True)


def _commit_prepared_file(staged: Path, target: Path) -> None:
    """Commit one prepared sibling file (a seam for publish fault injection)."""
    staged.replace(target)


def _replace_files_with_rollback(contents: dict[Path, bytes], *, commit_last: Path) -> None:
    """Atomically replace each file and restore the old set on partial failure.

    Filesystems do not offer a transaction across several paths. Preparing all
    siblings first, publishing the pointer last, and restoring already-replaced
    paths on error gives the workspace, stable aliases, and manifest one
    recoverable commit boundary.
    """
    if commit_last not in contents:
        raise ValueError("commit_last must be present in contents")
    ordered = [path for path in contents if path != commit_last] + [commit_last]
    staged: dict[Path, Path] = {}
    previous: dict[Path, bytes | None] = {}
    replaced: list[Path] = []
    token = uuid.uuid4().hex
    try:
        for target in ordered:
            target.parent.mkdir(parents=True, exist_ok=True)
            previous[target] = target.read_bytes() if target.is_file() else None
            prepared = target.with_name(f".{target.name}.publish-{token}")
            prepared.write_bytes(contents[target])
            staged[target] = prepared
        for target in ordered:
            _commit_prepared_file(staged[target], target)
            replaced.append(target)
    except BaseException as error:
        rollback_errors: list[OSError] = []
        for target in reversed(replaced):
            try:
                old = previous[target]
                if old is None:
                    target.unlink(missing_ok=True)
                else:
                    rollback = target.with_name(f".{target.name}.rollback-{token}")
                    rollback.write_bytes(old)
                    rollback.replace(target)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise RuntimeError("publish failed and rollback was incomplete") from error
        raise
    finally:
        for prepared in staged.values():
            prepared.unlink(missing_ok=True)


def _publish_viewer_revision(
    data_dir: Path,
    *,
    mapping_text: str,
    meta_text: str,
    source_pdf: bytes,
    target_pdf: bytes,
    workspace_updates: dict[Path, bytes] | None = None,
) -> str:
    """Write one complete viewer revision and commit all mutable pointers.

    The immutable revision is staged first. Stable aliases and optional
    workspace documents are replaced with rollback protection, then
    ``manifest.json`` is committed last. A failure at any point restores every
    mutable file and removes the unpublished revision.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    previous = _read_viewer_manifest(data_dir)
    revision = _viewer_revision_id()
    rev_dir = data_dir / "revisions" / revision
    rev_dir.mkdir(parents=True, exist_ok=True)
    (rev_dir / "mapping.json").write_text(mapping_text, encoding="utf-8")
    (rev_dir / "viewer-meta.json").write_text(meta_text, encoding="utf-8")
    (rev_dir / "source.pdf").write_bytes(source_pdf)
    (rev_dir / "target.pdf").write_bytes(target_pdf)
    manifest = {
        "revision": revision,
        "mapping": f"/data/revisions/{revision}/mapping.json",
        "meta": f"/data/revisions/{revision}/viewer-meta.json",
        "source": f"/data/revisions/{revision}/source.pdf",
        "target": f"/data/revisions/{revision}/target.pdf",
    }
    manifest_path = data_dir / "manifest.json"
    replacements = {
        data_dir / "mapping.json": mapping_text.encode(),
        data_dir / "viewer-meta.json": meta_text.encode(),
        data_dir / "source.pdf": source_pdf,
        data_dir / "target.pdf": target_pdf,
        **(workspace_updates or {}),
        manifest_path: (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(),
    }
    try:
        _replace_files_with_rollback(replacements, commit_last=manifest_path)
    except BaseException:
        shutil.rmtree(rev_dir, ignore_errors=True)
        raise
    keep = {revision}
    if previous is not None:
        keep.add(previous["revision"])
    _prune_viewer_revisions(data_dir, keep)
    return revision


def _viewer_node(node: generated.SemanticNode) -> dict[str, object]:
    data: dict[str, object] = {
        "id": node.id,
        "kind": node.kind,
        "content": dump_document(node.content),
        "confidence": dump_document(node.confidence),
        "provenanceIds": list(node.provenanceIds),
    }
    if node.parentId is not None:
        data["parentId"] = node.parentId
    return data


def _viewer_translation(translation: generated.TranslationLayer) -> dict[str, object]:
    data: dict[str, object] = {
        "targetLocale": translation.targetLocale,
        "entries": [
            {
                "semanticNodeId": entry.semanticNodeId,
                "content": dump_document(entry.content),
                **({"confidence": entry.confidence} if entry.confidence is not None else {}),
                **({"providerModel": entry.providerModel} if entry.providerModel else {}),
                **({"cacheKey": entry.cacheKey} if entry.cacheKey else {}),
            }
            for entry in translation.entries
        ],
    }
    if translation.sourceLocale is not None:
        data["sourceLocale"] = translation.sourceLocale
    if translation.providerModel is not None:
        data["providerModel"] = translation.providerModel
    if translation.terminologyRevision is not None:
        data["terminologyRevision"] = translation.terminologyRevision
    if translation.terminology is not None:
        data["terminology"] = [dump_document(term) for term in translation.terminology]
    return data


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
    translation: generated.TranslationLayer,
    workspace_updates: dict[Path, bytes] | None = None,
) -> str:
    """Emit the static fetch targets for the web viewer (M6 bidirectional reader, v2).

    Returns the published revision id. Files are staged in
    ``data_dir/revisions/<id>/`` and only become current when ``manifest.json``
    is replaced.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    page_index_by_id = {page.id: page.index for page in physical.pages}
    source_regions = [
        {
            "id": region.id,
            "pageIndex": page_index_by_id[region.pageId],
            "geometry": dump_document(region.geometry),
        }
        for region in layout.regions
    ]
    provenance = (
        [dump_document(record) for record in semantic.provenance.records]
        if semantic.provenance is not None
        else []
    )
    issues = [
        dump_document(issue)
        for store in (semantic.issues, mapping.issues, translation.issues)
        if store is not None
        for issue in store.issues
    ]
    mapping_text = (
        json.dumps(
            {
                "viewerDataVersion": 2,
                **dump_document(mapping),
                "semanticNodes": [_viewer_node(node) for node in semantic.nodes[1:]],
                "semanticRelations": [dump_document(rel) for rel in semantic.relations],
                "sourceRegions": source_regions,
                "renderAnchors": [dump_document(a) for a in render_anchors],
                "translation": _viewer_translation(translation),
                "provenance": provenance,
                "issues": issues,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    source_pages = [
        {"widthPt": page.geometry.widthPt, "heightPt": page.geometry.heightPt}
        for page in physical.pages
    ]
    target_doc = pdfium.PdfDocument(str(target_pdf))
    try:
        target_page_count = len(target_doc)
        target_pages: list[dict[str, float]] = []
        for index in range(target_page_count):
            width, height = target_doc[index].get_size()
            target_pages.append({"widthPt": width, "heightPt": height})
    finally:
        target_doc.close()
    meta = {
        "sourcePageCount": len(physical.pages),
        "targetPageCount": target_page_count,
        "sourcePages": source_pages,
        "targetPages": target_pages,
    }
    return _publish_viewer_revision(
        data_dir,
        mapping_text=mapping_text,
        meta_text=json.dumps(meta, indent=2) + "\n",
        source_pdf=source_pdf,
        target_pdf=target_pdf.read_bytes(),
        workspace_updates=workspace_updates,
    )


def _build_translation_provider(
    config: TranslationConfig,
) -> tuple[TranslationProvider | None, str, str, TranslationCache | None]:
    """Build (provider, provider_model, provider_endpoint, cache) from config.

    Shared by ``run_pipeline`` and ``rerender_workspace``. A ``None`` provider
    means the deterministic dummy translator.
    """
    cache: TranslationCache | None = None
    if config.cache_dir is not None:
        cache = TranslationCache(config.cache_dir / "translation-cache.jsonl")
    if config.provider is None:
        return None, DUMMY_PROVIDER_MODEL, "", cache
    provider = create_provider(provider_model="openai-compat", provider_config=config.provider)
    return (
        provider,
        f"openai-compat:{config.provider.model}",
        config.provider.endpoint,
        cache,
    )


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
    provider, provider_model, provider_endpoint, cache = _build_translation_provider(config)
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

    paths: dict[str, Path] = {}
    for name, document in outputs.items():
        path = out_dir / name
        _atomic_write_json(path, dump_document(document))
        paths[name] = path
    # Keep the input bytes in the workspace so rerender_workspace can rebuild
    # viewer assets without the user re-supplying the source PDF.
    source_copy = out_dir / "source.pdf"
    _atomic_write_bytes(source_copy, data)
    paths["source.pdf"] = source_copy
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
        translation=translation,
    )
    paths["viewer-data"] = data_dir
    return paths


def rerender_workspace(
    workspace_dir: Path,
    *,
    viewer_data_dir: Path,
    node_ids: set[str],
    translation_config: TranslationConfig | None = None,
) -> list[str]:
    """Re-translate `node_ids` in a finished workspace and rebuild render output.

    FR-TRANS-004: the source PDF is never re-parsed — physical/layout/semantic/
    mapping geometry is loaded from the workspace and only the translation,
    render document, target PDF, render anchors, and viewer assets are rebuilt.
    Compile, anchor recovery, and bundle validation finish against a staging
    build directory; workspace JSON and the viewer revision are published only
    after that succeeds. Failure leaves the previous complete version in place.
    Returns the sorted re-translated node ids.
    """
    documents = {
        name: load_document(kind, json.loads((workspace_dir / name).read_text(encoding="utf-8")))
        for name, kind in _WORKSPACE_KINDS.items()
    }
    physical = cast("PhysicalDocument", documents["physical.json"])
    layout = cast("LayoutDocument", documents["layout.json"])
    semantic = cast("SemanticDocument", documents["semantic.json"])
    translation = cast("generated.TranslationLayer", documents["translation.json"])
    mapping = cast("generated.MappingBundle", documents["mapping.json"])
    resources = cast("generated.ResourceDocument", documents["resources.json"])

    translatable = {entry.semanticNodeId for entry in translation.entries}
    unknown = node_ids - translatable
    if unknown:
        raise ValueError(f"not re-translatable nodes: {sorted(unknown)}")

    config = translation_config or load_translation_config()
    provider, provider_model, provider_endpoint, cache = _build_translation_provider(config)
    if provider is None and translation_requires_provider(translation):
        raise TranslationProviderNotConfiguredError
    new_translation = retranslate_nodes(
        semantic,
        translation,
        node_ids,
        provider,
        cache=cache,
        provider_model=provider_model,
        provider_endpoint=provider_endpoint,
        skip_cache_read=True,
    )
    render = compose_render_document(
        semantic,
        new_translation,
        profile=DEFAULT_PROFILE,
        policy=DEFAULT_POLICY,
        resources=resources.resources,
    )
    tex = project_to_latex(render, resource_dir=workspace_dir / "resources")
    staging_build = workspace_dir / "build" / f".rerender-{uuid.uuid4().hex}"
    try:
        target_pdf = compile_latex(tex, staging_build)
        render_anchors = recover_render_anchors(target_pdf, semantic)
        new_mapping = build_mapping_bundle(
            semantic,
            source_anchors=mapping.sourceAnchors,
            source_semantic_bindings=mapping.sourceSemanticBindings,
            physical_layout_bindings=mapping.physicalLayoutBindings,
            render_anchors=render_anchors,
            render_document_id=render_target_document_id(render),
        )
        bundle = {
            "physical": dump_document(physical),
            "layout": dump_document(layout),
            "semantic": dump_document(semantic),
            "translation": dump_document(new_translation),
            "render": dump_document(render),
            "mappings": dump_document(new_mapping),
        }
        issues = validate_bundle_references(bundle)
        if issues:
            raise RuntimeError(f"bundle reference issues: {issues}")

        workspace_updates = {
            workspace_dir / name: (
                json.dumps(dump_document(document), indent=2, ensure_ascii=False) + "\n"
            ).encode()
            for name, document in (
                ("translation.json", new_translation),
                ("render.json", render),
                ("mapping.json", new_mapping),
            )
        }
        _write_viewer_assets(
            data_dir=viewer_data_dir,
            source_pdf=(workspace_dir / "source.pdf").read_bytes(),
            target_pdf=target_pdf,
            mapping=new_mapping,
            render_anchors=render_anchors,
            physical=physical,
            layout=layout,
            semantic=semantic,
            translation=new_translation,
            workspace_updates=workspace_updates,
        )
    finally:
        shutil.rmtree(staging_build, ignore_errors=True)
    return sorted(node_ids)


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
