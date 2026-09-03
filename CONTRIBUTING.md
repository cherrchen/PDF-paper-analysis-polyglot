# Contributing

## Workflow

1. Install [mise](https://mise.jdx.dev/), then `mise install`.
2. Run `just setup` and `just doctor`.
3. Create a branch from `main`: `feat/*`, `fix/*`, `refactor/*`, `docs/*`, `ci/*`, or `chore/*`.
4. Use `just` commands. Do not invent parallel scripts.
5. Open a pull request. Squash merge into `main`.

Details: [`docs/development/workflow.md`](docs/development/workflow.md) ([English](docs/development/workflow.en.md)).

README, `docs/`, and Agent Notes are Chinese-primary with English `*.en.md` companions. See [`docs/development/bilingual.md`](docs/development/bilingual.md) ([English](docs/development/bilingual.en.md)).

## Checks

- Pre-commit: formatting, lint of staged files, typos, bilingual docs, Agent Notes, `git diff --cached --check`
- Pre-push: `just check-fast`
- PR CI: `CI / gate`

## Agent Notes

Non-trivial architecture, contract, process, or testing changes need an Agent Note pair. See [`.agents/notes/README.md`](.agents/notes/README.md) ([English](.agents/notes/README.en.md)).

## License

Contributions are under the repository [`LICENSE`](LICENSE): MIT plus Non-Commercial additional terms.
