"""Phase 2.5 + M5: generated.RenderDocument -> LaTeX projection and compile."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pdf_pipeline.math_latex import equation_to_latex
from pdf_pipeline.tex_escape import escape_latex

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

__all__ = [
    "LATEX_PRODUCER",
    "TEMPLATE_BODY_MARKER",
    "TEMPLATE_PROFILE_MARKER",
    "anchor_end_name",
    "compile_latex",
    "escape_latex",
    "project_to_latex",
    "render_target_document_id",
]

TEMPLATE_BODY_MARKER = "% BODY"
TEMPLATE_PROFILE_MARKER = "% PROFILE"
LATEX_PRODUCER = "pdf-pipeline.render-latex"
_ANCHOR_END_SUFFIX = ":end"
_MISSING_FIGURE = (
    r"\fbox{\parbox{0.6\textwidth}{\centering\vspace{1.2cm}[figure unavailable]\vspace{1.2cm}}}"
)
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bin")


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
    resource_ids = list(block.resourceIds or [])
    width = _figure_image_width(policy)
    graphics = [
        _graphic_for_resource(resource_dir, resource_id, width) for resource_id in resource_ids
    ]
    if not graphics:
        inner.append(_MISSING_FIGURE)
    else:
        inner.extend(graphics)
    caption_position = _caption_position("figure", policy)
    caption_lines: list[str] = []
    if block.caption is not None and len(block.semanticNodeIds) > 1:
        caption_lines = _caption_lines(
            "figure",
            block.caption.text,
            block.semanticNodeIds[1],
            floating=_figure_is_float(policy),
        )
    if caption_position == "ABOVE":
        inner[1:1] = caption_lines
    else:
        inner.extend(caption_lines)
    inner.append(f"\\renderanchorend{{{node_id}}}%")
    return [*_figure_wrapper_open(policy), *inner, _figure_wrapper_close(policy)]


def _figure_is_float(policy: generated.RenderPolicy) -> bool:
    return bool(policy.floatFigures) and (policy.wideFigureHandling or "SCALE_DOWN") != "INLINE"


def _figure_image_width(policy: generated.RenderPolicy) -> str:
    handling = policy.wideFigureHandling or "SCALE_DOWN"
    if handling == "WIDE_FLOAT":
        return r"\textwidth"
    return r"0.8\textwidth"


def _figure_wrapper_open(policy: generated.RenderPolicy) -> list[str]:
    if not _figure_is_float(policy):
        return [r"\begin{center}"]
    if policy.wideFigureHandling == "WIDE_FLOAT":
        return [r"\begin{figure*}[htbp]\centering"]
    return [r"\begin{figure}[htbp]\centering"]


def _figure_wrapper_close(policy: generated.RenderPolicy) -> str:
    if not _figure_is_float(policy):
        return r"\end{center}"
    if policy.wideFigureHandling == "WIDE_FLOAT":
        return r"\end{figure*}"
    return r"\end{figure}"


def _graphic_for_resource(resource_dir: Path | None, resource_id: str, width: str) -> str:
    if resource_dir is None:
        return _MISSING_FIGURE
    for extension in _IMAGE_EXTENSIONS:
        candidate = resource_dir / f"{resource_id}{extension}"
        if candidate.is_file():
            image_path = candidate.resolve().as_posix()
            return f"\\includegraphics[width={width}]{{{image_path}}}"
    return _MISSING_FIGURE


def _caption_position(kind: str, policy: generated.RenderPolicy) -> str:
    position = policy.captionPosition
    if position == "ABOVE":
        return "ABOVE"
    if position == "SOURCE":
        return "ABOVE" if kind == "table" else "BELOW"
    return "BELOW"


def _project_table(block: generated.RenderTableBlock, policy: generated.RenderPolicy) -> list[str]:
    table = block.table
    columns = max(table.columns, 1)
    alignments = cast(
        "list[generated.ColumnAlignment]",
        list(block.columnAlignments) if block.columnAlignments else ["LEFT"] * columns,
    )
    overflow = policy.tableOverflowHandling
    wide = overflow == "WIDE_FLOAT"
    floating = bool(policy.floatTables)
    node_id = block.semanticNodeIds[0]
    caption_id = block.semanticNodeIds[-1] if len(block.semanticNodeIds) > 1 else None
    lines = [_table_wrapper_open(floating=floating, wide=wide)]
    lines.append(f"\\renderanchor{{{node_id}}}%")
    caption_position = _caption_position("table", policy)
    if block.caption is not None and caption_position == "ABOVE":
        lines.extend(_caption_lines("table", block.caption.text, caption_id, floating=floating))
    tabular = _tabular_lines(table, alignments, columns, wrap=overflow == "WRAP")
    if overflow == "SCALE_FONT":
        lines.append("\\fitbox{%")
        lines.extend(tabular)
        lines.append("}")
    elif overflow == "FAIL":
        lines.append("\\sbox{\\fitcontentbox}{%")
        lines.extend(tabular)
        lines.append("}")
        lines.append(
            r"\ifdim\wd\fitcontentbox>\linewidth"
            r"\errmessage{table overflow with FAIL policy}\fi"
        )
        lines.append(r"\usebox{\fitcontentbox}")
    else:
        lines.extend(tabular)
    if block.caption is not None and caption_position != "ABOVE":
        lines.extend(_caption_lines("table", block.caption.text, caption_id, floating=floating))
    lines.append(f"\\renderanchorend{{{node_id}}}%")
    lines.append(_table_wrapper_close(floating=floating, wide=wide))
    return lines


def _table_wrapper_open(*, floating: bool, wide: bool) -> str:
    if floating and wide:
        return r"\begin{table*}[htbp]\centering"
    if floating:
        return r"\begin{table}[htbp]\centering"
    return r"\begin{center}"


def _table_wrapper_close(*, floating: bool, wide: bool) -> str:
    if floating and wide:
        return r"\end{table*}"
    if floating:
        return r"\end{table}"
    return r"\end{center}"


def _tabular_lines(
    table: generated.TableContent,
    alignments: list[generated.ColumnAlignment] | tuple[generated.ColumnAlignment, ...],
    columns: int,
    *,
    wrap: bool = False,
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
    if wrap:
        col_width = rf"\dimexpr(\linewidth-{2 * columns}\tabcolsep)/{columns}\relax"
        spec = "".join(f"p{{{col_width}}}" for _ in range(columns))
    else:
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
            text, consumed = _table_cell_tex(cell, padded, column, wrap=wrap)
            parts.append(text)
            column += consumed
        lines.append(" & ".join(parts) + " \\\\")
    lines.append("\\end{tabular}")
    return lines


def _table_cell_tex(
    cell: generated.TableCell,
    padded: list[generated.ColumnAlignment],
    column: int,
    *,
    wrap: bool,
) -> tuple[str, int]:
    align_char = {"LEFT": "l", "CENTER": "c", "RIGHT": "r"}
    text = escape_latex(cell.content.text)
    if cell.rowSpan > 1:
        text = rf"\multirow{{{cell.rowSpan}}}{{*}}{{{text}}}"
    if cell.colSpan > 1:
        align = "p{\\linewidth}" if wrap else align_char.get(padded[column], "l")
        return rf"\multicolumn{{{cell.colSpan}}}{{{align}}}{{{text}}}", cell.colSpan
    return f"{{{text}}}", 1


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
    handling = policy.longEquationHandling
    if handling in {"SCALE_DOWN", "MULTILINE"}:
        body = rf"\fitmath{{{body}}}"
    elif handling == "TRUNCATE":
        body = rf"\makebox[\linewidth][l]{{\ensuremath{{\displaystyle {body}}}}}"
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
