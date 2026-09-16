/**
 * Select surface: enumerate committed workspaces and open one read-only.
 *
 * `GET /api/workspaces` is a directory listing plus per-workspace summary, so
 * this panel never needs the API to know which workspace is loaded. `Open`
 * republishes the workspace's committed artifacts server-side and then swaps
 * the reader onto the new revision; the client never names a write target.
 */
import { type ApiPayload, openWorkspacePath, readApiJson } from "./jobs-client.js";
import type { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";
import type { SurfaceTabs } from "./surface-tabs.js";

const STAGE_TOTAL = 8;

type WorkspaceEntry = {
  name: string;
  path: string;
  workspaceVersion: string;
  stages: Record<string, string>;
  complete: boolean;
  updatedAt: string;
  error: string | null;
  publication: { current: boolean };
};

function toWorkspaceEntry(value: unknown): WorkspaceEntry | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const record = value as Partial<Record<keyof WorkspaceEntry, unknown>>;
  if (typeof record.name !== "string" || typeof record.path !== "string") return undefined;
  const stages: Record<string, string> = {};
  if (typeof record.stages === "object" && record.stages !== null) {
    for (const [name, status] of Object.entries(record.stages as Record<string, unknown>)) {
      if (typeof status === "string") stages[name] = status;
    }
  }
  const publication = record.publication as { current?: unknown } | undefined;
  return {
    name: record.name,
    path: record.path,
    workspaceVersion: typeof record.workspaceVersion === "string" ? record.workspaceVersion : "",
    stages,
    complete: record.complete === true,
    updatedAt: typeof record.updatedAt === "string" ? record.updatedAt : "",
    error: typeof record.error === "string" ? record.error : null,
    publication: { current: publication?.current === true },
  };
}

async function listWorkspaces(): Promise<WorkspaceEntry[] | undefined> {
  try {
    const response = await fetch("/api/workspaces");
    if (!response.ok) return undefined;
    const payload: ApiPayload = await readApiJson(response);
    if (!Array.isArray(payload.workspaces)) return undefined;
    return payload.workspaces
      .map(toWorkspaceEntry)
      .filter((entry): entry is WorkspaceEntry => entry !== undefined);
  } catch {
    return undefined;
  }
}

/**
 * Republish a committed workspace and swap the reader onto it.
 *
 * Shared by the select and history surfaces: both offer "Open" for a
 * workspace path and report the outcome in their own status line.
 */
export async function openPublishedWorkspace(
  reader: DualPaneReader,
  workspace: string,
  status: HTMLElement,
): Promise<void> {
  const result = await openWorkspacePath(workspace);
  if (!result.ok) {
    status.textContent = `Open failed · ${result.error ?? "unknown error"}`;
    return;
  }
  try {
    await reader.load(String(Date.now()));
  } catch (error) {
    status.textContent = `Open failed · ${String(error)}`;
    return;
  }
  status.textContent = `Opened · ${result.revision?.slice(0, 8) ?? "unknown"}`;
}

function workspaceItem(
  entry: WorkspaceEntry,
  reader: DualPaneReader,
  status: HTMLElement,
  refresh: () => Promise<void>,
): HTMLLIElement {
  const item = document.createElement("li");
  item.dataset.workspace = entry.path;
  item.dataset.current = String(entry.publication.current);

  const name = document.createElement("span");
  name.className = "select-name";
  name.textContent = entry.name;
  const path = document.createElement("span");
  path.className = "select-path";
  path.textContent = entry.path;
  const statuses = Object.values(entry.stages);
  const committed = statuses.filter((value) => value === "completed").length;
  const stages = document.createElement("span");
  stages.className = "select-stages";
  stages.textContent = `${committed}/${STAGE_TOTAL} stages committed${
    statuses.includes("degraded") ? " · degraded" : ""
  }`;
  const updated = document.createElement("span");
  updated.className = "select-updated";
  updated.textContent = entry.updatedAt;

  const open = document.createElement("button");
  open.type = "button";
  open.className = "select-open";
  open.textContent = "Open";
  const blocked =
    entry.error ?? (entry.complete ? undefined : "workspace stages are not committed");
  open.disabled = blocked !== undefined;
  if (blocked !== undefined) open.title = blocked;
  open.addEventListener("click", () => {
    open.disabled = true;
    void (async () => {
      try {
        await openPublishedWorkspace(reader, entry.path, status);
        await refresh();
      } finally {
        if (open.isConnected) open.disabled = false;
      }
    })();
  });

  item.append(name, path, stages, updated);
  if (entry.error !== null) {
    const error = document.createElement("span");
    error.className = "select-error";
    error.textContent = entry.error;
    item.append(error);
  }
  item.append(open);
  return item;
}

export function bootSelectPanel(reader: DualPaneReader, tabs: SurfaceTabs): void {
  const status = requiredElement<HTMLElement>("#select-status");
  const list = requiredElement<HTMLElement>("#select-list");
  const refreshButton = requiredElement<HTMLButtonElement>("#select-refresh");
  // A successful refresh leaves the status line alone: "Opened · …" and
  // "Open failed · …" are the answers the user just asked for.
  const refresh = async (): Promise<void> => {
    const entries = await listWorkspaces();
    if (!entries) {
      status.textContent = "Workspace list unavailable · API offline";
      list.replaceChildren();
      return;
    }
    list.replaceChildren(...entries.map((entry) => workspaceItem(entry, reader, status, refresh)));
  };
  refreshButton.addEventListener("click", () => void refresh());
  tabs.onChange((active) => {
    if (active === "select") void refresh();
  });
}
