import { useState } from "react";
import { Check, Database, Trash2 } from "lucide-react";
import { ApiError, datasetsApi, errorMessage, type DatasetSummary } from "../../api";
import { Badge, Button, Card, CardHeader, ConfirmDialog, EmptyState, useToast } from "../../components/ui";
import { useApp } from "../../state/AppState";
import { formatDateTime, plural } from "../../lib/format";

interface PendingDelete {
  dataset: DatasetSummary;
  /** true when the dataset has a published timetable (the server then requires ?force=true) */
  force: boolean;
}

export function DatasetList() {
  const { datasets, datasetId, selectDataset, forgetDataset } = useApp();
  const toast = useToast();
  const [pending, setPending] = useState<PendingDelete | null>(null);
  const [busy, setBusy] = useState(false);

  const confirmDelete = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      await datasetsApi.remove(pending.dataset.id, pending.force);
      toast.success("Dataset deleted", `"${pending.dataset.name}" and its timetables were removed.`);
      setPending(null);
      await forgetDataset(pending.dataset.id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "DATASET_HAS_PUBLISHED_VERSION" && !pending.force) {
        // somebody published since the list was loaded: ask again with the stronger warning
        setPending({ dataset: pending.dataset, force: true });
      } else if (err instanceof ApiError && err.status === 404) {
        setPending(null);
        await forgetDataset(pending.dataset.id);
      } else {
        toast.error("Could not delete the dataset", errorMessage(err));
        setPending(null);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card data-testid="dataset-list">
      <CardHeader
        icon={<Database className="h-5 w-5" aria-hidden />}
        title="Your datasets"
        description="Select one to work on. The selected dataset is used on every page."
      />
      <div className="px-5 pb-5 pt-4">
        {datasets.length === 0 ? (
          <EmptyState title="No datasets yet" className="py-8">
            Upload your files or load a demo dataset above and it will appear here.
          </EmptyState>
        ) : (
          <div className="scroll-thin overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[560px] text-left">
              <thead className="bg-slate-50">
                <tr>
                  <th className="th">Dataset</th>
                  <th className="th">Import</th>
                  <th className="th text-right">Sessions</th>
                  <th className="th text-right">Timetables</th>
                  <th className="th hidden xl:table-cell">Added</th>
                  <th className="th text-right">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {datasets.map((d) => {
                  const selected = d.id === datasetId;
                  return (
                    <tr key={d.id} className={selected ? "bg-indigo-50/50" : "hover:bg-slate-50/60"} data-testid={`dataset-row-${d.id}`}>
                      <td className="td">
                        <div className="font-semibold text-slate-900">{d.name}</div>
                        <div className="text-xs text-slate-500">
                          Semester {d.semester || "-"} {"·"} {d.source.startsWith("sample") ? "Demo data" : "Uploaded files"}
                        </div>
                      </td>
                      <td className="td">
                        {d.import_status === "ok" ? (
                          <Badge tone="green" size="sm">Passed</Badge>
                        ) : (
                          <Badge tone="red" size="sm">{plural(d.error_count, "error")}</Badge>
                        )}
                      </td>
                      <td className="td text-right tabular-nums">{d.total_sessions}</td>
                      <td className="td text-right">
                        <span className="tabular-nums">{d.version_count}</span>
                        {d.published_version_id !== null && (
                          <Badge tone="green" size="sm" className="ml-2">
                            Published
                          </Badge>
                        )}
                      </td>
                      <td className="td hidden whitespace-nowrap text-slate-500 xl:table-cell">{formatDateTime(d.created_at)}</td>
                      <td className="td">
                        <div className="flex justify-end gap-2">
                          {selected ? (
                            <span className="inline-flex h-8 items-center gap-1 rounded-lg bg-indigo-100 px-3 text-xs font-semibold text-indigo-700" data-testid="selected-mark">
                              <Check className="h-3.5 w-3.5" aria-hidden /> Selected
                            </span>
                          ) : (
                            <Button size="sm" onClick={() => selectDataset(d.id)} data-testid={`select-dataset-${d.id}`}>
                              Select
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-slate-500 hover:!bg-red-50 hover:!text-red-600"
                            aria-label={`Delete ${d.name}`}
                            data-testid={`delete-dataset-${d.id}`}
                            onClick={() => setPending({ dataset: d, force: d.published_version_id !== null })}
                            icon={<Trash2 className="h-4 w-4" aria-hidden />}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pending !== null}
        title="Delete this dataset?"
        confirmLabel={pending?.force ? "Delete dataset and published timetable" : "Delete dataset"}
        danger
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPending(null)}
      >
        {pending && (
          <div className="space-y-3">
            <p>
              <strong className="text-slate-900">{pending.dataset.name}</strong> will be removed together with all its timetable
              versions ({pending.dataset.version_count}). This cannot be undone.
            </p>
            {pending.force && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-800" data-testid="force-warning">
                <strong>This dataset has a published timetable.</strong> Deleting it will also permanently delete that published
                timetable. Only continue if you are sure nobody needs it.
              </div>
            )}
          </div>
        )}
      </ConfirmDialog>
    </Card>
  );
}
