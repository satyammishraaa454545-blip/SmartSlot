import { useEffect, useRef, useState } from "react";
import { errorMessage, type MoveResult } from "../../../api";

export type LiveState =
  | { phase: "idle" }
  | { phase: "checking"; previous: MoveResult | null }
  | { phase: "done"; result: MoveResult }
  | { phase: "error"; message: string };

/**
 * Debounced dry-run validation. `key` identifies the proposed change (re-runs when it changes), `run` performs the
 * call, and `enabled=false` means "nothing to check" (idle). Only the latest request may update the state.
 */
export function useLiveCheck(key: string, enabled: boolean, run: () => Promise<MoveResult>, delayMs = 250): LiveState {
  const [state, setState] = useState<LiveState>({ phase: "idle" });
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    if (!enabled) {
      setState({ phase: "idle" });
      return;
    }
    let cancelled = false;
    setState((prev) => ({ phase: "checking", previous: prev.phase === "done" ? prev.result : prev.phase === "checking" ? prev.previous : null }));
    const timer = window.setTimeout(async () => {
      try {
        const result = await runRef.current();
        if (!cancelled) setState({ phase: "done", result });
      } catch (err) {
        if (!cancelled) setState({ phase: "error", message: errorMessage(err) });
      }
    }, delayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [key, enabled, delayMs]);

  return state;
}
