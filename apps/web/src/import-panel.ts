/**
 * Upload surface (M8 batch F, rebuilt as the console upload tab).
 *
 * Two ways in: drop/choose a PDF, which the server stores in its own inbox and
 * answers with a derived workspace path, or type absolute source and workspace
 * paths directly. Both end in the same job submission, which polls the job
 * record until it finishes and reloads the viewer onto the job-published
 * revision on success.
 *
 * Module import performs no DOM access; elements arrive via `requiredElement`
 * at call time so unit tests can mount fakes.
 */
import { elapsedLabel, followJob, submitJob, uploadPdf } from "./jobs-client.js";
import type { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";

export type ImportPanelElements = {
  source: HTMLInputElement;
  workspace: HTMLInputElement;
  submit: HTMLButtonElement;
  status: HTMLElement;
  file: HTMLInputElement;
  drop: HTMLElement;
  uploadStatus: HTMLElement;
};

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
    const submission = await submitJob({ source: sourcePath, workspace: workspacePath });
    if (!submission.ok || !submission.job) {
      status.textContent = `Job submit failed · ${submission.error ?? "unknown error"}`;
      return;
    }
    const jobId = submission.job.id;
    status.textContent = `Job submitted · ${jobId.slice(0, 8)}`;
    const record = await followJob(jobId, (update, elapsedMs) => {
      if (!update) return;
      if (update.status === "succeeded") {
        status.textContent = "Job succeeded · reloading viewer";
        return;
      }
      if (update.status === "failed") {
        const stage = update.stage ?? "fatal";
        const detail = (update.error ?? "").slice(0, 160);
        status.textContent = `Job failed · ${stage} · ${detail}`;
        return;
      }
      // followJob reports time already elapsed; elapsedLabel formats from a
      // start timestamp, so reconstruct the job's start.
      status.textContent = `Job ${update.status} · ${jobId.slice(0, 8)} · ${elapsedLabel(
        Date.now() - elapsedMs,
      )}`;
    });
    if (!record) {
      status.textContent = "Job status unavailable · API offline";
      return;
    }
    if (record.status !== "succeeded") return;
    try {
      await reader.load(String(Date.now()));
    } catch (error) {
      // The reader still shows the previous revision: the manifest is the
      // commit pointer, so a failed swap never touches it.
      status.textContent = `Reload failed · ${String(error)}`;
    }
  } finally {
    submit.disabled = !reader.apiAvailable;
  }
}

/** Drop or file-picker entry: the server names both the inbox copy and the workspace. */
async function handleFile(
  file: File,
  elements: ImportPanelElements,
  reader: DualPaneReader,
): Promise<void> {
  const { uploadStatus } = elements;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    uploadStatus.textContent = "Upload failed · only .pdf files are accepted";
    return;
  }
  uploadStatus.textContent = `Uploading ${file.name}…`;
  const upload = await uploadPdf(file);
  if (!upload.ok || !upload.path || !upload.workspace) {
    uploadStatus.textContent = `Upload failed · ${upload.error ?? "unknown error"}`;
    return;
  }
  elements.source.value = upload.path;
  elements.workspace.value = upload.workspace;
  uploadStatus.textContent = `Uploaded ${upload.bytes ?? 0} bytes · ${upload.path}`;
  await submitImport(elements, reader);
}

export function importPanelElements(): ImportPanelElements {
  return {
    source: requiredElement<HTMLInputElement>("#import-source"),
    workspace: requiredElement<HTMLInputElement>("#import-workspace"),
    submit: requiredElement<HTMLButtonElement>("#import-submit"),
    status: requiredElement<HTMLElement>("#import-status"),
    file: requiredElement<HTMLInputElement>("#upload-file"),
    drop: requiredElement<HTMLElement>("#upload-drop"),
    uploadStatus: requiredElement<HTMLElement>("#upload-status"),
  };
}

export function bootImportPanel(reader: DualPaneReader, elements?: ImportPanelElements): void {
  const panel = elements ?? importPanelElements();
  panel.submit.disabled = !reader.apiAvailable;
  if (!reader.apiAvailable) panel.status.textContent = "Import unavailable · API offline";
  panel.submit.addEventListener("click", () => void submitImport(panel, reader));
  panel.file.addEventListener("change", () => {
    const file = panel.file.files?.[0];
    if (file) void handleFile(file, panel, reader);
  });
  panel.drop.addEventListener("dragover", (event) => event.preventDefault());
  panel.drop.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files[0];
    if (file) void handleFile(file, panel, reader);
  });
}
