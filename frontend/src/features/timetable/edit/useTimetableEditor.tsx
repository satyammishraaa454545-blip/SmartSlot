import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { MapPinOff, Pencil } from "lucide-react";
import {
  ApiError,
  errorMessage,
  versionsApi,
  type Conflict,
  type DatasetDetail,
  type EditResponse,
  type Entry,
  type MoveRequest,
  type MoveResult,
  type Suggestion,
  type UnscheduledItem,
  type VersionDetail,
  type ViewKind,
} from "../../../api";
import { Button, ConfirmDialog, useToast } from "../../../components/ui";
import { dayName } from "../../../lib/format";
import { useApp } from "../../../state/AppState";
import type { Slot } from "../gridModel";
import { EditSessionDialog, type EditPreview } from "./EditSessionDialog";
import { describeChange, formOf, viewForClash, type SlotForm } from "./helpers";
import { LastChangeCard, type LastChange } from "./LastChangeCard";
import { MoveBlockedDialog, type BlockedMove } from "./MoveBlockedDialog";
import { useDragCheck } from "./useDragCheck";

type Editing = { mode: "edit"; entry: Entry; initial: SlotForm | null } | { mode: "place"; item: UnscheduledItem };

interface Args {
  version: VersionDetail;
  dataset: DatasetDetail;
  /** switch the timetable to another batch / teacher / room */
  go: (view: ViewKind, id?: string) => void;
  /** the current view and entity (to know whether a clashing class is visible) */
  view: ViewKind;
  entityId: string;
  /** close the read-only details drawer when an editor opens */
  clearSelection: () => void;
}

type CommitFn = (res: EditResponse, before: Entry | null, opts: { title: string; undo: (() => Promise<EditResponse>) | null }) => void;

const moveBodyOf = (e: Entry): MoveRequest => ({ day: e.day, start_period: e.start_period, room_id: e.room_id, teacher_id: e.teacher_id });

/**
 * All the editing behaviour of the Timetable page in one place: the edit / place dialog, drag and drop with
 * pre-validation, the "Move blocked" modal, unschedule with confirmation, undo and the "last change" card.
 * Only drafts are editable; for other versions `editable` is false and nothing here can send a write request.
 */
export function useTimetableEditor({ version, dataset, go, view, entityId, clearSelection }: Args) {
  const toast = useToast();
  const { adoptVersion } = useApp();
  const editable = version.status === "draft";

  const [editing, setEditing] = useState<Editing | null>(null);
  const [preview, setPreview] = useState<EditPreview>({ clashIds: [], slot: null });
  const [blocked, setBlocked] = useState<BlockedMove | null>(null);
  const [applying, setApplying] = useState(false);
  const [unscheduleTarget, setUnscheduleTarget] = useState<Entry | null>(null);
  const [unscheduling, setUnscheduling] = useState(false);
  const [lastChange, setLastChange] = useState<LastChange | null>(null);
  const [undoing, setUndoing] = useState(false);
  const changeSeq = useRef(0);

  const drag = useDragCheck(version.id, version.dataset.days, version.dataset.periods);

  // ------------------------------------------------------------------ after a successful write
  const commit: CommitFn = useCallback(
    (res, before, opts) => {
      adoptVersion(res.version);
      const after = res.entry;
      const summary = describeChange(before, after ?? null);
      const st = res.version.summary;
      const stillValid = st.status !== "invalid";
      const id = ++changeSeq.current;

      const undoFn = opts.undo
        ? async () => {
            setUndoing(true);
            try {
              const back = await opts.undo!();
              commit(back, after ?? null, { title: "Change undone", undo: null });
            } catch (err) {
              toast.error("Could not undo that change", errorMessage(err));
            } finally {
              setUndoing(false);
            }
          }
        : null;

      setLastChange({ id, versionId: res.version.id, summary, validation: st, at: Date.now(), undo: undoFn });
      toast.success(
        stillValid ? `${opts.title} · timetable still valid` : `${opts.title} · ${st.error_count} conflict${st.error_count === 1 ? "" : "s"} elsewhere still need attention`,
        summary.headline,
        { testId: "toast-change-saved", action: undoFn ? { label: "Undo", onClick: () => void undoFn(), testId: "toast-undo" } : undefined },
      );
    },
    [adoptVersion, toast],
  );

  // ------------------------------------------------------------------ writes
  const applyMove = useCallback(
    async (entry: Entry, body: MoveRequest, label = "Change saved"): Promise<boolean> => {
      setApplying(true);
      try {
        const res = await versionsApi.moveEntry(version.id, entry.entry_id, body);
        commit(res, entry, { title: label, undo: () => versionsApi.moveEntry(version.id, entry.entry_id, moveBodyOf(entry)) });
        return true;
      } catch (err) {
        if (err instanceof ApiError && err.code === "MOVE_REJECTED") {
          // the server disagreed (for example the timetable changed in the meantime): explain, save nothing
          const d = err.detail as unknown as MoveResult;
          setBlocked({
            entry,
            target: { day: body.day ?? entry.day, period: body.start_period ?? entry.start_period },
            result: { ...d, message: d.message ?? err.message },
          });
        } else {
          toast.error("The change was not saved", errorMessage(err));
        }
        return false;
      } finally {
        setApplying(false);
      }
    },
    [commit, toast, version.id],
  );

  const doUnschedule = useCallback(async () => {
    const entry = unscheduleTarget;
    if (!entry) return;
    setUnscheduling(true);
    try {
      const res = await versionsApi.unscheduleEntry(version.id, entry.entry_id);
      setUnscheduleTarget(null);
      commit(res, entry, {
        title: "Session unscheduled",
        undo: () => versionsApi.place(version.id, entry.entry_id, { day: entry.day, start_period: entry.start_period, room_id: entry.room_id, teacher_id: entry.teacher_id }),
      });
    } catch (err) {
      toast.error("Could not unschedule the session", errorMessage(err));
    } finally {
      setUnscheduling(false);
    }
  }, [commit, toast, unscheduleTarget, version.id]);

  const onEditSaved = useCallback(
    (res: EditResponse, before: Entry | null) => {
      setEditing(null);
      if (before) {
        commit(res, before, { title: "Change saved", undo: () => versionsApi.moveEntry(version.id, before.entry_id, moveBodyOf(before)) });
      } else if (res.entry) {
        const placed = res.entry;
        commit(res, null, { title: "Session placed", undo: () => versionsApi.unscheduleEntry(version.id, placed.entry_id) });
      }
    },
    [commit, version.id],
  );

  // ------------------------------------------------------------------ drag and drop
  const onDropEntry = useCallback(
    async (entryId: string, slot: Slot) => {
      const entry = version.entries.find((e) => e.entry_id === entryId);
      if (!entry) return;
      const inOwnSpan = entry.day === slot.day && slot.period >= entry.start_period && slot.period <= entry.end_period;
      if (inOwnSpan) return; // dropped where it already is
      let result: MoveResult;
      try {
        result = await drag.resultFor(entry, slot);
      } catch (err) {
        toast.error("Could not check that move", errorMessage(err));
        return;
      }
      if (result.valid) {
        await applyMove(entry, { day: slot.day, start_period: slot.period }, "Change saved");
      } else {
        setBlocked({ entry, target: slot, result });
      }
    },
    [applyMove, drag, toast, version.entries],
  );

  const applySuggestion = useCallback(
    async (b: BlockedMove, s: Suggestion) => {
      const ok = await applyMove(b.entry, { day: s.day, start_period: s.start_period, room_id: s.room_id, teacher_id: s.teacher_id ?? undefined }, "Change saved");
      if (ok) setBlocked(null);
    },
    [applyMove],
  );

  // ------------------------------------------------------------------ navigation helpers
  const showEntry = useCallback(
    (entry: Entry, conflicts: Conflict[]) => {
      const visible = view === "batch" ? entry.batch_id === entityId : view === "teacher" ? entry.teacher_id === entityId : entry.room_id === entityId;
      if (!visible) {
        const t = viewForClash(entry, conflicts);
        go(t.view, t.id);
      }
      window.setTimeout(() => document.querySelector(`[data-entry-id="${CSS.escape(entry.entry_id)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" }), 120);
    },
    [entityId, go, view],
  );

  const openEdit = useCallback(
    (entry: Entry, initial: SlotForm | null = null) => {
      clearSelection();
      setBlocked(null);
      setEditing({ mode: "edit", entry, initial });
    },
    [clearSelection],
  );

  // ------------------------------------------------------------------ what the page renders
  const clashIds = useMemo(() => {
    const ids = new Set(preview.clashIds);
    blocked?.result.affected_entries.forEach((e) => ids.add(e.entry_id));
    return ids;
  }, [preview.clashIds, blocked]);

  const highlightSlots: Slot[] = useMemo(() => {
    if (blocked) return [blocked.target];
    if (editing && preview.slot) return [preview.slot];
    return [];
  }, [blocked, editing, preview.slot]);

  const drawerFooter = (entry: Entry): ReactNode =>
    editable ? (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="primary" icon={<Pencil className="h-4 w-4" aria-hidden />} onClick={() => openEdit(entry)} data-testid="edit-session">
          Edit session
        </Button>
        <Button
          icon={<MapPinOff className="h-4 w-4" aria-hidden />}
          onClick={() => {
            clearSelection();
            setUnscheduleTarget(entry);
          }}
          data-testid="unschedule-session"
        >
          Unschedule
        </Button>
      </div>
    ) : (
      <p className="text-sm text-slate-500" data-testid="drawer-readonly">
        This version is read-only. Restore it as a draft to edit this class.
      </p>
    );

  const unscheduledActions = (item: UnscheduledItem): ReactNode =>
    editable ? (
      <Button size="sm" variant="primary" onClick={() => setEditing({ mode: "place", item })} data-testid="place-session" data-session-id={item.session_id}>
        Place this session...
      </Button>
    ) : null;

  const dialogs = (
    <>
      <EditSessionDialog
        key={editing ? `${editing.mode}-${editing.mode === "edit" ? editing.entry.entry_id : editing.item.session_id}` : "none"}
        mode={editing?.mode ?? "edit"}
        version={version}
        dataset={dataset}
        entry={editing?.mode === "edit" ? editing.entry : null}
        item={editing?.mode === "place" ? editing.item : null}
        initial={editing?.mode === "edit" ? editing.initial : null}
        onClose={() => setEditing(null)}
        onSaved={onEditSaved}
        onPreview={setPreview}
        onShowEntry={showEntry}
      />
      <MoveBlockedDialog
        blocked={blocked}
        applying={applying}
        onClose={() => setBlocked(null)}
        onApply={(b, s) => void applySuggestion(b, s)}
        onEdit={(b) => openEdit(b.entry, { ...formOf(b.entry), day: b.target.day, start: b.target.period })}
        onShowEntry={showEntry}
      />
      <ConfirmDialog
        open={!!unscheduleTarget}
        title="Take this class off the timetable?"
        confirmLabel="Unschedule"
        danger
        busy={unscheduling}
        onConfirm={() => void doUnschedule()}
        onCancel={() => setUnscheduleTarget(null)}
        data-testid="unschedule-dialog"
        confirmTestId="unschedule-confirm"
      >
        {unscheduleTarget && (
          <p>
            <strong className="text-slate-900">
              {unscheduleTarget.subject_name} ({unscheduleTarget.batch_name})
            </strong>{" "}
            on {dayName(unscheduleTarget.day)}, Period {unscheduleTarget.start_period} will move to the <em>Unscheduled sessions</em> list and the timetable will be marked incomplete. You can place it again later, or undo this straight after.
          </p>
        )}
      </ConfirmDialog>
    </>
  );

  const lastChangeCard =
    lastChange && lastChange.versionId === version.id ? (
      <LastChangeCard
        change={lastChange}
        undoing={undoing}
        onUndo={() => void lastChange.undo?.()}
        onDismiss={() => setLastChange(null)}
        onShowEntity={(v, id) => go(v, id)}
      />
    ) : null;

  return {
    editable,
    showEntry,
    openEdit,
    drawerFooter,
    unscheduledActions,
    dialogs,
    lastChangeCard,
    highlightEntryIds: clashIds,
    highlightSlots,
    grid: editable
      ? {
          onDropEntry: (id: string, slot: Slot) => void onDropEntry(id, slot),
          onDragStartEntry: drag.start,
          onDragEndEntry: drag.end,
          dragStatus: drag.checks,
          draggingId: drag.dragging?.entry_id ?? null,
        }
      : {},
  };
}
