import { describe, expect, it } from "vitest";
import { workspaceLabel } from "./index.js";

describe("ui", () => {
  it("exposes the workspace label", () => {
    expect(workspaceLabel()).toBe("PDF Paper Analysis");
  });
});
