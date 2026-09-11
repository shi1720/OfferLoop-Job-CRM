/** Typed API client. Auth token comes from the auth layer via a provider
 * so this module stays framework-free. */

import type {
  Analytics,
  AppConfig,
  Application,
  Draft,
  DraftStatus,
  DraftType,
  ImportReport,
  Nudge,
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
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
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
  },
};
