import { Outlet, useLocation } from "react-router-dom";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { NETWORK_ERROR_MESSAGE } from "../../api";
import { useApp } from "../../state/AppState";
import { Button, ErrorBoundary, PageLoading } from "../ui";
import { ServerCrash } from "lucide-react";

export function AppShell() {
  const { datasetsStatus, datasetsError, refreshDatasets } = useApp();
  const location = useLocation();

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-slate-50 print:block print:h-auto print:overflow-visible">
      <Header />
      <div className="flex min-h-0 flex-1 print:block">
        <Sidebar />
        <main className="relative min-w-0 flex-1 overflow-y-auto overflow-x-hidden [scrollbar-gutter:stable] print:overflow-visible" id="main" data-testid="main">
          <div className="mx-auto max-w-[1400px] px-4 py-6 lg:px-8">
            {datasetsStatus === "loading" ? (
              <PageLoading label="Connecting to SmartSlot..." />
            ) : datasetsStatus === "error" ? (
              <div className="card mx-auto mt-12 max-w-lg p-8 text-center" role="alert" data-testid="server-error">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-red-600">
                  <ServerCrash className="h-7 w-7" aria-hidden />
                </div>
                <h2 className="text-lg font-semibold text-slate-900">Cannot reach the SmartSlot server</h2>
                <p className="mt-1.5 text-sm text-slate-500">
                  {datasetsError && datasetsError !== NETWORK_ERROR_MESSAGE ? datasetsError : "The server did not answer."} Start it with{" "}
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">start.ps1</code> and press Retry.
                </p>
                <Button variant="primary" className="mt-5" onClick={() => void refreshDatasets()}>
                  Retry
                </Button>
              </div>
            ) : (
              <ErrorBoundary key={location.pathname}>
                <Outlet />
              </ErrorBoundary>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
