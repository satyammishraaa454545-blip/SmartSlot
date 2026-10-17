import { ApiError, NETWORK_ERROR_CODE, NETWORK_ERROR_MESSAGE } from "../api";

function fileNameFrom(res: Response, fallback: string): string {
  const header = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* fall through */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1] : fallback;
}

export interface Downloaded {
  fileName: string;
  size: number;
  type: string;
}

/**
 * Download a file from the API and hand it to the browser as a normal "save as" download.
 * Errors (404, 409, network) are thrown as ApiError so the caller can show a toast.
 */
export async function downloadFile(url: string, fallbackName: string): Promise<Downloaded> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new ApiError(0, { code: NETWORK_ERROR_CODE, message: NETWORK_ERROR_MESSAGE });
  }
  if (!res.ok) {
    let message = res.status >= 500 ? NETWORK_ERROR_MESSAGE : `The server could not create the file (${res.status}).`; // a 5xx without a JSON body = API not running (dev proxy)
    let code = res.status >= 500 ? NETWORK_ERROR_CODE : `HTTP_${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail?.message) {
        message = data.detail.message;
        code = data.detail.code ?? code;
      }
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, { code, message });
  }
  const blob = await res.blob();
  const fileName = fileNameFrom(res, fallbackName);
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = fileName;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 30_000);
  return { fileName, size: blob.size, type: blob.type };
}

export const formatBytes = (n: number): string => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
