"""Phase 2.5 + M5: generated.RenderDocument -> LaTeX projection and compile."""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pdf_pipeline.math_latex import equation_to_latex

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

TEMPLATE_BODY_MARKER = "% BODY"
TEMPLATE_PROFILE_MARKER = "% PROFILE"
LATEX_PRODUCER = "pdf-pipeline.render-latex"
_ANCHOR_END_SUFFIX = ":end"
_MISSING_FIGURE = (
    r"\fbox{\parbox{0.6\textwidth}{\centering\vspace{1.2cm}[figure unavailable]\vspace{1.2cm}}}"
)

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
    policy = render.policy
    for block in render.blocks:
        if block.renderKind == "BIBLIOGRAPHY":
            lines.extend(_project_bibliography(block))
            continue
        if block.renderKind == "FIGURE":
            lines.extend(_project_figure(block, resource_dir=resource_dir, policy=policy))
            continue
        if block.renderKind == "TABLE":
            lines.extend(_project_table(block, policy))
            continue
        node_id = block.semanticNodeIds[0]
        lines.append(f"\\renderanchor{{{node_id}}}%")
        if block.renderKind == "HEADING":
            command = ("section", "subsection", "subsubsection")[block.level - 1]
            lines.append(f"\\{command}{{{escape_latex(block.content.text)}}}")
        elif block.renderKind == "PARAGRAPH":
            lines.append(escape_latex(block.content.text))
            lines.append("")
        elif block.renderKind == "EQUATION":
            lines.extend(_project_equation(block, policy))
        lines.append(f"\\renderanchorend{{{node_id}}}%")
    return "\n".join(lines)


def _project_figure(
    block: generated.RenderFigureBlock,
    *,
    resource_dir: Path | None,
    policy: generated.RenderPolicy,
) -> list[str]:
    node_id = block.semanticNodeIds[0]
    inner = [f"\\renderanchor{{{node_id}}}%"]
    graphic = _MISSING_FIGURE
    if resource_dir is not None and block.resourceIds:
        resource_id = block.resourceIds[0]
        for extension in (".png", ".jpg", ".jpeg", ".webp", ".bin"):
            candidate = resource_dir / f"{resource_id}{extension}"
            if candidate.is_file():
                image_path = candidate.resolve().as_posix()
                graphic = f"\\includegraphics[width=0.8\\textwidth]{{{image_path}}}"
                break
    inner.append(graphic)
    if block.caption is not None and len(block.semanticNodeIds) > 1:
        inner.extend(
            _caption_lines(
                "figure",
                block.caption.text,
                block.semanticNodeIds[1],
                floating=bool(policy.floatFigures),
            )
        )
    inner.append(f"\\renderanchorend{{{node_id}}}%")
    if policy.floatFigures:
        return ["\\begin{figure}[htbp]\\centering", *inner, "\\end{figure}"]
    return ["\\begin{center}", *inner, "\\end{center}"]


def _project_table(block: generated.RenderTableBlock, policy: generated.RenderPolicy) -> list[str]:
    table = block.table
    columns = max(table.columns, 1)
    alignments = cast(
        "list[generated.ColumnAlignment]",
        list(block.columnAlignments) if block.columnAlignments else ["LEFT"] * columns,
    )
    floating = bool(policy.floatTables)
    node_id = block.semanticNodeIds[0]
    caption_id = block.semanticNodeIds[-1] if len(block.semanticNodeIds) > 1 else None
    lines = ["\\begin{table}[htbp]\\centering"] if floating else ["\\begin{center}"]
    lines.append(f"\\renderanchor{{{node_id}}}%")
    if block.caption is not None and policy.captionPosition == "ABOVE":
        lines.extend(_caption_lines("table", block.caption.text, caption_id, floating=floating))
    tabular = _tabular_lines(table, alignments, columns)
    if policy.tableOverflowHandling == "SCALE_FONT":
        lines.append("\\fitbox{%")
        lines.extend(tabular)
        lines.append("}")
    else:
        lines.extend(tabular)
    if block.caption is not None and policy.captionPosition != "ABOVE":
        lines.extend(_caption_lines("table", block.caption.text, caption_id, floating=floating))
    lines.append(f"\\renderanchorend{{{node_id}}}%")
    lines.append("\\end{table}" if floating else "\\end{center}")
    return lines


def _tabular_lines(
    table: generated.TableContent,
    alignments: list[generated.ColumnAlignment] | tuple[generated.ColumnAlignment, ...],
    columns: int,
) -> list[str]:
    inferred_columns = max(
        (cell.column + cell.colSpan for cell in table.cells),
        default=columns,
    )
    columns = max(columns, inferred_columns, 1)
    rows = max(table.rows, 0)
    inferred_rows = max((cell.row + cell.rowSpan for cell in table.cells), default=0)
    rows = max(rows, inferred_rows)
    align_char = {"LEFT": "l", "CENTER": "c", "RIGHT": "r"}
    padded = list(alignments[:columns])
    while len(padded) < columns:
        padded.append("LEFT")
    spec = "".join(align_char.get(align, "l") for align in padded)
    origins: dict[tuple[int, int], generated.TableCell] = {}
    covered: set[tuple[int, int]] = set()
    for cell in table.cells:
        origins[(cell.row, cell.column)] = cell
        for row_delta in range(cell.rowSpan):
            for col_delta in range(cell.colSpan):
                if row_delta == 0 and col_delta == 0:
                    continue
                covered.add((cell.row + row_delta, cell.column + col_delta))
    lines = [f"\\begin{{tabular}}{{{spec}}}"]
    for row_index in range(rows):
        parts: list[str] = []
        column = 0
        while column < columns:
            if (row_index, column) in covered:
                parts.append("{}")
                column += 1
                continue
            cell = origins.get((row_index, column))
            if cell is None:
                parts.append("{}")
                column += 1
                continue
            text = escape_latex(cell.content.text)
            if cell.rowSpan > 1:
                text = rf"\multirow{{{cell.rowSpan}}}{{*}}{{{text}}}"
            if cell.colSpan > 1:
                align = align_char.get(padded[column], "l")
                text = rf"\multicolumn{{{cell.colSpan}}}{{{align}}}{{{text}}}"
                parts.append(text)
                column += cell.colSpan
                continue
            parts.append(f"{{{text}}}")
            column += 1
        lines.append(" & ".join(parts) + " \\\\")
    lines.append("\\end{tabular}")
    return lines


def _caption_lines(
    kind: str,
    text: str,
    caption_id: str | None,
    *,
    floating: bool,
) -> list[str]:
    command = r"\caption" if floating else rf"\captionof{{{kind}}}"
    lines: list[str] = []
    if caption_id is not None:
        lines.append(f"\\renderanchor{{{caption_id}}}%")
    lines.append(f"{command}{{{escape_latex(text)}}}")
    if caption_id is not None:
        lines.append(f"\\renderanchorend{{{caption_id}}}%")
    return lines


def _project_equation(
    block: generated.RenderEquationBlock, policy: generated.RenderPolicy
) -> list[str]:
    body = equation_to_latex(block.equation)
    if policy.longEquationHandling == "SCALE_DOWN":
        body = rf"\fitmath{{{body}}}"
    if block.equation.number:
        tagged = rf"{body} \tag{{{escape_latex(block.equation.number)}}}"
        return ["\\begin{equation}", tagged, "\\end{equation}"]
    return [rf"\[{body}\]"]


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
