import { request } from "./client";
import type {
  AvailabilityChange,
  Batch,
  DatasetDetail,
  DatasetEditResponse,
  DatasetSummary,
  Day,
  GenerateRequest,
  GenerateResponse,
  ImportResponse,
  PeriodInput,
  Room,
  Teacher,
} from "./types";

export type SampleKind = "feasible" | "infeasible" | "invalid";

export const datasetsApi = {
  list: (signal?: AbortSignal) => request<DatasetSummary[]>("/datasets", { signal }),
  get: (id: number, signal?: AbortSignal) => request<DatasetDetail>(`/datasets/${id}`, { signal }),

  /** Multipart upload: repeated `files` field (CSV files or one .zip). */
  importFiles: (files: File[], name: string, semester: string) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    if (name.trim()) form.append("name", name.trim());
    if (semester.trim()) form.append("semester", semester.trim());
    return request<ImportResponse>("/datasets/import", { method: "POST", body: form });
  },
  loadSample: (kind: SampleKind) =>
    request<ImportResponse>("/datasets/load-sample", { method: "POST", query: { kind } }),
  remove: (id: number, force = false) =>
    request<void>(`/datasets/${id}`, { method: "DELETE", query: force ? { force: true } : undefined }),

  // ---- configuration ----
  saveConfig: (id: number, days: Day[], periods: PeriodInput[]) =>
    request<DatasetEditResponse>(`/datasets/${id}/config`, { method: "PUT", body: { days, periods } }),
  setAvailability: (id: number, change: AvailabilityChange) =>
    request<DatasetEditResponse>(`/datasets/${id}/availability`, { method: "PATCH", body: change }),
  setAvailabilityBulk: (id: number, changes: AvailabilityChange[]) =>
    request<DatasetEditResponse>(`/datasets/${id}/availability/bulk`, { method: "PATCH", body: { changes } }),
  patchRoom: (id: number, roomId: string, patch: Partial<Pick<Room, "name" | "capacity" | "room_type">>) =>
    request<DatasetEditResponse>(`/datasets/${id}/rooms/${encodeURIComponent(roomId)}`, {
      method: "PATCH",
      body: patch,
    }),
  patchTeacher: (id: number, teacherId: string, patch: Partial<Pick<Teacher, "name" | "department_id">>) =>
    request<DatasetEditResponse>(`/datasets/${id}/teachers/${encodeURIComponent(teacherId)}`, {
      method: "PATCH",
      body: patch,
    }),
  patchBatch: (
    id: number,
    batchId: string,
    patch: Partial<Pick<Batch, "name" | "student_count" | "semester" | "department_id">>,
  ) =>
    request<DatasetEditResponse>(`/datasets/${id}/batches/${encodeURIComponent(batchId)}`, {
      method: "PATCH",
      body: patch,
    }),

  generate: (id: number, body: GenerateRequest = {}) =>
    request<GenerateResponse>(`/datasets/${id}/generate`, { method: "POST", body }),
};

/** Static download links for blank CSV templates. */
export const templateLinks = {
  zip: "/api/templates.zip",
  file: (name: string) => `/api/templates/${name}`,
};
