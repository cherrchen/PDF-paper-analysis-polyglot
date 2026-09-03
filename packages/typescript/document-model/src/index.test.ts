import { describe, expect, it } from "vitest";
import { SCHEMA_STATUS, version } from "./index.js";

describe("document-model", () => {
  it("reports unresolved schema ownership", () => {
    expect(SCHEMA_STATUS).toBe("unresolved");
    expect(version).toBe("0.0.0");
  });
});
