# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""End-to-end pipeline orchestration (Physical through render + mapping).

PDF -> Physical -> Evidence -> Layout -> Semantic + Translation ->
RenderDocument -> LaTeX -> Target PDF -> RenderAnchor MappingBundle.

Run as a module: ``python -m pdf_pipeline run <input.pdf> <outdir>``.
Outputs seven canonical JSON documents plus the compiled target PDF, the
document probe artifact, and page previews for the viewer.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pypdfium2 as pdfium
from document_model import (
    SCHEMA_VERSION,
    dump_document,
    load_document,
    validate_bundle_references,
)
from document_model.generated import schema_models as generated
from paper_llm import translate_document
from paper_llm.cache import TranslationCache
from paper_llm.config import TranslationConfig, load_translation_config
from paper_llm.prompt import TRANSLATION_PROMPT_VERSION
from paper_llm.translation import (
    DUMMY_PROVIDER_MODEL,
    TranslationProviderNotConfiguredError,
    create_provider,
    retranslate_nodes,
    translation_requires_provider,
)

from pdf_pipeline.capabilities import load_registry, registry_fingerprint
from pdf_pipeline.evidence.docling import (
    DOCLING_CMD_ENV,
    DOCLING_DUMP_ENV,
    DOCLING_PROVIDER,
)
from pdf_pipeline.evidence.grobid import GROBID_DUMP_ENV, GROBID_PROVIDER, GROBID_URL_ENV
from pdf_pipeline.evidence.mineru import (
    MINERU_CMD_ENV,
    MINERU_DUMP_ENV,
    MINERU_PROVIDER,
)
from pdf_pipeline.evidence.native import resolve_dump_path
from pdf_pipeline.evidence.normalize import merge_evidence_bundles
from pdf_pipeline.fusion import RegionLine
from pdf_pipeline.geometry import as_rect
from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.layout import LAYOUT_PRODUCER_VERSION, recover_layout_document
from pdf_pipeline.physical import PRODUCER_VERSION as PHYSICAL_PRODUCER_VERSION
from pdf_pipeline.physical import extract_physical_document, probe_input_capability
from pdf_pipeline.probe import PRODUCER_VERSION as PROBE_VERSION
from pdf_pipeline.probe import probe_document
from pdf_pipeline.render_anchor import (
    build_mapping_bundle,
    recover_render_anchors,
)
from pdf_pipeline.render_composer import DEFAULT_POLICY, DEFAULT_PROFILE, compose_render_document
from pdf_pipeline.render_latex import (
    compile_latex,
    project_to_latex,
    render_target_document_id,
    template_fingerprint,
)
from pdf_pipeline.resource_store import (
    attach_figure_pdf_fragments,
    bind_figure_image_resources,
    extract_resource_document,
)
from pdf_pipeline.routing import ROUTING_VERSION, collect_bundles, route_providers
from pdf_pipeline.sem_validate import validate_semantic_recovery
from pdf_pipeline.semantic import SEMANTIC_PRODUCER_VERSION, recover_semantic_document
from pdf_pipeline.workspace import (
    STAGE_ORDER,
    Stage,
    WorkspaceManager,
    sha256_bytes,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from document_model.generated.schema_models import (
        LayoutDocument,
        PhysicalDocument,
        SemanticDocument,
    )
    from paper_llm.types import TranslationProvider
    from pydantic import BaseModel

PIPELINE_VERSION = "0.1.0"

# Stage-level producer versions for stages without a dedicated module
# constant. TRANSLATE piggybacks on the prompt version: it is the knob
# that changes translation behavior for the dummy and real providers.
RENDER_STAGE_VERSION = "0.1.0"
INDEX_STAGE_VERSION = "0.1.0"

STAGE_PRODUCER_VERSIONS: dict[Stage, str] = {
    Stage.INGEST: PIPELINE_VERSION,
    Stage.PHYSICAL: PHYSICAL_PRODUCER_VERSION,
    Stage.EVIDENCE: ROUTING_VERSION,
    Stage.LAYOUT: LAYOUT_PRODUCER_VERSION,
    Stage.SEMANTIC: SEMANTIC_PRODUCER_VERSION,
    Stage.TRANSLATE: TRANSLATION_PROMPT_VERSION,
    Stage.RENDER: RENDER_STAGE_VERSION,
    Stage.INDEX: INDEX_STAGE_VERSION,
}


class StageExecutionError(RuntimeError):
    """A stage raised while executing; carries the stage for job attribution."""

    stage: Stage

    def __init__(self, stage: Stage, cause: BaseException) -> None:
        super().__init__(f"{stage.value} stage failed: {cause}")
        self.stage = stage


def _execute_stage[T](stage: Stage, action: Callable[[], T]) -> T:
    """Run one stage body, tagging any failure with the stage that raised.

    The job layer needs to know *which* stage failed to attribute the issue
    and to decide whether a retry can resume from the batch A stage state.
    """
    try:
        return action()
    except Exception as error:
        raise StageExecutionError(stage, error) from error


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


def _canonical_artifact(document: BaseModel) -> bytes:
    """Canonical document as workspace artifact bytes (indent-2 JSON + newline)."""
    return (json.dumps(dump_document(document), indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _json_artifact(payload: object) -> bytes:
    """Ad-hoc JSON (probe.json class, outside frozen schemas) as artifact bytes."""
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _load_canonical(path: Path, kind: str) -> object:
    """Load a canonical document previously committed to the workspace."""
    return load_document(kind, json.loads(path.read_text(encoding="utf-8")))


def _load_evidence_bundles(path: Path) -> list[generated.EvidenceBundle]:
    """Load the per-provider bundles persisted by the EVIDENCE stage."""
    items = json.loads(path.read_text(encoding="utf-8"))
    return [cast("generated.EvidenceBundle", load_document("evidence", item)) for item in items]


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


def _provider_identity(config: TranslationConfig) -> tuple[str, str]:
    """Provider model identity and endpoint used for cache keys and entries.

    Single source shared by ``_build_translation_provider`` (which records it
    on ``TranslationLayer.providerModel``) and ``stage_config_inputs`` (which
    keys TRANSLATE on it), so a stage record can never disagree with the layer
    it produced.
    """
    if config.provider is None:
        return DUMMY_PROVIDER_MODEL, ""
    return f"openai-compat:{config.provider.model}", config.provider.endpoint


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
    provider_model, provider_endpoint = _provider_identity(config)
    if config.provider is None:
        return None, provider_model, provider_endpoint, cache
    provider = create_provider(provider_model="openai-compat", provider_config=config.provider)
    return provider, provider_model, provider_endpoint, cache


# Parser inputs whose identity the EVIDENCE cache key covers: recorded dumps
# (content-hashed) and live-parser environment (literal value). Every real
# adapter participates regardless of routing, which needs a probe to narrow;
# over-invalidating costs one rerun, a false hit would be silent staleness.
_PARSER_DUMP_INPUTS: tuple[tuple[str, str], ...] = (
    (MINERU_PROVIDER, MINERU_DUMP_ENV),
    (DOCLING_PROVIDER, DOCLING_DUMP_ENV),
    (GROBID_PROVIDER, GROBID_DUMP_ENV),
)
_PARSER_LIVE_INPUTS: tuple[str, ...] = (MINERU_CMD_ENV, DOCLING_CMD_ENV, GROBID_URL_ENV)


def _file_digest(path: Path | None) -> str:
    """sha256 of a configured file; ``none``/``unreadable`` are distinct states."""
    if path is None:
        return "none"
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return "unreadable"


def _parser_config_inputs(source_fingerprint: str) -> dict[str, str]:
    """Dump digests and live-parser environment for the EVIDENCE cache key.

    Dumps are resolved exactly as the adapters resolve them (explicit env path,
    else ``PAPER_PARSER_DUMP_DIR/<provider>/<fingerprint>.*``), so changing the
    recorded parser output — not just the environment — reruns evidence.
    """
    config: dict[str, str] = {}
    for provider, dump_env in _PARSER_DUMP_INPUTS:
        env_dump = os.environ.get(dump_env)
        path = resolve_dump_path(provider, source_fingerprint, Path(env_dump) if env_dump else None)
        config[f"parserDump:{provider}"] = _file_digest(path)
    for cmd_env in _PARSER_LIVE_INPUTS:
        config[f"liveEnv:{cmd_env}"] = os.environ.get(cmd_env, "")
    return config


def stage_config_inputs(
    config: TranslationConfig, source_bytes: bytes
) -> dict[Stage, dict[str, str]]:
    """Every stage's configuration inputs, i.e. non-artifact parts of its cache key.

    ``schemaVersion``/``pipelineVersion`` are common to all stages: the
    canonical document contract and this driver's code, so a schema or stage
    code change reruns the chain. The rest is per-stage — capability registry
    and parser dumps for EVIDENCE/LAYOUT, translation target for TRANSLATE,
    render profile/policy and LaTeX template for RENDER.

    Deliberately excluded: API key, timeout, retry count, cache directory —
    they do not change produced artifacts, only how the provider is reached.
    """
    common = {"schemaVersion": SCHEMA_VERSION, "pipelineVersion": PIPELINE_VERSION}
    registry_input = {"capabilityRegistry": registry_fingerprint()}
    provider_model, provider_endpoint = _provider_identity(config)
    per_stage: dict[Stage, dict[str, str]] = {
        Stage.EVIDENCE: {
            **registry_input,
            **_parser_config_inputs(sha256_bytes(source_bytes)),
        },
        Stage.LAYOUT: dict(registry_input),
        Stage.TRANSLATE: {
            "targetLocale": config.target_locale,
            "sourceLocale": config.source_locale or "",
            "providerModel": provider_model,
            "providerEndpoint": provider_endpoint,
            "terminologyFile": _file_digest(config.terminology_file),
        },
        Stage.RENDER: {
            "renderProfile": sha256_bytes(DEFAULT_PROFILE.model_dump_json().encode("utf-8")),
            "renderPolicy": sha256_bytes(DEFAULT_POLICY.model_dump_json().encode("utf-8")),
            "latexTemplate": template_fingerprint(),
        },
    }
    return {stage: {**common, **per_stage.get(stage, {})} for stage in STAGE_ORDER}


def _bind_figure_assets(
    semantic: generated.SemanticDocument,
    layout: generated.LayoutDocument,
    physical: generated.PhysicalDocument,
    pdf_bytes: bytes,
    resource_dir: Path,
) -> tuple[generated.SemanticDocument, generated.ResourceDocument]:
    """Extract rasters, bind them, then crop PDF fragments for figures."""
    resources = extract_resource_document(pdf_bytes, resource_dir=resource_dir)
    semantic = bind_figure_image_resources(semantic, layout, resources.resources)
    return attach_figure_pdf_fragments(
        semantic,
        layout,
        physical,
        pdf_bytes,
        resource_dir=resource_dir,
        resources=resources,
    )


def _run_ingest_stage(workspace: WorkspaceManager, source_bytes: bytes) -> None:
    """INGEST: keep the source PDF bytes in the workspace.

    The fingerprint covers no upstream artifacts on purpose: the source
    binding lives in the manifest's ``sourceFingerprint``.
    """
    workspace.commit_stage(
        Stage.INGEST,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.INGEST],
        artifacts={"source.pdf": source_bytes},
    )


def _run_physical_stage(workspace: WorkspaceManager, source_bytes: bytes) -> PhysicalDocument:
    physical = extract_physical_document(source_bytes)
    workspace.commit_stage(
        Stage.PHYSICAL,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.PHYSICAL],
        artifacts={"physical.json": _canonical_artifact(physical)},
    )
    return physical


def _run_evidence_stage(
    workspace: WorkspaceManager, physical: PhysicalDocument
) -> tuple[list[generated.EvidenceBundle], generated.EvidenceBundle]:
    """Probe, route, and collect per-provider bundles plus the merged bundle.

    The per-provider bundles persist in the ad-hoc ``evidence-bundles.json``
    so a resumed LAYOUT stage does not rerun evidence providers.
    """
    registry = load_registry()
    probe = probe_document(physical)
    plan = route_providers(probe, registry)
    bundles = collect_bundles(plan, physical)
    evidence = merge_evidence_bundles(bundles)
    workspace.commit_stage(
        Stage.EVIDENCE,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.EVIDENCE],
        artifacts={
            "evidence.json": _canonical_artifact(evidence),
            "evidence-bundles.json": _json_artifact([dump_document(b) for b in bundles]),
            "probe.json": _json_artifact(
                {
                    "probeVersion": PROBE_VERSION,
                    "routingVersion": ROUTING_VERSION,
                    **probe.to_json(),
                    "routing": plan.to_json(),
                }
            ),
        },
    )
    return bundles, evidence


def _run_layout_stage(
    workspace: WorkspaceManager,
    physical: PhysicalDocument,
    bundles: list[generated.EvidenceBundle],
) -> LayoutDocument:
    layout = recover_layout_document(physical, evidence=bundles, registry=load_registry())
    workspace.commit_stage(
        Stage.LAYOUT,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.LAYOUT],
        artifacts={"layout.json": _canonical_artifact(layout)},
    )
    return layout


def _run_semantic_stage(
    workspace: WorkspaceManager,
    source_bytes: bytes,
    out_dir: Path,
    *,
    physical: PhysicalDocument,
    layout: LayoutDocument,
    evidence: generated.EvidenceBundle,
) -> tuple[SemanticDocument, generated.ResourceDocument]:
    """Recover semantics, validate, then bind figure resources.

    Figure binding lives here rather than in RENDER so ``semantic.json``
    has a single owner: the persisted document is the figure-bound one,
    exactly what render, mapping, and the viewer have always consumed.
    """
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
    resource_dir = out_dir / "resources"
    # The SEMANTIC record declares every file under resources/, so a stale
    # raster or figure fragment from an earlier run or source would be
    # recorded as current output. Drop the directory first and let figure
    # binding repopulate it.
    shutil.rmtree(resource_dir, ignore_errors=True)
    semantic, resources = _bind_figure_assets(
        semantic, layout, physical, source_bytes, resource_dir
    )
    workspace.commit_stage(
        Stage.SEMANTIC,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.SEMANTIC],
        artifacts={
            "semantic.json": _canonical_artifact(semantic),
            "resources.json": _canonical_artifact(resources),
            **_directory_artifacts(resource_dir, "resources"),
        },
    )
    return semantic, resources


def _run_translation_stage(
    workspace: WorkspaceManager,
    semantic: SemanticDocument,
    config: TranslationConfig,
) -> generated.TranslationLayer:
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
    workspace.commit_stage(
        Stage.TRANSLATE,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.TRANSLATE],
        artifacts={"translation.json": _canonical_artifact(translation)},
    )
    return translation


def _directory_artifacts(root: Path, prefix: str) -> dict[str, bytes]:
    """Every file under root as a workspace artifact named ``prefix/<relpath>``."""
    if not root.is_dir():
        return {}
    return {
        f"{prefix}/{path.relative_to(root).as_posix()}": path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run_render_stage(
    workspace: WorkspaceManager,
    *,
    semantic: SemanticDocument,
    translation: generated.TranslationLayer,
    resources: generated.ResourceDocument,
    out_dir: Path,
) -> tuple[generated.RenderDocument, Path]:
    """Compose the render document and compile the target PDF."""
    resource_dir = out_dir / "resources"
    render = compose_render_document(
        semantic,
        translation,
        profile=DEFAULT_PROFILE,
        policy=DEFAULT_POLICY,
        resources=resources.resources,
    )
    tex = project_to_latex(render, resource_dir=resource_dir)
    target_pdf = compile_latex(tex, out_dir / "build")
    workspace.commit_stage(
        Stage.RENDER,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.RENDER],
        artifacts={
            "render.json": _canonical_artifact(render),
            "target.pdf": target_pdf.read_bytes(),
        },
    )
    return render, out_dir / "target.pdf"


def _viewer_receipt(data_dir: Path) -> bytes:
    manifest = _read_viewer_manifest(data_dir)
    if manifest is None:
        raise ValueError("missing viewer manifest")
    revision = manifest["revision"]
    names = ("mapping.json", "viewer-meta.json", "source.pdf", "target.pdf")
    paths = ["manifest.json", *names, *(f"revisions/{revision}/{name}" for name in names)]
    return _json_artifact(
        {
            "directory": str(data_dir.resolve()),
            "artifacts": {name: sha256_bytes((data_dir / name).read_bytes()) for name in paths},
        }
    )


def _viewer_current(out_dir: Path, data_dir: Path) -> bool:
    try:
        return (out_dir / "viewer-publication.json").read_bytes() == _viewer_receipt(data_dir)
    except (OSError, ValueError):
        return False


def _run_index_stage(
    workspace: WorkspaceManager,
    source_bytes: bytes,
    *,
    physical: PhysicalDocument,
    layout: LayoutDocument,
    semantic: SemanticDocument,
    translation: generated.TranslationLayer,
    render: generated.RenderDocument,
    evidence: generated.EvidenceBundle,
    target_pdf: Path,
    viewer_data_dir: Path,
) -> generated.MappingBundle:
    """Render anchors, mapping bundle, bundle validation, viewer publish."""
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
    _write_viewer_assets(
        data_dir=viewer_data_dir,
        source_pdf=source_bytes,
        target_pdf=target_pdf,
        mapping=mapping,
        render_anchors=render_anchors,
        physical=physical,
        layout=layout,
        semantic=semantic,
        translation=translation,
    )
    workspace.commit_stage(
        Stage.INDEX,
        producer_version=STAGE_PRODUCER_VERSIONS[Stage.INDEX],
        artifacts={
            "mapping.json": _canonical_artifact(mapping),
            "viewer-publication.json": _viewer_receipt(viewer_data_dir),
        },
    )
    return mapping


def _ensure_analysis_stages(
    workspace: WorkspaceManager, source_bytes: bytes, out_dir: Path
) -> tuple[
    PhysicalDocument,
    LayoutDocument,
    SemanticDocument,
    generated.ResourceDocument,
    generated.EvidenceBundle,
]:
    """Run or reload INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC."""
    if not workspace.stage_completed(Stage.INGEST, STAGE_PRODUCER_VERSIONS[Stage.INGEST]):
        _execute_stage(Stage.INGEST, lambda: _run_ingest_stage(workspace, source_bytes))

    if workspace.stage_completed(Stage.PHYSICAL, STAGE_PRODUCER_VERSIONS[Stage.PHYSICAL]):
        physical = cast(
            "PhysicalDocument", _load_canonical(out_dir / "physical.json", "physical-document")
        )
    else:
        physical = _execute_stage(
            Stage.PHYSICAL, lambda: _run_physical_stage(workspace, source_bytes)
        )

    if workspace.stage_completed(Stage.EVIDENCE, STAGE_PRODUCER_VERSIONS[Stage.EVIDENCE]):
        bundles = _load_evidence_bundles(out_dir / "evidence-bundles.json")
        evidence = cast(
            "generated.EvidenceBundle", _load_canonical(out_dir / "evidence.json", "evidence")
        )
    else:
        bundles, evidence = _execute_stage(
            Stage.EVIDENCE, lambda: _run_evidence_stage(workspace, physical)
        )

    if workspace.stage_completed(Stage.LAYOUT, STAGE_PRODUCER_VERSIONS[Stage.LAYOUT]):
        layout = cast("LayoutDocument", _load_canonical(out_dir / "layout.json", "layout-document"))
    else:
        layout = _execute_stage(
            Stage.LAYOUT, lambda: _run_layout_stage(workspace, physical, bundles)
        )

    if workspace.stage_completed(Stage.SEMANTIC, STAGE_PRODUCER_VERSIONS[Stage.SEMANTIC]):
        semantic = cast(
            "SemanticDocument", _load_canonical(out_dir / "semantic.json", "semantic-document")
        )
        resources = cast(
            "generated.ResourceDocument", _load_canonical(out_dir / "resources.json", "resources")
        )
    else:
        semantic, resources = _execute_stage(
            Stage.SEMANTIC,
            lambda: _run_semantic_stage(
                workspace,
                source_bytes,
                out_dir,
                physical=physical,
                layout=layout,
                evidence=evidence,
            ),
        )
    return physical, layout, semantic, resources, evidence


def _ensure_rebuild_stages(
    workspace: WorkspaceManager,
    *,
    semantic: SemanticDocument,
    resources: generated.ResourceDocument,
    config: TranslationConfig,
    out_dir: Path,
) -> tuple[generated.TranslationLayer, generated.RenderDocument, Path]:
    """Run or reload TRANSLATE and RENDER.

    Returns the translation, the render document, and the compiled target
    PDF path.
    """
    if workspace.stage_completed(Stage.TRANSLATE, STAGE_PRODUCER_VERSIONS[Stage.TRANSLATE]):
        translation = cast(
            "generated.TranslationLayer",
            _load_canonical(out_dir / "translation.json", "translation-layer"),
        )
    else:
        translation = _execute_stage(
            Stage.TRANSLATE, lambda: _run_translation_stage(workspace, semantic, config)
        )

    if workspace.stage_completed(Stage.RENDER, STAGE_PRODUCER_VERSIONS[Stage.RENDER]):
        render = cast(
            "generated.RenderDocument", _load_canonical(out_dir / "render.json", "render-document")
        )
        target_pdf = out_dir / "target.pdf"
    else:
        render, target_pdf = _execute_stage(
            Stage.RENDER,
            lambda: _run_render_stage(
                workspace,
                semantic=semantic,
                translation=translation,
                resources=resources,
                out_dir=out_dir,
            ),
        )
    return translation, render, target_pdf


def run_pipeline(
    source_pdf: Path,
    out_dir: Path,
    *,
    viewer_data_dir: Path | None = None,
    translation_config: TranslationConfig | None = None,
    rerun_from: Stage | None = None,
    accept_source_change: bool = False,
) -> dict[str, Path]:
    """Run the Walking Skeleton pipeline into a resumable local workspace.

    Each stage (INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC →
    TRANSLATE → RENDER → INDEX) commits its artifacts and its manifest
    record atomically (``workspace.json`` written last). A restart skips
    stages whose recorded artifacts still verify and whose cache key
    (producer version + upstream artifacts + stage config) still matches, and
    reruns only the rest, so completed JSON/PDF artifacts survive an
    interrupted run and a half-written stage is never accepted as success.

    ``rerun_from`` drops that stage and every downstream record before
    running, an explicit local rerun. Source PDF bytes differing from the
    manifest raise ``WorkspaceSourceMismatchError`` unless
    ``accept_source_change`` is set, which rebinds the workspace and reruns
    every stage. Returns produced artifact paths.
    """
    source_bytes = source_pdf.read_bytes()
    out_dir.mkdir(parents=True, exist_ok=True)
    config = translation_config or load_translation_config()
    workspace = WorkspaceManager(out_dir, stage_configs=stage_config_inputs(config, source_bytes))
    workspace.open_or_create(source_bytes, accept_source_change=accept_source_change)
    if rerun_from is not None:
        workspace.invalidate_from(rerun_from)

    capability = probe_input_capability(source_bytes)
    if not capability.usable:
        # FR-PDF-002: fail loudly at the entry point rather than silently
        # producing low-quality recovery output for scanned documents.
        raise ValueError(f"unsupported input PDF: {capability.reason}")

    physical, layout, semantic, resources, evidence = _ensure_analysis_stages(
        workspace, source_bytes, out_dir
    )
    translation, render, target_pdf = _ensure_rebuild_stages(
        workspace,
        semantic=semantic,
        resources=resources,
        config=config,
        out_dir=out_dir,
    )

    data_dir = viewer_data_dir or out_dir / "viewer" / "data"
    if not workspace.stage_completed(
        Stage.INDEX, STAGE_PRODUCER_VERSIONS[Stage.INDEX]
    ) or not _viewer_current(out_dir, data_dir):
        _execute_stage(
            Stage.INDEX,
            lambda: _run_index_stage(
                workspace,
                source_bytes,
                physical=physical,
                layout=layout,
                semantic=semantic,
                translation=translation,
                render=render,
                evidence=evidence,
                target_pdf=target_pdf,
                viewer_data_dir=data_dir,
            ),
        )

    paths: dict[str, Path] = {
        name: out_dir / name
        for name in (
            "physical.json",
            "evidence.json",
            "layout.json",
            "semantic.json",
            "translation.json",
            "render.json",
            "mapping.json",
            "resources.json",
            "source.pdf",
            "target.pdf",
            "probe.json",
        )
    }
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
    source_bytes = (workspace_dir / "source.pdf").read_bytes()
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
        workspace_updates[workspace_dir / "target.pdf"] = target_pdf.read_bytes()
        if (workspace_dir / "workspace.json").is_file():
            workspace = WorkspaceManager(
                workspace_dir, stage_configs=stage_config_inputs(config, source_bytes)
            )
            workspace.open_or_create(source_bytes)
            for stage, names in (
                (Stage.TRANSLATE, ("translation.json",)),
                (Stage.RENDER, ("render.json", "target.pdf")),
            ):
                workspace.stages[stage] = workspace.make_stage_record(
                    stage,
                    producer_version=STAGE_PRODUCER_VERSIONS[stage],
                    artifacts={
                        name: sha256_bytes(workspace_updates[workspace_dir / name])
                        for name in names
                    },
                )
            workspace.drop_stage_records(Stage.INDEX)
            workspace_updates[workspace.manifest_path] = workspace.manifest_bytes()
        _write_viewer_assets(
            data_dir=viewer_data_dir,
            source_pdf=source_bytes,
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
    parser.add_argument(
        "--rerun-from",
        choices=[stage.value for stage in STAGE_ORDER],
        type=Stage,
        default=None,
        help="drop this stage and every downstream stage record before running",
    )
    parser.add_argument(
        "--accept-source-change",
        action="store_true",
        help="rebind the workspace to different source PDF bytes and rerun every stage",
    )
    args = parser.parse_args(argv)
    paths = run_pipeline(
        args.input,
        args.outdir,
        viewer_data_dir=args.viewer_data_dir,
        rerun_from=args.rerun_from,
        accept_source_change=args.accept_source_change,
    )
    sys.stdout.write(json.dumps({name: str(path) for name, path in paths.items()}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
