/**
 * Runtime validation of canonical documents against the JSON Schemas in
 * schemas/. The validator implements the JSON Schema subset the canonical
 * schemas use: type, required, additionalProperties, properties, items,
 * enum, const, oneOf, anyOf, $ref (intra- and cross-document), pattern,
 * minimum/maximum, minItems, minLength, exclusiveMinimum.
 *
 * Cross-document $refs such as "../common/schema.json#/$defs/Rect" are
 * resolved against the schema root directory.
 */

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface JsonSchemaNode {
  $ref?: string;
  type?: string | string[];
  properties?: Record<string, JsonSchemaNode>;
  required?: string[];
  additionalProperties?: boolean | JsonSchemaNode;
  items?: JsonSchemaNode;
  enum?: JsonValue[];
  const?: JsonValue;
  oneOf?: JsonSchemaNode[];
  anyOf?: JsonSchemaNode[];
  pattern?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  minItems?: number;
  minLength?: number;
  $defs?: Record<string, JsonSchemaNode>;
  description?: string;
}

export interface ValidationError {
  pointer: string;
  message: string;
}

interface SchemaBundle {
  byId: Map<string, JsonSchemaNode>;
}

import { readFileSync, statSync } from "node:fs";
import path from "node:path";

const SCHEMA_NAMES = [
  "common",
  "physical-document",
  "evidence",
  "layout-document",
  "semantic-document",
  "mapping",
] as const;

export type SchemaName = (typeof SCHEMA_NAMES)[number];

const schemaCache = new Map<SchemaName, JsonSchemaNode>();

/** Locate the repository's schemas/ directory by walking up from the cwd. */
export function findSchemaRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    const candidate = path.join(dir, "schemas");
    try {
      if (statSync(candidate).isDirectory()) {
        return candidate;
      }
    } catch {
      // keep walking up
    }
    dir = path.dirname(dir);
  }
  throw new Error("schemas/ directory not found");
}

function loadSchemaFile(name: SchemaName): JsonSchemaNode {
  const cached = schemaCache.get(name);
  if (cached) {
    return cached;
  }
  const schemaPath = path.join(findSchemaRoot(), name, "schema.json");
  const schema = JSON.parse(readFileSync(schemaPath, "utf8")) as JsonSchemaNode;
  schemaCache.set(name, schema);
  return schema;
}

function resolveRef(
  ref: string,
  current: JsonSchemaNode,
  bundle: SchemaBundle,
): { node: JsonSchemaNode; document: JsonSchemaNode } {
  if (ref.startsWith("#/")) {
    // intra-document pointer: #/$defs/Name
    const parts = ref.slice(2).split("/");
    let node: JsonSchemaNode = current;
    for (const part of parts) {
      const defs = node.$defs ?? {};
      const next = defs[part] ?? (node as unknown as Record<string, JsonSchemaNode>)[part];
      if (!next) {
        throw new Error(`unresolvable intra-document ref: ${ref}`);
      }
      node = next;
    }
    return { node, document: current };
  }
  // cross-document: ../common/schema.json#/$defs/Rect
  const [file, pointer] = ref.split("#");
  if (file === undefined) {
    throw new Error(`unresolvable schema ref: ${ref}`);
  }
  const match = file.match(/([a-z-]+)\/schema\.json$/);
  if (!match) {
    throw new Error(`unresolvable schema ref: ${ref}`);
  }
  const schemaName = match[1] as SchemaName;
  const target = bundle.byId.get(schemaName) ?? loadSchemaFile(schemaName);
  bundle.byId.set(schemaName, target);
  if (!pointer) {
    return { node: target, document: target };
  }
  const parts = pointer.replace(/^\/\$defs\//, "").split("/");
  let node: JsonSchemaNode = target;
  const defs = node.$defs ?? {};
  for (const part of parts) {
    const next = defs[part];
    if (!next) {
      throw new Error(`unresolvable pointer in ref: ${ref}`);
    }
    node = next;
  }
  return { node, document: target };
}

function validateAgainst(
  value: JsonValue,
  schema: JsonSchemaNode,
  current: JsonSchemaNode,
  bundle: SchemaBundle,
  pointer: string,
  errors: ValidationError[],
): void {
  let node = schema;
  let document = current;
  while (node.$ref) {
    const resolved = resolveRef(node.$ref, document, bundle);
    // intra-document pointers stay in the same document; cross-document
    // refs return the target document so nested pointers resolve there
    node = resolved.node;
    document = resolved.document;
  }

  if (node.oneOf) {
    const matches = node.oneOf.filter((variant) => {
      const sub: ValidationError[] = [];
      validateAgainst(value, variant, document, bundle, pointer, sub);
      return sub.length === 0;
    });
    if (matches.length !== 1) {
      errors.push({
        pointer,
        message: `expected exactly one oneOf match, got ${matches.length}`,
      });
      return;
    }
    return;
  }

  if (node.anyOf) {
    const matches = node.anyOf.filter((variant) => {
      const sub: ValidationError[] = [];
      validateAgainst(value, variant, document, bundle, pointer, sub);
      return sub.length === 0;
    });
    if (matches.length === 0) {
      errors.push({ pointer, message: "value matches none of anyOf variants" });
    }
    return;
  }

  if (node.enum) {
    if (!node.enum.some((candidate) => JSON.stringify(candidate) === JSON.stringify(value))) {
      errors.push({ pointer, message: `value not in enum: ${JSON.stringify(value)}` });
    }
    return;
  }

  if (node.const !== undefined) {
    if (JSON.stringify(node.const) !== JSON.stringify(value)) {
      errors.push({ pointer, message: `const mismatch: expected ${JSON.stringify(node.const)}` });
    }
    return;
  }

  if (typeof node.type === "string" || Array.isArray(node.type)) {
    const types = Array.isArray(node.type) ? node.type : [node.type];
    if (!types.some((t) => typeMatches(value, t))) {
      errors.push({ pointer, message: `expected type ${types.join("|")}, got ${typeof value}` });
      return;
    }
  }

  if (typeof value === "string") {
    if (node.pattern && !new RegExp(node.pattern).test(value)) {
      errors.push({ pointer, message: `string does not match pattern ${node.pattern}` });
    }
    if (node.minLength !== undefined && value.length < node.minLength) {
      errors.push({ pointer, message: `string shorter than minLength ${node.minLength}` });
    }
  }

  if (typeof value === "number") {
    if (node.minimum !== undefined && value < node.minimum) {
      errors.push({ pointer, message: `number below minimum ${node.minimum}` });
    }
    if (node.maximum !== undefined && value > node.maximum) {
      errors.push({ pointer, message: `number above maximum ${node.maximum}` });
    }
    if (node.exclusiveMinimum !== undefined && value <= node.exclusiveMinimum) {
      errors.push({
        pointer,
        message: `number not above exclusiveMinimum ${node.exclusiveMinimum}`,
      });
    }
  }

  if (Array.isArray(value)) {
    if (node.minItems !== undefined && value.length < node.minItems) {
      errors.push({ pointer, message: `array shorter than minItems ${node.minItems}` });
    }
    if (node.items) {
      value.forEach((item, index) => {
        validateAgainst(
          item,
          node.items as JsonSchemaNode,
          document,
          bundle,
          `${pointer}/${index}`,
          errors,
        );
      });
    }
    return;
  }

  if (typeof value === "object" && value !== null) {
    const properties = node.properties ?? {};
    const required = node.required ?? [];
    for (const key of required) {
      if (!(key in value)) {
        errors.push({ pointer, message: `missing required property ${key}` });
      }
    }
    const record = value as { [key: string]: JsonValue };
    for (const [key, child] of Object.entries(record)) {
      const propertySchema = properties[key];
      if (propertySchema) {
        validateAgainst(child, propertySchema, document, bundle, `${pointer}/${key}`, errors);
      } else {
        const additional = node.additionalProperties;
        if (additional === false) {
          errors.push({
            pointer: `${pointer}/${key}`,
            message: "additional properties are not allowed",
          });
        } else if (typeof additional === "object") {
          validateAgainst(child, additional, document, bundle, `${pointer}/${key}`, errors);
        }
      }
    }
  }
}

function typeMatches(value: JsonValue, type: string): boolean {
  switch (type) {
    case "string":
      return typeof value === "string";
    case "number":
      return typeof value === "number";
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "boolean":
      return typeof value === "boolean";
    case "null":
      return value === null;
    case "array":
      return Array.isArray(value);
    case "object":
      return typeof value === "object" && value !== null && !Array.isArray(value);
    default:
      return false;
  }
}

/**
 * Validate a parsed JSON document against one of the canonical schemas.
 * Returns all violations; an empty array means the document is valid.
 */
export function validateDocument(schemaName: SchemaName, document: JsonValue): ValidationError[] {
  const schema = loadSchemaFile(schemaName);
  const bundle: SchemaBundle = { byId: new Map([[schemaName, schema]]) };
  const errors: ValidationError[] = [];
  validateAgainst(document, schema, schema, bundle, "", errors);
  return errors;
}
