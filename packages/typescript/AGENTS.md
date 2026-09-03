# TypeScript packages

## Ownership

Reusable TypeScript lives here, not under `apps/web/shared/`.

- `@paper/document-model` — TS view of SemanticDocument. Canonical schema is `schemas/`.
- `@paper/api-client` — HTTP client. Wire contracts belong in `schemas/api/`.
- `@paper/ui` — shared UI.

Import across packages with workspace names (`@paper/...`). Do not add path aliases that hide package boundaries.

## Typing

`strict`, `noUncheckedIndexedAccess`, and `noImplicitOverride` are required. TypeScript owns type correctness. Biome is not a substitute for `tsc`.

## Browser / server

Keep DOM-only code in `@paper/ui` or `apps/web`. Keep Node-only code out of UI packages unless the export path is explicitly server-only.

## Public API

Each package exports a small, deliberate surface through `src/index.ts`.

## Biome

Biome owns formatting, linting, and import organization for TypeScript, JavaScript, JSON, and CSS. Do not add Prettier or a large ESLint config without an Agent Note.

## Schema ownership

Do not independently maintain an authoritative SemanticDocument in TypeScript.
