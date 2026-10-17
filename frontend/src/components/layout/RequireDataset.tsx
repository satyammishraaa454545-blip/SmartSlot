import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { FileUp, Inbox } from "lucide-react";
import type { DatasetDetail } from "../../api";
import { useApp } from "../../state/AppState";
import { Button, Card, EmptyState, PageLoading } from "../ui";

/** Renders `children` once a dataset is selected and loaded; otherwise a friendly empty / loading state. */
export function RequireDataset({ children }: { children: (dataset: DatasetDetail) => ReactNode }) {
  const { datasets, dataset, datasetStatus } = useApp();

  if (datasets.length === 0) {
    return (
      <Card data-testid="no-dataset">
        <EmptyState
          icon={<Inbox className="h-7 w-7" aria-hidden />}
          title="No dataset yet"
          action={
            <Link to="/import">
              <Button variant="primary" icon={<FileUp className="h-4 w-4" aria-hidden />}>
                Go to Import
              </Button>
            </Link>
          }
        >
          Start by importing your college data (teachers, subjects, batches, rooms and requirements) or load the demo
          dataset. Everything else in SmartSlot builds on it.
        </EmptyState>
      </Card>
    );
  }
  if (datasetStatus === "error") {
    return (
      <Card>
        <EmptyState title="This dataset could not be loaded">
          Pick another dataset in the header, or try again in a moment.
        </EmptyState>
      </Card>
    );
  }
  if (!dataset) return <PageLoading label="Loading dataset..." />;
  return <>{children(dataset)}</>;
}
