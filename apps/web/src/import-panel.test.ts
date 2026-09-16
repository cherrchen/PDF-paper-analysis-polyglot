import { afterEach, describe, expect, it, vi } from "vitest";
import { bootImportPanel, type ImportPanelElements } from "./import-panel.js";
import { DualPaneReader } from "./reader.js";

type FetchHandler = (url: string, init?: RequestInit) => Promise<Response>;

type ElementKey = keyof ImportPanelElements;
type Listener = (event: unknown) => void;

type Panel = ImportPanelElements & {
  fire: (key: ElementKey, type: string, event?: unknown) => void;
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Minimal element doubles. Listeners are captured per element and event type so
 * a test drives the panel through the same entry points a user does.
 */
function fakeElements(): Panel {
  const listeners: Array<{ key: ElementKey; type: string; listener: Listener }> = [];
  const host = (key: ElementKey, extra: Record<string, unknown>): object => ({
    ...extra,
    addEventListener: (type: string, listener: Listener) => {
      listeners.push({ key, type, listener });
    },
  });
  return {
    source: host("source", { value: "" }),
    workspace: host("workspace", { value: "" }),
    submit: host("submit", { disabled: false }),
    status: host("status", { textContent: "" }),
    file: host("file", { files: [] }),
    drop: host("drop", {}),
    uploadStatus: host("uploadStatus", { textContent: "" }),
    fire(key: ElementKey, type: string, event?: unknown): void {
      for (const entry of listeners) {
        if (entry.key === key && entry.type === type) entry.listener(event);
      }
    },
  } as unknown as Panel;
}

/** The two fields the drop handler reads off a DragEvent. */
function dropEvent(file: File): unknown {
  return { preventDefault: () => undefined, dataTransfer: { files: [file] } };
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
  panel.fire("submit", "click");
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

  it("keeps following a slow job instead of giving up on the client", async () => {
    // A real paper on a real provider runs for minutes (the reference 11-page
    // paper took ~10), so the panel follows the job record to its terminal
    // state instead of abandoning the import on a client-side deadline.
    vi.useFakeTimers();
    try {
      const panel = fakeElements();
      panel.source.value = "/tmp/paper.pdf";
      panel.workspace.value = "/tmp/ws";
      const reader = fakeReader();
      const jobId = "d".repeat(32);
      let polls = 0;
      stubFetch(async (url) => {
        if (url === "/api/jobs") {
          return jsonResponse({ ok: true, job: { id: jobId, status: "queued" } });
        }
        polls += 1;
        return jsonResponse({
          ok: true,
          job: { id: jobId, status: polls > 400 ? "succeeded" : "running" },
        });
      });
      bootImportPanel(reader, panel);

      click(panel);
      await vi.advanceTimersByTimeAsync(900_000);

      expect(polls).toBeGreaterThan(400);
      expect(reader.load).toHaveBeenCalledOnce();
      expect(String(panel.status.textContent)).toBe("Job succeeded · reloading viewer");
      expect(panel.submit.disabled).toBe(false);
    } finally {
      vi.useRealTimers();
    }
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

  it("uploads a dropped PDF, fills the derived paths, and starts the job", async () => {
    const panel = fakeElements();
    const reader = fakeReader();
    let submitBody = "";
    stubFetch(async (url, init) => {
      if (url === "/api/uploads") {
        return jsonResponse({
          ok: true,
          path: "/inbox/paper-1a2b3c4d.pdf",
          workspace: "/jobs/workspaces/paper-1a2b3c4d",
          bytes: 12,
        });
      }
      if (url === "/api/jobs" && init?.method === "POST") {
        submitBody = String(init.body);
        return jsonResponse({ ok: true, job: { id: "e".repeat(32), status: "queued" } });
      }
      if (url === `/api/jobs/${"e".repeat(32)}`) {
        return jsonResponse({ ok: true, job: { id: "e".repeat(32), status: "succeeded" } });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    bootImportPanel(reader, panel);

    panel.fire("drop", "drop", dropEvent(new File(["%PDF-1.4\n"], "paper.pdf")));
    await expectStatus(panel, "Job succeeded");

    // The server owns both paths; the panel only displays what it derived.
    expect(panel.source.value).toBe("/inbox/paper-1a2b3c4d.pdf");
    expect(panel.workspace.value).toBe("/jobs/workspaces/paper-1a2b3c4d");
    expect(String(panel.uploadStatus.textContent)).toContain("Uploaded 12 bytes");
    expect(JSON.parse(submitBody)).toEqual({
      source: "/inbox/paper-1a2b3c4d.pdf",
      workspace: "/jobs/workspaces/paper-1a2b3c4d",
    });
    expect(reader.load).toHaveBeenCalledOnce();
  });

  it("rejects a non-PDF drop without calling the API", async () => {
    const panel = fakeElements();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    bootImportPanel(fakeReader(), panel);

    panel.fire("drop", "drop", dropEvent(new File(["hello"], "notes.txt")));

    await vi.waitFor(() => {
      expect(String(panel.uploadStatus.textContent)).toContain("only .pdf");
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
