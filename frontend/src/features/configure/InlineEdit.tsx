import { useEffect, useState } from "react";

interface InlineEditProps {
  value: string | number;
  type?: "text" | "number";
  min?: number;
  max?: number;
  ariaLabel: string;
  testId?: string;
  align?: "left" | "right";
  /** Return an error message to reject the value (it reverts), or null to accept. */
  validate?: (raw: string) => string | null;
  onCommit: (raw: string) => void;
  onInvalid?: (message: string) => void;
}

/** A table cell that looks like text until focused; commits on blur / Enter, reverts on Escape. */
export function InlineEdit({
  value,
  type = "text",
  min,
  max,
  ariaLabel,
  testId,
  align = "left",
  validate,
  onCommit,
  onInvalid,
}: InlineEditProps) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);

  const commit = () => {
    const raw = draft.trim();
    if (raw === String(value)) return;
    const problem = validate?.(raw) ?? (raw === "" ? "This value cannot be empty." : null);
    if (problem) {
      onInvalid?.(problem);
      setDraft(String(value));
      return;
    }
    onCommit(raw);
  };

  return (
    <input
      type={type}
      value={draft}
      min={min}
      max={max}
      aria-label={ariaLabel}
      data-testid={testId}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          setDraft(String(value));
          (e.target as HTMLInputElement).blur();
        }
      }}
      className={`h-8 w-full rounded-md border border-slate-200/80 bg-slate-50/70 px-2 text-sm text-slate-800 hover:border-slate-300 hover:bg-white focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 ${
        align === "right" ? "text-right tabular-nums" : ""
      }`}
    />
  );
}
