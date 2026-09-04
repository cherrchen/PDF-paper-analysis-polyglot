"""Phase 2.5 + 2.6: generated.RenderDocument -> LaTeX projection and compile.

The projection layer is the dedicated boundary between the semantic model
and ``templates/latex/generic-academic.tex`` (see the LaTeX render-model
Agent Note): the template owns presentation, the projection owns structure,
and no TeX ever leaks into canonical semantic or translation content.

RenderAnchor support (Phase 2.6): every block's body is preceded by a
``\\renderanchor{<nodeId>}`` marker whose hypertarget lands in the compiled
PDF, so targets can be recovered from the target PDF's link annotations.
"""

from __future__ import annotations

import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

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
    """Normalize extracted controls and escape TeX special characters."""
    escaped: list[str] = []
    for char in text:
        if char in "\r\n\t":
            escaped.append(" ")
        elif unicodedata.category(char) == "Cc":
            # PDFium may emit non-rendering extraction markers such as U+0002
            # at line-end hyphenation boundaries. They are not valid TeX text.
            continue
        else:
            escaped.append(_TEX_SPECIALS.get(char, char))
    return "".join(escaped)


def project_to_latex(render: generated.RenderDocument) -> str:
    """Project a canonical RenderDocument into a generic-academic document."""
    template_path = _template_path()
    template = template_path.read_text(encoding="utf-8")
    body = _project_body(render)
    if TEMPLATE_BODY_MARKER not in template:
        raise ValueError(f"template missing {TEMPLATE_BODY_MARKER!r} marker")
    return template.replace(TEMPLATE_BODY_MARKER, body)


def _project_body(render: generated.RenderDocument) -> str:
    lines: list[str] = []
    for block in render.blocks:
        lines.append(f"\\renderanchor{{{block.semanticNodeIds[0]}}}%")
        if block.renderKind == "HEADING":
            command = ("section", "subsection", "subsubsection")[block.level - 1]
            lines.append(f"\\{command}{{{escape_latex(block.content.text)}}}")
        elif block.renderKind == "PARAGRAPH":
            lines.append(escape_latex(block.content.text))
            lines.append("")
        elif block.renderKind == "FIGURE":
            lines.append("\\begin{figure}[htbp]\\centering")
            lines.append("\\fbox{\\rule{0.6\\textwidth}{4cm}}")
            if block.caption is not None:
                lines.append(f"\\renderanchor{{{block.semanticNodeIds[1]}}}%")
                lines.append(f"\\caption{{{escape_latex(block.caption.text)}}}")
            lines.append("\\end{figure}")
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
    out_dir = out_dir.resolve()
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


def render_target_document_id(render: generated.RenderDocument) -> str:
    """Return the canonical RenderDocument id bound into render mappings."""
    return render.id
