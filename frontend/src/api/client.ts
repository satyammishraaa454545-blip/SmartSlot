// Small typed fetch wrapper. All requests go to /api (proxied by Vite to http://127.0.0.1:8000).

export interface ErrorDetail {
  code: string;
  message: string;
  [extra: string]: unknown;
}

/** Any failed API call. `code` is the server's stable error code, `message` is safe to show to a user. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: ErrorDetail;

  constructor(status: number, detail: ErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.code = detail.code;
    this.detail = detail;
  }
}

export const NETWORK_ERROR_CODE = "NETWORK_ERROR";
export const NETWORK_ERROR_MESSAGE = "Cannot reach the SmartSlot server. Make sure it is running (start.ps1) and try again.";

const BASE = "/api";

type Query = Record<string, string | number | boolean | undefined | null>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Query;
  /** JSON body (object) or FormData (multipart). */
  body?: unknown;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query): string {
  const url = `${BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null) params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: ErrorDetail = { code: `HTTP_${res.status}`, message: `The server answered with an error (${res.status}).` };
  try {
    const data = await res.json();
    const d = data?.detail;
    if (d && typeof d === "object" && typeof d.message === "string") {
      detail = d as ErrorDetail;
    } else if (typeof d === "string") {
      detail = { code: `HTTP_${res.status}`, message: d };
    }
  } catch {
    /* body was not JSON */
  }
  // The API always answers with a {detail: {code, message}} envelope, even for its own 500s. A 5xx without one comes
  // from the dev proxy / a gateway because the API process is not running.
  if (res.status >= 500 && detail.code === `HTTP_${res.status}` && detail.message.startsWith("The server answered")) {
    detail = { code: NETWORK_ERROR_CODE, message: NETWORK_ERROR_MESSAGE };
  }
  return new ApiError(res.status, detail);
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, body, signal } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), { method, headers, body: payload, signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, { code: NETWORK_ERROR_CODE, message: NETWORK_ERROR_MESSAGE });
  }

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const isAbort = (err: unknown): boolean => err instanceof DOMException && err.name === "AbortError";

/** Best human-readable text for any thrown value. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong. Please try again.";
}

/** URL of a file download (templates, exports) so it can be used in <a href>. */
export const apiUrl = (path: string): string => `${BASE}${path}`;
