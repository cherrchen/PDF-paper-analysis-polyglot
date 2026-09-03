# Security

## Disclosure

Report vulnerabilities privately to the maintainers. Do not file public GitHub issues for undisclosed security problems.

## Secrets

Never commit credentials, API keys, tokens, or private keys. Application environment files are not present until a runtime actually needs configuration. When they exist, only `.env.example` with non-secret placeholders may be committed.

## Dependencies

Dependency vulnerabilities are handled through Renovate, `cargo deny`, and GitHub dependency review. Do not add a second overlapping updater for the same ecosystems.

## Supported expectations

This repository is pre-1.0. Security fixes are applied on `main`. There are no published package artifacts yet.

## License boundary

The project is source-available under MIT plus Non-Commercial additional terms. A security report does not grant commercial rights.
