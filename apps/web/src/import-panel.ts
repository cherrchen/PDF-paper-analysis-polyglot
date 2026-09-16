/**
 * Path-style import panel (M8 batch F).
 *
 * Submits a local analysis job to `POST /api/jobs` with absolute source and
 * workspace paths, polls the job record until it finishes, and reloads the
 * viewer onto the job-published revision on success. No upload: the local
 * product is POSIX-only and the job contract takes absolute paths.
 *
 * Module import performs no DOM access; elements arrive via `requiredElement`
 * at call time so unit tests can mount fakes.
 */
import type { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";

const POLL_INTERVAL_MS = 2000;

export type ImportPanelElements = {
  source: HTMLInputElement;
  workspace: HTMLInputElement;
  submit: HTMLButtonElement;
  status: HTMLElement;
};

type JobRecord = {
  id?: string;
  status?: string;
  stage?: string | null;
  error?: string | null;
};

async function getJson(url: string): Promise<JobRecord | undefined> {
  const response = await fetch(url).catch(() => undefined);
  if (!response?.ok) return undefined;
  const payload = (await response.json().catch(() => undefined)) as { job?: JobRecord } | undefined;
  return payload?.job;
}

function elapsedLabel(startedAt: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}

/**
 * Follow the job until it reaches a terminal state.
 *
 * There is no client-side deadline: a real paper on a real provider runs for
 * minutes (the reference 11-page paper took ~10), and giving up early leaves
 * the reader on the previous revision with no way back but a manual reload.
 * The job record stays authoritative, so the status line reports the job's own
 * state plus local elapsed time.
 */
async function pollJob(jobId: string, status: HTMLElement, reader: DualPaneReader): Promise<void> {
  const startedAt = Date.now();
  for (;;) {
    const record = await getJson(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (record) {
      if (record.status === "succeeded") {
        status.textContent = "Job succeeded · reloading viewer";
        try {
          await reader.load(String(Date.now()));
        } catch (error) {
          // The reader still shows the previous revision: the manifest is the
          // commit pointer, so a failed swap never touches it.
          status.textContent = `Reload failed · ${String(error)}`;
          return;
        }
        return;
      }
      if (record.status === "failed") {
        const stage = record.stage ?? "fatal";
        const detail = (record.error ?? "").slice(0, 160);
        status.textContent = `Job failed · ${stage} · ${detail}`;
        return;
      }
      status.textContent = `Job ${record.status ?? "running"} · ${jobId.slice(0, 8)} · ${elapsedLabel(startedAt)}`;
    }
    const { promise, resolve } = Promise.withResolvers<void>();
    setTimeout(resolve, POLL_INTERVAL_MS);
    await promise;
  }
}

async function submitImport(elements: ImportPanelElements, reader: DualPaneReader): Promise<void> {
  const { source, workspace, submit, status } = elements;
  const sourcePath = source.value.trim();
  const workspacePath = workspace.value.trim();
  if (!sourcePath.startsWith("/") || !workspacePath.startsWith("/")) {
    status.textContent = "Import failed · both paths must be absolute";
    return;
  }
  submit.disabled = true;
  status.textContent = "Submitting job…";
  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      // No viewerDataDir: the server defaults it to its own --data-dir, the
      // directory this viewer reads.
      body: JSON.stringify({ source: sourcePath, workspace: workspacePath }),
    });
    const payload = (await response.json().catch(() => undefined)) as
      | { ok?: boolean; error?: string; job?: JobRecord }
      | undefined;
    if (!response.ok || payload?.ok !== true || !payload.job?.id) {
      status.textContent = `Job submit failed · ${payload?.error ?? String(response.status)}`;
      return;
    }
    status.textContent = `Job submitted · ${payload.job.id.slice(0, 8)}`;
    await pollJob(payload.job.id, status, reader);
  } catch (error) {
    status.textContent = `Job submit failed · ${String(error)}`;
  } finally {
    submit.disabled = !reader.apiAvailable;
  }
}

export function importPanelElements(): ImportPanelElements {
  return {
    source: requiredElement<HTMLInputElement>("#import-source"),
    workspace: requiredElement<HTMLInputElement>("#import-workspace"),
    submit: requiredElement<HTMLButtonElement>("#import-submit"),
    status: requiredElement<HTMLElement>("#import-status"),
  };
}

export function bootImportPanel(reader: DualPaneReader, elements?: ImportPanelElements): void {
  const panel = elements ?? importPanelElements();
  panel.submit.disabled = !reader.apiAvailable;
  if (!reader.apiAvailable) panel.status.textContent = "Import unavailable · API offline";
  panel.submit.addEventListener("click", () => void submitImport(panel, reader));
}
