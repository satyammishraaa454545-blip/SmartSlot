import { request } from "./client";
import type {
  Analytics,
  CompareResult,
  EditResponse,
  MoveRequest,
  MoveResult,
  PlaceRequest,
  PublishResponse,
  RestoreResponse,
  Suggestion,
  ValidateResponse,
  VersionDetail,
  VersionMeta,
} from "./types";

const enc = encodeURIComponent;

export const versionsApi = {
  listForDataset: (datasetId: number, signal?: AbortSignal) =>
    request<VersionMeta[]>(`/datasets/${datasetId}/versions`, { signal }),
  get: (id: number, signal?: AbortSignal) => request<VersionDetail>(`/versions/${id}`, { signal }),
  validate: (id: number) => request<ValidateResponse>(`/versions/${id}/validate`, { method: "POST" }),
  revalidate: (id: number) => request<ValidateResponse>(`/versions/${id}/revalidate`, { method: "POST" }),

  // ---- publishing, versions, insights and manual editing ----
  publish: (id: number, acknowledgeIncomplete = false) =>
    request<PublishResponse>(`/versions/${id}/publish`, {
      method: "POST",
      body: { acknowledge_incomplete: acknowledgeIncomplete },
    }),
  restore: (id: number, body: { label?: string; notes?: string } = {}) =>
    request<RestoreResponse>(`/versions/${id}/restore`, { method: "POST", body }),
  remove: (id: number) => request<void>(`/versions/${id}`, { method: "DELETE" }),
  compare: (a: number, b: number) => request<CompareResult>(`/versions/${a}/compare/${b}`),
  analytics: (id: number) => request<Analytics>(`/versions/${id}/analytics`),

  validateMove: (id: number, entryId: string, move: MoveRequest) =>
    request<MoveResult>(`/versions/${id}/entries/${enc(entryId)}/validate-move`, { method: "POST", body: move }),
  moveEntry: (id: number, entryId: string, move: MoveRequest) =>
    request<EditResponse>(`/versions/${id}/entries/${enc(entryId)}`, { method: "PATCH", body: move }),
  unscheduleEntry: (id: number, entryId: string) =>
    request<EditResponse>(`/versions/${id}/entries/${enc(entryId)}/unschedule`, { method: "POST" }),
  entrySuggestions: (id: number, entryId: string, limit = 5) =>
    request<Suggestion[]>(`/versions/${id}/entries/${enc(entryId)}/suggestions`, { query: { limit } }),
  unscheduledSuggestions: (id: number, sessionId: string, limit = 5) =>
    request<Suggestion[]>(`/versions/${id}/unscheduled/${enc(sessionId)}/suggestions`, { query: { limit } }),
  validatePlace: (id: number, sessionId: string, body: PlaceRequest) =>
    request<MoveResult>(`/versions/${id}/unscheduled/${enc(sessionId)}/validate-place`, { method: "POST", body }),
  place: (id: number, sessionId: string, body: PlaceRequest) =>
    request<EditResponse>(`/versions/${id}/unscheduled/${enc(sessionId)}/place`, { method: "POST", body }),
};

export const exportLinks = {
  csv: (versionId: number) => `/api/versions/${versionId}/export.csv`,
  pdf: (versionId: number, view?: "batch" | "teacher" | "room", id?: string) => {
    const params = new URLSearchParams();
    if (view) params.set("view", view);
    if (id) params.set("id", id);
    const qs = params.toString();
    return `/api/versions/${versionId}/export.pdf${qs ? `?${qs}` : ""}`;
  },
};
