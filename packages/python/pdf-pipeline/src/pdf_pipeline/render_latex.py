"""Phase 2.5 + M5: generated.RenderDocument -> LaTeX projection and compile."""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

from pdf_pipeline.math_latex import equation_to_latex

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

TEMPLATE_BODY_MARKER = "% BODY"
TEMPLATE_PROFILE_MARKER = "% PROFILE"
LATEX_PRODUCER = "pdf-pipeline.render-latex"
_ANCHOR_END_SUFFIX = ":end"

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
            continue
        else:
            escaped.append(_TEX_SPECIALS.get(char, char))
    return "".join(escaped)


def project_to_latex(
    render: generated.RenderDocument,
    *,
    resource_dir: Path | None = None,
) -> str:
    """Project a canonical RenderDocument into a generic-academic document."""
    template_path = _template_path()
    template = template_path.read_text(encoding="utf-8")
    template = _apply_profile(template, render.profile)
    body = _project_body(render, resource_dir=resource_dir)
    if TEMPLATE_BODY_MARKER not in template:
        raise ValueError(f"template missing {TEMPLATE_BODY_MARKER!r} marker")
    return template.replace(TEMPLATE_BODY_MARKER, body)


def _apply_profile(template: str, profile: generated.RenderProfile) -> str:
    paper = (profile.paperSize or "A4").lower()
    paper_option = "letterpaper" if paper == "letter" else "a4paper"
    font_size = profile.fontSizePt or 11.0
    line_spacing = profile.lineSpacingFactor or 1.25
    profile_block = f"\\linespread{{{line_spacing:g}}}\n"
    if TEMPLATE_PROFILE_MARKER not in template:
        return template
    documentclass_line = "\\" + f"documentclass[{font_size:g}pt,{paper_option}]{{article}}"
    template = re.sub(
        r"[\\]documentclass\[[^\]]*\]\{article\}",
        lambda _match: documentclass_line,
        template,
        count=1,
    )
    return template.replace(TEMPLATE_PROFILE_MARKER, profile_block)


def _project_body(render: generated.RenderDocument, *, resource_dir: Path | None) -> str:
    lines: list[str] = []
    for block in render.blocks:
        if block.renderKind == "BIBLIOGRAPHY":
            lines.extend(_project_bibliography(block))
            continue
        node_id = block.semanticNodeIds[0]
        lines.append(f"\\renderanchor{{{node_id}}}%")
        if block.renderKind == "HEADING":
            command = ("section", "subsection", "subsubsection")[block.level - 1]
            lines.append(f"\\{command}{{{escape_latex(block.content.text)}}}")
        elif block.renderKind == "PARAGRAPH":
            lines.append(escape_latex(block.content.text))
            lines.append("")
        elif block.renderKind == "FIGURE":
            lines.extend(_project_figure(block, resource_dir=resource_dir))
        elif block.renderKind == "TABLE":
            lines.extend(_project_table(block, render.policy))
        elif block.renderKind == "EQUATION":
            lines.extend(_project_equation(block))
        lines.append(f"\\renderanchorend{{{node_id}}}%")
    return "\n".join(lines)


def _project_figure(
    block: generated.RenderFigureBlock,
    *,
    resource_dir: Path | None,
) -> list[str]:
    lines = ["\\begin{figure}[htbp]\\centering"]
    graphic = "\\fbox{\\rule{0.6\\textwidth}{4cm}}"
    if resource_dir is not None and block.resourceIds:
        resource_id = block.resourceIds[0]
        for extension in (".png", ".jpg", ".jpeg", ".webp", ".bin"):
            candidate = resource_dir / f"{resource_id}{extension}"
            if candidate.is_file():
                graphic = f"\\includegraphics[width=0.8\\textwidth]{{{candidate.as_posix()}}}"
                break
    lines.append(graphic)
    if block.caption is not None and len(block.semanticNodeIds) > 1:
        caption_id = block.semanticNodeIds[1]
        lines.append(f"\\renderanchor{{{caption_id}}}%")
        lines.append(f"\\caption{{{escape_latex(block.caption.text)}}}")
        lines.append(f"\\renderanchorend{{{caption_id}}}%")
    lines.append("\\end{figure}")
    return lines


def _project_table(block: generated.RenderTableBlock, policy: generated.RenderPolicy) -> list[str]:
    table = block.table
    columns = max(table.columns, 1)
    alignments = block.columnAlignments or (["LEFT"] * columns)
    align_char = {"LEFT": "l", "CENTER": "c", "RIGHT": "r"}
    spec = "".join(align_char.get(align, "l") for align in alignments)
    lines = ["\\begin{table}[htbp]\\centering"] if policy.floatTables else ["\\begin{center}"]
    if block.caption is not None and policy.captionPosition == "ABOVE":
        caption_id = block.semanticNodeIds[-1] if len(block.semanticNodeIds) > 1 else None
        if caption_id is not None:
            lines.append(f"\\renderanchor{{{caption_id}}}%")
        lines.append(f"\\caption{{{escape_latex(block.caption.text)}}}")
        if caption_id is not None:
            lines.append(f"\\renderanchorend{{{caption_id}}}%")
    lines.append(f"\\begin{{tabular}}{{{spec}}}")
    rows: dict[int, list[generated.TableCell]] = {}
    for cell in table.cells:
        rows.setdefault(cell.row, []).append(cell)
    for row_index in sorted(rows):
        row_cells = sorted(rows[row_index], key=lambda item: item.column)
        lines.append(
            " & ".join(f"{{{escape_latex(cell.content.text)}}}" for cell in row_cells) + " \\\\"
        )
    lines.append("\\end{tabular}")
    if block.caption is not None and policy.captionPosition != "ABOVE":
        caption_id = block.semanticNodeIds[-1] if len(block.semanticNodeIds) > 1 else None
        if caption_id is not None:
            lines.append(f"\\renderanchor{{{caption_id}}}%")
        lines.append(f"\\caption{{{escape_latex(block.caption.text)}}}")
        if caption_id is not None:
            lines.append(f"\\renderanchorend{{{caption_id}}}%")
    lines.append("\\end{table}" if policy.floatTables else "\\end{center}")
    return lines


def _project_equation(block: generated.RenderEquationBlock) -> list[str]:
    body = equation_to_latex(block.equation)
    if block.equation.number:
        return ["\\begin{equation}", body, "\\end{equation}"]
    return [f"\\[{body}\\]"]


def _project_bibliography(block: generated.RenderBibliographyBlock) -> list[str]:
    lines = ["\\begin{thebibliography}{99}"]
    for index, entry in enumerate(block.entries, start=1):
        lines.append(f"\\renderanchor{{{entry.semanticNodeId}}}%")
        lines.append(f"\\bibitem{{{index}}} {escape_latex(entry.content.text)}")
        lines.append(f"\\renderanchorend{{{entry.semanticNodeId}}}%")
    lines.append("\\end{thebibliography}")
    return lines


def _repo_root() -> Path:
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
    completed = subprocess.run(  # noqa: S603
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
    return render.id


def anchor_end_name(node_id: str) -> str:
    return f"{node_id}{_ANCHOR_END_SUFFIX}"
