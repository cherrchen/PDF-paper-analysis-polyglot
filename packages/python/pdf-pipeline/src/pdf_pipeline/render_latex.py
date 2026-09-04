"""Phase 2.5 + 2.6: generated.SemanticDocument -> LaTeX projection and compile.

The projection layer is the dedicated boundary between the semantic model
and ``templates/latex/generic-academic.tex`` (see the LaTeX render-model
Agent Note): the template owns presentation, the projection owns structure,
and no TeX ever leaks into generated.SemanticDocument.

RenderAnchor support (Phase 2.6): every node's body is preceded by a
``\\renderanchor{<nodeId>}`` marker whose hypertarget lands in the compiled
PDF, so targets can be recovered from the target PDF's link annotations.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

TEMPLATE_BODY_MARKER = "% BODY"
LATEX_PRODUCER = "pdf-pipeline.render-latex"

_TEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    """Escape TeX special characters; text content must survive verbatim."""
    return "".join(_TEX_SPECIALS.get(char, char) for char in text)


def _iter_nodes(semantic: generated.SemanticDocument) -> Iterator:
    by_id = {node.id: node for node in semantic.nodes}

    def walk(node_id: str) -> Iterator:
        node = by_id[node_id]
        for child_id in node.children:
            child = by_id[child_id]
            yield child
            yield from walk(child.id)

    yield from walk(semantic.rootId)


def _node_heading_level(node: generated.SemanticNode) -> int:
    level = node.attributes.get("level")
    return level if isinstance(level, int) and 1 <= level <= 3 else 1


def project_to_latex(semantic: generated.SemanticDocument) -> str:
    """Project a generated.SemanticDocument into a full generic-academic document."""
    template_path = _template_path()
    template = template_path.read_text(encoding="utf-8")
    body = _project_body(semantic)
    if TEMPLATE_BODY_MARKER not in template:
        raise ValueError(f"template missing {TEMPLATE_BODY_MARKER!r} marker")
    return template.replace(TEMPLATE_BODY_MARKER, body)


def _project_body(semantic: generated.SemanticDocument) -> str:
    lines: list[str] = []
    for node in _iter_nodes(semantic):
        # RenderAnchor marker: identity of the node in the target PDF.
        lines.append(f"\\renderanchor{{{node.id}}}%")
        content = node.content
        if node.kind == "HEADING":
            level = _node_heading_level(node)
            command = ("section", "subsection", "subsubsection")[level - 1]
            lines.append(f"\\{command}{{{escape_latex(content.text)}}}")
        elif node.kind in {"PARAGRAPH", "FIGURE_CAPTION"}:
            if node.kind == "FIGURE_CAPTION":
                lines.append("\\begin{figure}[htbp]\\centering")
                lines.append(f"\\caption{{{escape_latex(content.text)}}}")
                lines.append("\\end{figure}")
            else:
                lines.append(escape_latex(content.text))
                lines.append("")
        elif node.kind == "FIGURE":
            lines.append("\\begin{figure}[htbp]\\centering")
            lines.append("\\fbox{\\rule{0.6\\textwidth}{4cm}}")
            lines.append("\\end{figure}")
        elif node.kind == "DOCUMENT":
            continue
        else:
            # Unknown kinds still get their anchor; content falls back to text.
            text = getattr(content, "text", None)
            if text:
                lines.append(escape_latex(text))
                lines.append("")
    return "\n".join(lines)


def _repo_root() -> Path:
    # packages/python/pdf-pipeline/src/pdf_pipeline/render_latex.py -> repo root
    return Path(__file__).resolve().parents[5]


def _template_path() -> Path:
    return _repo_root() / "templates/latex/generic-academic.tex"


def compile_latex(tex_source: str, out_dir: Path, job_name: str = "target") -> Path:
    """Compile LaTeX source with LuaLaTeX; return the produced PDF path."""
    lualatex = shutil.which("lualatex")
    if lualatex is None:
        raise RuntimeError("lualatex not found; run `just doctor`")
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{job_name}.tex"
    tex_path.write_text(tex_source, encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, path from caller
        [
            lualatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            f"-jobname={job_name}",
            "-output-directory",
            str(out_dir),
            str(tex_path),
        ],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    pdf_path = out_dir / f"{job_name}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        tail = "\n".join(completed.stdout.splitlines()[-25:])
        raise RuntimeError(f"lualatex failed for {tex_path}:\n{tail}")
    return pdf_path


def render_target_document_id(semantic: generated.SemanticDocument) -> str:
    """Stable target-document id bound into render bindings."""
    return stable_uuid(semantic.id, "render-document")
