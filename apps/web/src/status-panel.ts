/**
 * Status surface: API reachability, worker heartbeat, job counts, viewer
 * revision.
 *
 * The worker line reads the heartbeat file rather than inferring liveness from
 * the queue, so an idle worker and a dead worker are distinguishable. Polling
 * only runs while the surface is open.
 */
import { type ApiPayload, readApiJson } from "./jobs-client.js";
import type { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";
import type { SurfaceTabs } from "./surface-tabs.js";

const POLL_INTERVAL_MS = 3000;

type WorkerStatus = {
  present: boolean;
  alive: boolean;
  pid: number | null;
  ageSeconds: number | null;
  concurrency: number | null;
  running: number;
};

type JobCounts = {
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  oldestQueuedAt: string | null;
};

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function numberField(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  return typeof value === "number" ? value : null;
}

function stringField(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" ? value : null;
}

function workerStatus(value: unknown): WorkerStatus {
  const raw = asObject(value);
  return {
    present: raw.present === true,
    alive: raw.alive === true,
    pid: numberField(raw, "pid"),
    ageSeconds: numberField(raw, "ageSeconds"),
    concurrency: numberField(raw, "concurrency"),
    running: numberField(raw, "running") ?? 0,
  };
}

function jobCounts(value: unknown): JobCounts {
  const raw = asObject(value);
  return {
    queued: numberField(raw, "queued") ?? 0,
    running: numberField(raw, "running") ?? 0,
    succeeded: numberField(raw, "succeeded") ?? 0,
    failed: numberField(raw, "failed") ?? 0,
    oldestQueuedAt: stringField(raw, "oldestQueuedAt"),
  };
}

function workerLine(payload: ApiPayload): string {
  const worker = workerStatus(payload.worker);
  if (worker.alive) {
    const age = worker.ageSeconds ?? 0;
    return `Worker running · pid ${worker.pid ?? 0} · ${worker.running} job(s) · heartbeat ${age}s`;
  }
  if (worker.present) return `Worker stale · last heartbeat ${worker.ageSeconds ?? 0}s ago`;
  return "Worker not detected · start just dev-worker";
}

function jobsLine(payload: ApiPayload): string {
  const counts = jobCounts(payload.jobs);
  const line = [
    `Queued ${counts.queued}`,
    `Running ${counts.running}`,
    `Succeeded ${counts.succeeded}`,
    `Failed ${counts.failed}`,
  ].join(" · ");
  if (counts.queued > 0 && counts.oldestQueuedAt !== null) {
    return `${line} · oldest queued ${counts.oldestQueuedAt}`;
  }
  return line;
}

function viewerLine(payload: ApiPayload, reader: DualPaneReader): string {
  const revision =
    payload.viewer === null ? null : stringField(asObject(payload.viewer), "revision");
  if (revision === null) return "No published revision";
  const facts = [
    `source ${reader.meta.sourcePageCount} pages`,
    `target ${reader.meta.targetPageCount} pages`,
    `${reader.model.pairs.size} linked regions`,
  ];
  if (reader.activeNodeId) facts.push(`active ${reader.activeNodeId.slice(0, 8)}`);
  const workspace = stringField(asObject(payload.viewer), "workspace") ?? "unknown";
  return `Revision ${revision.slice(0, 12)} · workspace ${workspace} · ${facts.join(" · ")}`;
}

export function bootStatusPanel(reader: DualPaneReader, tabs: SurfaceTabs): void {
  const api = requiredElement<HTMLElement>("#status-api");
  const worker = requiredElement<HTMLElement>("#status-worker");
  const jobs = requiredElement<HTMLElement>("#status-jobs");
  const viewer = requiredElement<HTMLElement>("#status-viewer");
  let timer: number | undefined;

  const clear = (): void => {
    worker.textContent = "";
    jobs.textContent = "";
    viewer.textContent = "";
  };
  const refresh = async (): Promise<void> => {
    let payload: ApiPayload;
    try {
      const response = await fetch("/api/status");
      if (!response.ok) {
        api.textContent = `API unreachable · ${response.status}`;
        clear();
        return;
      }
      payload = await readApiJson(response);
    } catch (error) {
      api.textContent = `API unreachable · ${String(error)}`;
      clear();
      return;
    }
    api.textContent = `API ok · ${window.location.origin}`;
    worker.textContent = workerLine(payload);
    jobs.textContent = jobsLine(payload);
    viewer.textContent = viewerLine(payload, reader);
  };

  const stop = (): void => {
    if (timer === undefined) return;
    window.clearInterval(timer);
    timer = undefined;
  };

  tabs.onChange((active) => {
    stop();
    if (active !== "status") return;
    void refresh();
    timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
  });
}
