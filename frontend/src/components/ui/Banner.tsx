import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { TONES, type Tone } from "./tones";

interface BannerProps {
  tone: Tone;
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
  role?: "status" | "alert";
  "data-testid"?: string;
}

function defaultIcon(tone: Tone) {
  const cls = `h-5 w-5 ${TONES[tone].icon}`;
  switch (tone) {
    case "green":
      return <CheckCircle2 className={cls} aria-hidden />;
    case "amber":
      return <AlertTriangle className={cls} aria-hidden />;
    case "red":
      return <XCircle className={cls} aria-hidden />;
    default:
      return <Info className={cls} aria-hidden />;
  }
}

/** Inline callout used for results, warnings and errors. */
export function Banner({ tone, title, children, actions, icon, className = "", role = "status", ...rest }: BannerProps) {
  return (
    <div
      role={role}
      data-testid={rest["data-testid"]}
      className={`flex flex-wrap items-start gap-3 rounded-xl border px-4 py-3 ${TONES[tone].soft} ${className}`}
    >
      <div className="mt-0.5 shrink-0">{icon ?? defaultIcon(tone)}</div>
      <div className="min-w-0 flex-1 basis-64">
        {title && <div className="text-sm font-semibold">{title}</div>}
        {children && <div className={`text-sm ${title ? "mt-0.5 opacity-90" : ""}`}>{children}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
