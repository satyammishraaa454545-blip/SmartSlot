import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { Tone } from "./tones";

export interface ToastOptions {
  /** one extra button, for example "Undo" */
  action?: { label: string; onClick: () => void; testId?: string };
  /** how long it stays, in milliseconds (default 5 s, errors 9 s, with an action 10 s) */
  durationMs?: number;
  testId?: string;
}

interface ToastItem {
  id: number;
  tone: Tone;
  title: string;
  message?: string;
  options?: ToastOptions;
}

interface ToastApi {
  success: (title: string, message?: string, options?: ToastOptions) => void;
  error: (title: string, message?: string, options?: ToastOptions) => void;
  warning: (title: string, message?: string, options?: ToastOptions) => void;
  info: (title: string, message?: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const ICONS: Record<string, ReactNode> = {
  green: <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden />,
  red: <XCircle className="h-5 w-5 text-red-600" aria-hidden />,
  amber: <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />,
  blue: <Info className="h-5 w-5 text-sky-600" aria-hidden />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setItems((cur) => cur.filter((t) => t.id !== id)), []);

  const push = useCallback(
    (tone: Tone, title: string, message?: string, options?: ToastOptions) => {
      const id = nextId.current++;
      setItems((cur) => [...cur.slice(-3), { id, tone, title, message, options }]);
      window.setTimeout(() => dismiss(id), options?.durationMs ?? (options?.action ? 10000 : tone === "red" ? 9000 : 5000));
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (t, m, o) => push("green", t, m, o),
      error: (t, m, o) => push("red", t, m, o),
      warning: (t, m, o) => push("amber", t, m, o),
      info: (t, m, o) => push("blue", t, m, o),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
        aria-live="polite"
        data-testid="toast-region"
      >
        {items.map((t) => (
          <div
            key={t.id}
            role={t.tone === "red" ? "alert" : "status"}
            data-testid={t.options?.testId ?? `toast-${t.tone}`}
            data-tone={t.tone}
            className="pointer-events-auto flex animate-toast-in items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-pop"
          >
            <div className="mt-0.5 shrink-0">{ICONS[t.tone]}</div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900">{t.title}</p>
              {t.message && <p className="mt-0.5 break-words text-sm text-slate-600">{t.message}</p>}
              {t.options?.action && (
                <button
                  onClick={() => {
                    t.options?.action?.onClick();
                    dismiss(t.id);
                  }}
                  data-testid={t.options.action.testId ?? "toast-action"}
                  className="mt-1.5 rounded-md bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                >
                  {t.options.action.label}
                </button>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
              className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
