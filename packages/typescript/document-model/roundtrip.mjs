#!/usr/bin/env node
/**
 * CLI for cross-language roundtrip validation. Used by the Python
 * integration tests (tests/integration) to complete the chain:
 *
 *   Python serialize -> JSON -> TS validate/parse -> JSON -> Python parse
 *
 * Usage:
 *   node roundtrip.mjs <schema-name> <document.json> [out.json]
 *
 * Exits non-zero if the document fails canonical validation.
 */

import { readFileSync, writeFileSync } from "node:fs";
// Import validate.ts (not src/index.ts) so no generated-module imports are pulled in.
import { validateDocument } from "./src/validate.ts";

const [schemaName, inputFile, outputFile] = process.argv.slice(2);

if (!schemaName || !inputFile) {
  console.error("usage: node roundtrip.mjs <schema-name> <document.json> [out.json]");
  process.exit(2);
}

let document;
try {
  document = JSON.parse(readFileSync(inputFile, "utf8"));
} catch (error) {
  console.error(`cannot read document: ${error instanceof Error ? error.message : error}`);
  process.exit(2);
}

const errors = validateDocument(
  schemaName,
  /** @type {import("./src/index.js").JsonValue} */ (document),
);

if (errors.length > 0) {
  console.error("validation failed:");
  for (const error of errors) {
    console.error(`  ${error.pointer || "<root>"}: ${error.message}`);
  }
  process.exit(1);
}

// Normalized re-serialization is byte-stable for canonical documents.
const serialized = `${JSON.stringify(document, null, 2)}\n`;
if (outputFile) {
  writeFileSync(outputFile, serialized, "utf8");
} else {
  process.stdout.write(serialized);
}
