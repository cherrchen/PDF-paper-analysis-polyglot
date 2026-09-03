import { describe, expect, it } from "vitest";
import { clientStatus } from "./index.js";

describe("api-client", () => {
  it("reports bootstrap status", () => {
    expect(clientStatus).toBe("ok");
  });
});
