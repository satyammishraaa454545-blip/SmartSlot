import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage, versionsApi, type PublishResponse, type RestoreResponse, type VersionMeta } from "../../api";
import { useToast } from "../../components/ui";
import { useApp } from "../../state/AppState";

type Ref = Pick<VersionMeta, "id" | "label" | "status">;

/**
 * Version-level actions shared by the Versions page, the Timetable page and the Configure page.
 * Every action keeps the header, version list and dataset summary in sync (adoptVersion + refreshes) and
 * shows a consistent toast. Failures are re-thrown so a dialog can keep its own error text.
 */
export function useVersionActions() {
  const toast = useToast();
  const navigate = useNavigate();
  const { adoptVersion, refreshVersions, refreshDatasets, refreshDataset, selectVersion } = useApp();

  const syncLists = useCallback(async () => {
    await Promise.all([refreshVersions(), refreshDatasets(), refreshDataset()]);
  }, [refreshVersions, refreshDatasets, refreshDataset]);

  /** Clone any version into a new editable draft. */
  const restoreAsDraft = useCallback(
    async (v: Ref, opts: { fixed?: boolean; goToTimetable?: boolean } = {}): Promise<RestoreResponse> => {
      try {
        const res = await versionsApi.restore(v.id, opts.fixed ? { label: `Fixed draft of ${v.label}` } : {});
        adoptVersion(res.version);
        void syncLists();
        toast.success(opts.fixed ? "Fixed draft created" : "Restored as a new draft", `${res.version.label} is a copy of ${v.label}. ${v.label} itself was not changed.`, {
          testId: "toast-restored",
          action: opts.goToTimetable ? undefined : { label: "Open in timetable", onClick: () => navigate("/timetable"), testId: "toast-open-timetable" },
        });
        if (opts.goToTimetable) navigate("/timetable");
        return res;
      } catch (err) {
        toast.error("Could not restore that version", errorMessage(err));
        throw err;
      }
    },
    [adoptVersion, navigate, syncLists, toast],
  );

  const publish = useCallback(
    async (v: Ref, acknowledgeIncomplete: boolean): Promise<PublishResponse> => {
      const res = await versionsApi.publish(v.id, acknowledgeIncomplete);
      adoptVersion(res.version);
      void syncLists();
      toast.success("Timetable published", res.message, { testId: "toast-published" });
      return res;
    },
    [adoptVersion, syncLists, toast],
  );

  const remove = useCallback(
    async (v: Ref, wasSelected: boolean) => {
      try {
        await versionsApi.remove(v.id);
        const [list] = await Promise.all([refreshVersions(), refreshDatasets(), refreshDataset()]);
        if (wasSelected) selectVersion((list.find((x) => x.status === "published") ?? list[0])?.id ?? null);
        toast.success("Draft deleted", `${v.label} was removed. Other versions are untouched.`);
      } catch (err) {
        toast.error("Could not delete that version", errorMessage(err));
        throw err;
      }
    },
    [refreshDataset, refreshDatasets, refreshVersions, selectVersion, toast],
  );

  return { restoreAsDraft, publish, remove, syncLists };
}
