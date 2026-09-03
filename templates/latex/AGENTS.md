# LaTeX templates

## Ownership

`templates/latex/` owns first-party presentation and template rules.

SemanticDocument remains the canonical semantic model. Generated LaTeX is a rendering representation, not semantic truth.

## Engine

LuaLaTeX is the default. XeLaTeX is allowed only for a documented compatibility need. Do not make pdfLaTeX the multilingual renderer.

## Formatting

`latexindent` formats first-party `.tex` files in this tree and in repository-authored fixtures.

Do not auto-format vendored or external academic templates.

## Linting

ChkTeX runs against first-party sources. Suppressions must be narrow, local, and documented. Do not globally disable useful warnings because one journal template triggers them.

## Regression

Template changes require `just latex-check` and `just latex-smoke`. Update fixtures and golden data only when the contract intentionally changed.

## Generated content

Do not commit latexmk auxiliary files. Do not hardcode one-paper hacks into generic templates.
