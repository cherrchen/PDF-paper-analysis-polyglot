import { afterEach, describe, expect, it, vi } from "vitest";
import { bootImportPanel, type ImportPanelElements } from "./import-panel.js";
import { DualPaneReader } from "./reader.js";

type FetchHandler = (url: string, init?: RequestInit) => Promise<Response>;

type Panel = ImportPanelElements & { clicks: Array<() => void> };

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function fakeElements(): Panel {
  const clicks: Array<() => void> = [];
  return {
    source: { value: "" } as unknown as HTMLInputElement,
    workspace: { value: "" } as unknown as HTMLInputElement,
    submit: {
      disabled: false,
      addEventListener: (_type: string, listener: () => void) => clicks.push(listener),
    } as unknown as HTMLButtonElement,
    status: { textContent: "" } as unknown as HTMLElement,
    clicks,
  };
}

function fakeReader(overrides: Partial<DualPaneReader> = {}): DualPaneReader {
  return Object.assign(Object.create(DualPaneReader.prototype), {
    apiAvailable: true,
    load: vi.fn(async () => undefined),
    ...overrides,
  }) as DualPaneReader;
}

function stubFetch(handler: FetchHandler): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init)),
  );
}

function expectStatus(panel: Panel, text: string, timeout = 6000): Promise<void> {
  return vi.waitFor(
    () => {
      expect(String(panel.status.textContent)).toContain(text);
    },
    { timeout },
  );
}

function click(panel: Panel): void {
  panel.clicks[0]?.();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("bootImportPanel", () => {
  it("disables submit and reports offline when the API is unavailable", () => {
    const panel = fakeElements();
    bootImportPanel(fakeReader({ apiAvailable: false }), panel);

    expect(panel.submit.disabled).toBe(true);
    expect(panel.status.textContent).toBe("Import unavailable · API offline");
  });

  it("submits absolute paths without viewerDataDir, polls, and reloads once", async () => {
    const panel = fakeElements();
    panel.source.value = "/tmp/paper.pdf";
    panel.workspace.value = "/tmp/ws";
    const reader = fakeReader();
    let polls = 0;
    let submitBody = "";
    stubFetch(async (url, init) => {
      if (url === "/api/jobs" && init?.method === "POST") {
        submitBody = String(init.body);
        return jsonResponse({ ok: true, job: { id: "a".repeat(32), status: "queued" } });
      }
      if (url === `/api/jobs/${"a".repeat(32)}`) {
        polls += 1;
        return jsonResponse({
          ok: true,
          job: { id: "a".repeat(32), status: polls >= 2 ? "succeeded" : "running" },
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    bootImportPanel(reader, panel);

    click(panel);
    await expectStatus(panel, "Job submitted");
    await expectStatus(panel, "Job succeeded");

    expect(JSON.parse(submitBody)).toEqual({ source: "/tmp/paper.pdf", workspace: "/tmp/ws" });
    expect(reader.load).toHaveBeenCalledOnce();
    expect(polls).toBe(2);
    expect(panel.submit.disabled).toBe(false);
  });

  it("renders stage and error on a failed job without reloading", async () => {
    const panel = fakeElements();
    panel.source.value = "/tmp/paper.pdf";
    panel.workspace.value = "/tmp/ws";
    const reader = fakeReader();
    stubFetch(async (url) => {
      if (url === "/api/jobs") {
        return jsonResponse({ ok: true, job: { id: "b".repeat(32), status: "queued" } });
      }
      return jsonResponse({
        ok: true,
        job: {
          id: "b".repeat(32),
          status: "failed",
          stage: "RENDER",
          error: "lualatex exited 1",
        },
      });
    });
    bootImportPanel(reader, panel);

    click(panel);
    await expectStatus(panel, "Job failed · RENDER · lualatex exited 1");

    expect(reader.load).not.toHaveBeenCalled();
  });

  it("keeps the previous revision when the reload fails", async () => {
    const panel = fakeElements();
    panel.source.value = "/tmp/paper.pdf";
    panel.workspace.value = "/tmp/ws";
    const reader = fakeReader({
      load: vi.fn(async () => {
        throw new Error("manifest missing");
      }),
    });
    stubFetch(async (url) => {
      if (url === "/api/jobs") {
        return jsonResponse({ ok: true, job: { id: "c".repeat(32), status: "queued" } });
      }
      return jsonResponse({ ok: true, job: { id: "c".repeat(32), status: "succeeded" } });
    });
    bootImportPanel(reader, panel);

    click(panel);
    await expectStatus(panel, "Reload failed · Error: manifest missing");

    expect(reader.load).toHaveBeenCalledOnce();
  });

  it("rejects relative paths before touching the API", async () => {
    const panel = fakeElements();
    panel.source.value = "paper.pdf";
    panel.workspace.value = "/tmp/ws";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    bootImportPanel(fakeReader(), panel);

    click(panel);
    await expectStatus(panel, "must be absolute", 1000);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
