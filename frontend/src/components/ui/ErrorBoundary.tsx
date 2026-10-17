import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";
import { Button } from "./Button";

interface Props {
  children: ReactNode;
  /** short name used in the message, for example "this page" */
  what?: string;
  /** compact inline fallback instead of a full card */
  inline?: boolean;
}

interface State {
  error: Error | null;
}

/** Catches render errors so one broken widget never blanks the whole app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("SmartSlot UI error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    const what = this.props.what ?? "this page";
    return (
      <div
        role="alert"
        data-testid="error-boundary"
        className={`rounded-2xl border border-red-200 bg-red-50 text-red-900 ${this.props.inline ? "p-4" : "mx-auto mt-10 max-w-lg p-8 text-center"}`}
      >
        <div className={`flex items-center gap-3 ${this.props.inline ? "" : "justify-center"}`}>
          <TriangleAlert className="h-6 w-6 shrink-0 text-red-600" aria-hidden />
          <h2 className="text-base font-semibold">Something went wrong on {what}</h2>
        </div>
        <p className="mt-2 text-sm text-red-800/90">
          Your timetable data is safe: nothing was changed. Try again, or reload the page if the problem stays.
        </p>
        <p className="mt-1 break-words text-xs text-red-700/80">{this.state.error.message}</p>
        <div className={`mt-4 ${this.props.inline ? "" : "flex justify-center"}`}>
          <Button icon={<RefreshCw className="h-4 w-4" aria-hidden />} onClick={() => this.setState({ error: null })} data-testid="error-retry">
            Try again
          </Button>
        </div>
      </div>
    );
  }
}
