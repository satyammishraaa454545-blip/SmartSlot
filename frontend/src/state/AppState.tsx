import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  datasetsApi,
  errorMessage,
  isAbort,
  versionsApi,
  type DatasetDetail,
  type DatasetSummary,
  type GenerationResult,
  type Summary,
  type UnscheduledItem,
  type VersionDetail,
  type VersionMeta,
} from "../api";
import { readNumber, writeStorage } from "../lib/storage";

const KEY_DATASET = "smartslot.datasetId";
const KEY_VERSION = "smartslot.versionId";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

/** Snapshot of the most recent "Generate" click, so the result stays visible when you come back to the page. */
export interface LastGeneration {
  datasetId: number;
  versionId: number;
  versionLabel: string;
  result: GenerationResult;
  summary: Summary;
  unscheduled: UnscheduledItem[];
  at: number;
}

export interface AppState {
  // ---- datasets ----
  datasets: DatasetSummary[];
  datasetsStatus: LoadStatus;
  datasetsError: string | null;
  datasetId: number | null;
  /** Full detail of the selected dataset (records, config, availability, import report). */
  dataset: DatasetDetail | null;
  datasetStatus: LoadStatus;
  // ---- versions ----
  versions: VersionMeta[];
  versionId: number | null;
  /** Full detail (entries, unscheduled, validation) of the selected version. */
  version: VersionDetail | null;
  versionStatus: LoadStatus;
  versionError: string | null;
  lastGeneration: LastGeneration | null;

  // ---- actions ----
  selectDataset: (id: number | null) => void;
  selectVersion: (id: number | null) => void;
  refreshDatasets: () => Promise<DatasetSummary[]>;
  refreshDataset: () => Promise<void>;
  refreshVersions: () => Promise<VersionMeta[]>;
  refreshVersion: () => Promise<void>;
  /** A dataset was just imported: add it to the list and select it. */
  adoptImportedDataset: (summary: DatasetSummary) => Promise<void>;
  /** Replace the selected dataset's detail with a fresh copy returned by an edit call. */
  applyDatasetDetail: (detail: DatasetDetail) => void;
  /** Optimistic local change to the selected dataset (caller rolls back on failure). */
  patchDatasetLocal: (fn: (d: DatasetDetail) => DatasetDetail) => void;
  /** A dataset was deleted on the server. */
  forgetDataset: (id: number) => Promise<void>;
  /** A version was created or changed on the server (generate, edit, publish, restore): show it. */
  adoptVersion: (v: VersionDetail, opts?: { select?: boolean }) => void;
  setLastGeneration: (g: LastGeneration | null) => void;
}

const Ctx = createContext<AppState | null>(null);

export const metaOf = (v: VersionDetail): VersionMeta => ({
  id: v.id,
  dataset_id: v.dataset_id,
  seq: v.seq,
  status: v.status,
  status_label: v.status_label,
  label: v.label,
  source: v.source,
  created_at: v.created_at,
  created_by: v.created_by,
  published_at: v.published_at,
  is_complete: v.is_complete,
  parent_version_id: v.parent_version_id,
  notes: v.notes,
  summary: v.summary,
});

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetsStatus, setDatasetsStatus] = useState<LoadStatus>("loading");
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [datasetId, setDatasetId] = useState<number | null>(() => readNumber(KEY_DATASET));
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [datasetStatus, setDatasetStatus] = useState<LoadStatus>("idle");
  const [versions, setVersions] = useState<VersionMeta[]>([]);
  const [versionId, setVersionId] = useState<number | null>(() => readNumber(KEY_VERSION));
  const [version, setVersion] = useState<VersionDetail | null>(null);
  const [versionStatus, setVersionStatus] = useState<LoadStatus>("idle");
  const [versionError, setVersionError] = useState<string | null>(null);
  const [lastGeneration, setLastGeneration] = useState<LastGeneration | null>(null);

  const versionRef = useRef<VersionDetail | null>(null);
  versionRef.current = version;
  const datasetIdRef = useRef(datasetId);
  datasetIdRef.current = datasetId;
  const versionIdRef = useRef(versionId);
  versionIdRef.current = versionId;

  // ---------------------------------------------------------------- persistence
  useEffect(() => writeStorage(KEY_DATASET, datasetId === null ? null : String(datasetId)), [datasetId]);
  useEffect(() => writeStorage(KEY_VERSION, versionId === null ? null : String(versionId)), [versionId]);

  // ---------------------------------------------------------------- dataset list
  const refreshDatasets = useCallback(async (): Promise<DatasetSummary[]> => {
    try {
      const list = await datasetsApi.list();
      setDatasets(list);
      setDatasetsStatus("ready");
      setDatasetsError(null);
      // Tolerate a stale / missing stored id: fall back to the newest dataset (or none).
      setDatasetId((cur) => (cur !== null && list.some((d) => d.id === cur) ? cur : (list[0]?.id ?? null)));
      return list;
    } catch (err) {
      setDatasetsStatus("error");
      setDatasetsError(errorMessage(err));
      return [];
    }
  }, []);

  useEffect(() => {
    void refreshDatasets();
  }, [refreshDatasets]);

  // ---------------------------------------------------------------- selected dataset (+ its versions)
  const loadSeq = useRef(0);
  // Only fetch a dataset the server has told us about: a stale id from localStorage must not cause 404s.
  const datasetKnown = datasetId !== null && datasets.some((d) => d.id === datasetId);
  useEffect(() => {
    if (datasetId !== null && !datasetKnown) {
      if (datasetsStatus === "ready") setDatasetId(null); // list loaded but the id is not in it
      return;
    }
    if (datasetId === null) {
      setDataset(null);
      setDatasetStatus("idle");
      setVersions([]);
      setVersionId(null);
      setVersion(null);
      setVersionStatus("idle");
      return;
    }
    const seq = ++loadSeq.current;
    const ctrl = new AbortController();
    setDatasetStatus("loading");
    Promise.all([datasetsApi.get(datasetId, ctrl.signal), versionsApi.listForDataset(datasetId, ctrl.signal)])
      .then(([detail, list]) => {
        if (seq !== loadSeq.current) return;
        setDataset(detail);
        setDatasetStatus("ready");
        setVersions(list);
        // keep the stored version if it belongs to this dataset, otherwise use the newest one
        setVersionId((cur) => (cur !== null && list.some((v) => v.id === cur) ? cur : (list[0]?.id ?? null)));
      })
      .catch((err) => {
        if (isAbort(err) || seq !== loadSeq.current) return;
        if (err instanceof ApiError && err.status === 404) {
          void refreshDatasets(); // stale id: reconcile with the server
          return;
        }
        setDatasetStatus("error");
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, datasetKnown]);

  // ---------------------------------------------------------------- selected version
  // Same rule: only fetch a version that the dataset's version list contains.
  const versionKnown = versionId !== null && versions.some((v) => v.id === versionId);
  useEffect(() => {
    if (versionId === null) {
      setVersion(null);
      setVersionStatus(datasetId === null ? "idle" : "ready");
      return;
    }
    if (!versionKnown) return; // wait for the list (the dataset effect corrects a stale id)
    if (versionRef.current?.id === versionId) return; // already loaded (e.g. just generated)
    const ctrl = new AbortController();
    setVersionStatus("loading");
    setVersionError(null);
    versionsApi
      .get(versionId, ctrl.signal)
      .then((v) => {
        setVersion(v);
        setVersionStatus("ready");
      })
      .catch((err) => {
        if (isAbort(err)) return;
        setVersion(null);
        if (err instanceof ApiError && err.status === 404) {
          setVersionId(null); // deleted elsewhere
          setVersionStatus("ready");
          return;
        }
        setVersionError(errorMessage(err));
        setVersionStatus("error");
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, versionKnown]);

  // ---------------------------------------------------------------- actions
  const selectDataset = useCallback((id: number | null) => {
    if (id === datasetIdRef.current) return;
    setVersionId(null);
    setVersion(null);
    setVersions([]);
    setDataset(null);
    setDatasetId(id);
  }, []);

  const selectVersion = useCallback((id: number | null) => setVersionId(id), []);

  const refreshDataset = useCallback(async () => {
    const id = datasetIdRef.current;
    if (id === null) return;
    try {
      const detail = await datasetsApi.get(id);
      if (datasetIdRef.current === id) setDataset(detail);
    } catch {
      /* keep the data we already have */
    }
  }, []);

  const refreshVersions = useCallback(async (): Promise<VersionMeta[]> => {
    const id = datasetIdRef.current;
    if (id === null) return [];
    try {
      const list = await versionsApi.listForDataset(id);
      if (datasetIdRef.current === id) setVersions(list);
      return list;
    } catch {
      return [];
    }
  }, []);

  const refreshVersion = useCallback(async () => {
    const id = versionIdRef.current;
    if (id === null) return;
    try {
      const v = await versionsApi.get(id);
      if (versionIdRef.current === id) {
        setVersion(v);
        setVersionStatus("ready");
        setVersions((cur) => cur.map((m) => (m.id === v.id ? metaOf(v) : m)));
      }
    } catch (err) {
      setVersionError(errorMessage(err));
    }
  }, []);

  const adoptImportedDataset = useCallback(
    async (summary: DatasetSummary) => {
      setDatasets((cur) => [summary, ...cur.filter((d) => d.id !== summary.id)]);
      selectDataset(summary.id);
      await refreshDatasets();
    },
    [refreshDatasets, selectDataset],
  );

  const applyDatasetDetail = useCallback((detail: DatasetDetail) => {
    setDataset((cur) => (cur && cur.id === detail.id ? detail : cur));
    setDatasets((cur) => cur.map((d) => (d.id === detail.id ? { ...d, ...summaryOf(detail) } : d)));
  }, []);

  const patchDatasetLocal = useCallback((fn: (d: DatasetDetail) => DatasetDetail) => {
    setDataset((cur) => (cur ? fn(cur) : cur));
  }, []);

  const forgetDataset = useCallback(
    async (id: number) => {
      setDatasets((cur) => cur.filter((d) => d.id !== id));
      if (datasetIdRef.current === id) {
        setVersionId(null);
        setVersion(null);
      }
      await refreshDatasets(); // also moves the selection to another dataset when needed
    },
    [refreshDatasets],
  );

  const adoptVersion = useCallback((v: VersionDetail, opts?: { select?: boolean }) => {
    // A slow request (generate, edit, publish ...) can finish after the user switched to another dataset:
    // its version belongs to the other dataset and must not replace the selection or enter this version list.
    if (v.dataset_id !== datasetIdRef.current) return;
    const select = opts?.select ?? true;
    if (select) {
      setVersion(v);
      setVersionStatus("ready");
      setVersionError(null);
      setVersionId(v.id);
    } else if (versionRef.current?.id === v.id) {
      setVersion(v);
    }
    setVersions((cur) => {
      const meta = metaOf(v);
      return cur.some((m) => m.id === v.id) ? cur.map((m) => (m.id === v.id ? meta : m)) : [meta, ...cur];
    });
  }, []);

  const value = useMemo<AppState>(
    () => ({
      datasets,
      datasetsStatus,
      datasetsError,
      datasetId,
      dataset,
      datasetStatus,
      versions,
      versionId,
      version,
      versionStatus,
      versionError,
      lastGeneration,
      selectDataset,
      selectVersion,
      refreshDatasets,
      refreshDataset,
      refreshVersions,
      refreshVersion,
      adoptImportedDataset,
      applyDatasetDetail,
      patchDatasetLocal,
      forgetDataset,
      adoptVersion,
      setLastGeneration,
    }),
    [
      datasets,
      datasetsStatus,
      datasetsError,
      datasetId,
      dataset,
      datasetStatus,
      versions,
      versionId,
      version,
      versionStatus,
      versionError,
      lastGeneration,
      selectDataset,
      selectVersion,
      refreshDatasets,
      refreshDataset,
      refreshVersions,
      refreshVersion,
      adoptImportedDataset,
      applyDatasetDetail,
      patchDatasetLocal,
      forgetDataset,
      adoptVersion,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function summaryOf(d: DatasetDetail): DatasetSummary {
  return {
    id: d.id,
    name: d.name,
    semester: d.semester,
    source: d.source,
    import_status: d.import_status,
    created_at: d.created_at,
    updated_at: d.updated_at,
    counts: d.counts,
    error_count: d.error_count,
    warning_count: d.warning_count,
    total_sessions: d.total_sessions,
    version_count: d.version_count,
    published_version_id: d.published_version_id,
  };
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside <AppStateProvider>");
  return ctx;
}
