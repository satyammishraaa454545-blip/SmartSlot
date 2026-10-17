import { useEffect, useRef, useState } from "react";
import { PageHeader } from "../../components/layout/PageHeader";
import { PageLoading, useToast } from "../../components/ui";
import type { ImportResponse } from "../../api";
import { useApp } from "../../state/AppState";
import { plural } from "../../lib/format";
import { UploadCard } from "./UploadCard";
import { DemoCard } from "./DemoCard";
import { ValidationSummary } from "./ValidationSummary";
import { DatasetList } from "./DatasetList";
import { TemplateDocs } from "./TemplateDocs";

export function ImportPage() {
  const { dataset, datasetStatus, datasetId, adoptImportedDataset } = useApp();
  const toast = useToast();
  const summaryRef = useRef<HTMLDivElement>(null);
  const [scrollToId, setScrollToId] = useState<number | null>(null);

  const handleImported = (res: ImportResponse) => {
    const { dataset: ds, can_generate } = res;
    if (can_generate) {
      toast.success("Import complete", `${ds.name}: ${plural(ds.total_sessions, "session")} per week are ready to schedule.`);
    } else {
      toast.warning("Imported with errors", `${plural(ds.error_count, "error")} found. Generation is blocked until they are fixed.`);
    }
    setScrollToId(ds.id);
    void adoptImportedDataset(ds);
  };

  // after an import, bring the validation summary into view once it has loaded
  useEffect(() => {
    if (scrollToId !== null && dataset && dataset.id === scrollToId && datasetId === scrollToId) {
      summaryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setScrollToId(null);
    }
  }, [scrollToId, dataset, datasetId]);

  return (
    <div className="space-y-6">
      <PageHeader
        step={1}
        title="Import your data"
        description="Upload the CSV files exported from your college ERP or spreadsheet, or start with a demo dataset. SmartSlot checks every row and tells you exactly how to fix any problem."
      />

      <div className="grid items-start gap-6 xl:grid-cols-[3fr_2fr]">
        <UploadCard onImported={handleImported} />
        <DemoCard onImported={handleImported} />
      </div>

      <div ref={summaryRef} className="scroll-mt-4">
        {dataset ? (
          <ValidationSummary dataset={dataset} />
        ) : datasetStatus === "loading" ? (
          <PageLoading label="Loading validation summary..." />
        ) : null}
      </div>

      <DatasetList />
      <TemplateDocs />
    </div>
  );
}
