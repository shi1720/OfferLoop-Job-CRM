/** Typed API client. Auth token comes from the auth layer via a provider
 * so this module stays framework-free. */

import type {
  Analytics,
  AppConfig,
  Application,
  CapturedPosting,
  Draft,
  DraftStatus,
  DraftType,
  ImportReport,
  Nudge,
  PrepPack,
  Profile,
  ScanReport,
  Status,
} from "./types";

let tokenProvider: () => Promise<string> = async () => "demo";

export function setTokenProvider(provider: () => Promise<string>) {
  tokenProvider = provider;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Machine-readable code from structured error bodies, e.g.
     * "key_required" | "key_invalid" | "gemini_quota_exhausted". */
    public code: string | null = null,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenProvider();
  const response = await fetch(path, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    let code: string | null = null;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail && typeof body.detail.message === "string") {
        detail = body.detail.message;
        code = body.detail.code ?? null;
      } else {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),

  applications: {
    list: () => request<Application[]>("/api/applications"),
    get: (id: string) => request<Application>(`/api/applications/${id}`),
    create: (payload: Partial<Application>) =>
      request<Application>("/api/applications", { method: "POST", body: JSON.stringify(payload) }),
    update: (id: string, payload: Partial<Application> & { status_note?: string }) =>
      request<Application>(`/api/applications/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    setStatus: (id: string, status: Status, note = "") =>
      request<Application>(`/api/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, status_note: note }),
      }),
    remove: (id: string) => request<void>(`/api/applications/${id}`, { method: "DELETE" }),
    restore: (id: string) => request<Application>(`/api/applications/${id}/restore`, { method: "POST" }),
    capture: (payload: { url?: string; text?: string }) =>
      request<CapturedPosting>("/api/applications/capture", { method: "POST", body: JSON.stringify(payload) }),
    prep: (id: string) => request<PrepPack>(`/api/applications/${id}/prep`, { method: "POST" }),
  },

  drafts: {
    list: (applicationId?: string) =>
      request<Draft[]>(`/api/drafts${applicationId ? `?application_id=${applicationId}` : ""}`),
    generate: (applicationId: string, type: DraftType, instructions = "") =>
      request<Draft>(`/api/applications/${applicationId}/drafts`, {
        method: "POST",
        body: JSON.stringify({ type, instructions }),
      }),
    update: (id: string, payload: { subject?: string; contents?: string; status?: DraftStatus }) =>
      request<Draft>(`/api/drafts/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  },

  nudges: {
    list: (status?: string) => request<Nudge[]>(`/api/nudges${status ? `?status=${status}` : ""}`),
    done: (id: string) => request<Nudge>(`/api/nudges/${id}/done`, { method: "POST" }),
    dismiss: (id: string) => request<Nudge>(`/api/nudges/${id}/dismiss`, { method: "POST" }),
  },

  scan: () => request<ScanReport>("/api/scan", { method: "POST" }),

  importCsvs: (files: { postings?: File; drafts?: File }) => {
    const form = new FormData();
    if (files.postings) form.append("postings", files.postings);
    if (files.drafts) form.append("drafts", files.drafts);
    return request<ImportReport>("/api/import", { method: "POST", body: form });
  },
  importHistory: () => request<ImportReport[]>("/api/import/history"),
  sampleFile: async (name: "postings" | "drafts"): Promise<File> => {
    const token = await tokenProvider();
    const response = await fetch(`/api/import/samples/${name}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new ApiError(response.status, "Sample dataset unavailable");
    const text = await response.text();
    return new File([text], `sample_${name}.csv`, { type: "text/csv" });
  },

  analytics: () => request<Analytics>("/api/analytics"),

  profile: {
    get: () => request<Profile>("/api/profile"),
    update: (payload: Partial<Profile>) =>
      request<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(payload) }),
    setGeminiKey: (key: string) =>
      request<Profile>("/api/profile/gemini-key", { method: "PUT", body: JSON.stringify({ key }) }),
    removeGeminiKey: () => request<Profile>("/api/profile/gemini-key", { method: "DELETE" }),
    registerPushToken: (token: string) =>
      request<Profile>("/api/profile/push-token", { method: "PUT", body: JSON.stringify({ token }) }),
    disablePush: () => request<Profile>("/api/profile/push-token", { method: "DELETE" }),
  },

  account: {
    /** Authenticated CSV download — fetches with the bearer token, then
     * hands the bytes to the browser as a file. */
    download: async (name: "applications" | "drafts") => {
      const token = await tokenProvider();
      const response = await fetch(`/api/export/${name}.csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new ApiError(response.status, "Export failed — try again");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `offerloop_${name}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    },
    deleteEverything: () => request<void>("/api/account", { method: "DELETE" }),
  },
};
