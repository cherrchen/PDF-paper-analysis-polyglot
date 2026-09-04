/**
 * TypeScript view of the canonical document contracts.
 *
 * Types in `./generated/schema.js` mirror the schemas in schemas/<layer>/schema.json and must
 * not be edited by hand. Runtime validation reads the canonical JSON Schemas
 * directly, so the generated types and the contract cannot drift.
 */

export * as generated from "./generated/schema.js";
export {
  findSchemaRoot,
  type JsonSchemaNode,
  type JsonValue,
  type SchemaName,
  type ValidationError,
  validateDocument,
} from "./validate.js";

export const SCHEMA_VERSION = "0.1.0" as const;
