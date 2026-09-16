/**
 * Console API client for worker jobs, uploads, and workspace opening (M8 F).
 *
 * Every call resolves to a plain result instead of throwing: the console has
 * to render "API offline" lines, and an unreachable server is an expected
 * state, not an exceptional one. Module import performs no DOM access.
 */
export type JobRecord = {
  id: string;
  status: string;
  stage: string | null;
  error: string | null;
  attempt: number;
  source: string;
  workspace: string;
  createdAt: string;
  updatedAt: string;
};

export type JobResult = { ok: boolean; error?: string; job?: JobRecord };

export type UploadResult = {
  ok: boolean;
  error?: string;
  path?: string;
  workspace?: string;
  bytes?: number;
};

export type OpenWorkspaceResult = { ok: boolean; error?: string; revision?: string };

export const POLL_INTERVAL_MS = 2000;

/** Every console endpoint answers `{ok, …}`; fields stay `unknown` until used. */
export type ApiPayload = Partial<
  Record<
    | "ok"
    | "error"
    | "job"
    | "jobs"
    | "path"
    | "workspace"
    | "workspaces"
    | "bytes"
    | "revision"
    | "api"
    | "worker"
    | "viewer",
    unknown
  >
>;

/** Parse the JSON body at the boundary; a non-object or unparsable body is `{}`. */
export async function readApiJson(response: Response): Promise<ApiPayload> {
  const value: unknown = await response.json().catch(() => undefined);
  return typeof value === "object" && value !== null ? (value as ApiPayload) : {};
}

/** Job records arrive from the worker API; unknown shapes degrade to blanks. */
function toJobRecord(value: unknown): JobRecord | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const record = value as Partial<Record<keyof JobRecord, unknown>>;
  if (typeof record.id !== "string" || record.id.length === 0) return undefined;
  return {
    id: record.id,
    status: typeof record.status === "string" ? record.status : "unknown",
    stage: typeof record.stage === "string" ? record.stage : null,
    error: typeof record.error === "string" ? record.error : null,
    attempt: typeof record.attempt === "number" ? record.attempt : 0,
    source: typeof record.source === "string" ? record.source : "",
    workspace: typeof record.workspace === "string" ? record.workspace : "",
    createdAt: typeof record.createdAt === "string" ? record.createdAt : "",
    updatedAt: typeof record.updatedAt === "string" ? record.updatedAt : "",
  };
}

async function submitLike(url: string, init: RequestInit | undefined): Promise<JobResult> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    return { ok: false, error: String(error) };
  }
  const payload = await readApiJson(response);
  const job = toJobRecord(payload.job);
  if (!response.ok || payload.ok !== true || !job) {
    const error = typeof payload.error === "string" ? payload.error : String(response.status);
    return { ok: false, error };
  }
  return { ok: true, job };
}

export async function listJobs(): Promise<JobRecord[] | undefined> {
  let response: Response;
  try {
    response = await fetch("/api/jobs");
  } catch {
    return undefined;
  }
  if (!response.ok) return undefined;
  const payload = await readApiJson(response);
  if (!Array.isArray(payload.jobs)) return undefined;
  return payload.jobs
    .map(toJobRecord)
    .filter((record): record is JobRecord => record !== undefined);
}

export async function getJob(id: string): Promise<JobRecord | undefined> {
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
    if (!response.ok) return undefined;
    return toJobRecord((await readApiJson(response)).job);
  } catch {
    return undefined;
  }
}

export async function submitJob(body: { source: string; workspace: string }): Promise<JobResult> {
  return submitLike("/api/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    // No viewerDataDir: the server defaults it to its own --data-dir, the
    // directory this viewer reads.
    body: JSON.stringify(body),
  });
}

export async function retryJob(id: string): Promise<JobResult> {
  return submitLike(`/api/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" });
}

export async function uploadPdf(file: File): Promise<UploadResult> {
  let response: Response;
  try {
    response = await fetch("/api/uploads", {
      method: "POST",
      headers: { "content-type": "application/pdf", "X-Upload-Name": file.name },
      body: file,
    });
  } catch (error) {
    return { ok: false, error: String(error) };
  }
  const payload = await readApiJson(response);
  if (!response.ok || payload.ok !== true) {
    const error = typeof payload.error === "string" ? payload.error : String(response.status);
    return { ok: false, error };
  }
  const result: UploadResult = { ok: true };
  if (typeof payload.path === "string") result.path = payload.path;
  if (typeof payload.workspace === "string") result.workspace = payload.workspace;
  if (typeof payload.bytes === "number") result.bytes = payload.bytes;
  return result;
}

export async function openWorkspacePath(workspace: string): Promise<OpenWorkspaceResult> {
  let response: Response;
  try {
    response = await fetch("/api/workspaces/open", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ workspace }),
    });
  } catch (error) {
    return { ok: false, error: String(error) };
  }
  const payload = await readApiJson(response);
  if (!response.ok || payload.ok !== true) {
    const error = typeof payload.error === "string" ? payload.error : String(response.status);
    return { ok: false, error };
  }
  return typeof payload.revision === "string"
    ? { ok: true, revision: payload.revision }
    : { ok: true };
}

export function elapsedLabel(startedAt: number): string {
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
 * The job record stays authoritative, so callers report the job's own state
 * plus local elapsed time. Two consecutive missing records mean the API is
 * unreachable rather than the job gone.
 */
export async function followJob(
  jobId: string,
  onUpdate: (record: JobRecord | undefined, elapsedMs: number) => void,
): Promise<JobRecord | undefined> {
  const startedAt = Date.now();
  let missing = 0;
  for (;;) {
    const record = await getJob(jobId);
    if (!record) {
      missing += 1;
      if (missing >= 2) return undefined;
    } else {
      missing = 0;
      onUpdate(record, Date.now() - startedAt);
      if (record.status === "succeeded" || record.status === "failed") return record;
    }
    const { promise, resolve } = Promise.withResolvers<void>();
    setTimeout(resolve, POLL_INTERVAL_MS);
    await promise;
  }
}
