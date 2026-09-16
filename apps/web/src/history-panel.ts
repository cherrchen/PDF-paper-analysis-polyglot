/**
 * History surface: every worker job record with the two follow-up actions.
 *
 * `Retry` requeues a failed job; `Open` republishes a succeeded job's
 * workspace and swaps the reader onto it — the same server path the select
 * surface uses, so the client still never names a write target.
 */
import { type JobRecord, listJobs, retryJob } from "./jobs-client.js";
import type { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";
import { openPublishedWorkspace } from "./select-panel.js";
import type { SurfaceTabs } from "./surface-tabs.js";

const ERROR_CHARS = 160;

function line(className: string, text: string): HTMLSpanElement {
  const element = document.createElement("span");
  element.className = className;
  element.textContent = text;
  return element;
}

function actionButton(
  className: string,
  label: string,
  run: () => Promise<void>,
): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", () => {
    button.disabled = true;
    void (async () => {
      try {
        await run();
      } finally {
        if (button.isConnected) button.disabled = false;
      }
    })();
  });
  return button;
}

function jobItem(
  job: JobRecord,
  reader: DualPaneReader,
  status: HTMLElement,
  refresh: () => Promise<void>,
): HTMLLIElement {
  const item = document.createElement("li");
  item.dataset.jobId = job.id;
  item.dataset.status = job.status;
  item.append(
    line("history-status", `${job.status} · attempt ${job.attempt} · stage ${job.stage ?? "—"}`),
    line("history-updated", job.updatedAt),
    line("history-source", job.source),
    line("history-workspace", job.workspace),
  );
  if (job.error !== null) item.append(line("history-error", job.error.slice(0, ERROR_CHARS)));
  if (job.status === "failed") {
    item.append(
      actionButton("history-retry", "Retry", async () => {
        const result = await retryJob(job.id);
        if (!result.ok) {
          status.textContent = `Retry failed · ${result.error ?? "unknown error"}`;
          return;
        }
        await refresh();
      }),
    );
  }
  if (job.status === "succeeded") {
    item.append(
      actionButton("history-open", "Open", async () => {
        await openPublishedWorkspace(reader, job.workspace, status);
      }),
    );
  }
  return item;
}

export function bootHistoryPanel(reader: DualPaneReader, tabs: SurfaceTabs): void {
  const status = requiredElement<HTMLElement>("#history-status");
  const list = requiredElement<HTMLElement>("#history-list");
  const refreshButton = requiredElement<HTMLButtonElement>("#history-refresh");
  const refresh = async (): Promise<void> => {
    const jobs = await listJobs();
    if (!jobs) {
      status.textContent = "Job history unavailable · API offline";
      list.replaceChildren();
      return;
    }
    const ordered = [...jobs].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    if (ordered.length === 0) status.textContent = "No jobs recorded";
    list.replaceChildren(...ordered.map((job) => jobItem(job, reader, status, refresh)));
  };
  refreshButton.addEventListener("click", () => void refresh());
  tabs.onChange((active) => {
    if (active === "history") void refresh();
  });
}
