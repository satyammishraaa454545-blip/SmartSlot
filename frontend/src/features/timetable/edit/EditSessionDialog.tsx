import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Loader2, OctagonX, Save, ShieldCheck } from "lucide-react";
import {
  ApiError,
  errorMessage,
  versionsApi,
  type Conflict,
  type DatasetDetail,
  type Day,
  type EditResponse,
  type Entry,
  type MoveResult,
  type Suggestion,
  type UnscheduledItem,
  type VersionDetail,
} from "../../../api";
import { Button, Drawer } from "../../../components/ui";
import { dayName, plural } from "../../../lib/format";
import type { Slot } from "../gridModel";
import { formFromSuggestion, formOf, periodLabel, roomOptions, sameForm, teacherOptions, teachingPeriods, type SlotForm } from "./helpers";
import { AffectedEntries, BlockedHeading, ConflictList, SuggestionChips } from "./MoveFeedback";
import { useLiveCheck } from "./useLiveCheck";

export interface EditPreview {
  /** classes the proposed change would clash with (outlined in the grid) */
  clashIds: string[];
  /** the slot the form currently points at */
  slot: Slot | null;
}

interface Props {
  mode: "edit" | "place";
  version: VersionDetail;
  dataset: DatasetDetail;
  /** the class being edited (mode "edit") */
  entry?: Entry | null;
  /** the unscheduled session being placed (mode "place") */
  item?: UnscheduledItem | null;
  /** start the form on this slot (for example the slot a drag was dropped on) */
  initial?: SlotForm | null;
  onClose: () => void;
  onSaved: (res: EditResponse, before: Entry | null) => void;
  onPreview: (p: EditPreview) => void;
  /** jump to a clashing class in the grid */
  onShowEntry: (entry: Entry, conflicts: Conflict[]) => void;
}

const DEFAULT_PLACE: Pick<SlotForm, "day" | "start"> = { day: "Mon", start: 1 };

function FieldLabel({ id, children }: { id: string; children: string }) {
  return (
    <label htmlFor={id} className="label">
      {children}
    </label>
  );
}

/**
 * Edit a scheduled class (day, period, room, teacher) or place an unscheduled one. Every change of the form is
 * checked on the server with a dry run, so the coordinator sees a green "valid" or a plain-English list of blocking
 * clashes before anything is saved. The save button stays disabled while the proposal is invalid.
 */
export function EditSessionDialog({ mode, version, dataset, entry, item, initial, onClose, onSaved, onPreview, onShowEntry }: Props) {
  const target = mode === "edit" ? entry : item;
  const open = !!target;
  const id = (mode === "edit" ? entry?.entry_id : item?.session_id) ?? "";
  const subjectId = target?.subject_id ?? "";
  const batchId = target?.batch_id ?? "";
  const subjectType = (target?.subject_type === "practical" ? "practical" : "lecture") as "lecture" | "practical";
  const days = version.dataset.days;
  const periods = version.dataset.periods;
  const duration = target?.duration ?? 1;

  const original: SlotForm | null = entry ? formOf(entry) : null;
  const blank: SlotForm = useMemo(
    () => ({
      day: days[0] ?? DEFAULT_PLACE.day,
      start: teachingPeriods(periods)[0]?.period ?? DEFAULT_PLACE.start,
      roomId: roomOptions(dataset, subjectType, batchId).find((r) => r.suitable)?.room.room_id ?? dataset.rooms[0]?.room_id ?? "",
      teacherId: item?.teacher_id ?? "",
    }),
    [days, periods, dataset, subjectType, batchId, item?.teacher_id],
  );

  const [form, setForm] = useState<SlotForm>(initial ?? original ?? blank);
  const [touched, setTouched] = useState(!!initial);
  const [showAll, setShowAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<{ key: string; result: MoveResult } | null>(null);
  const [alternatives, setAlternatives] = useState<Suggestion[]>([]);
  const [loadingAlt, setLoadingAlt] = useState(false);
  // the async suggestion callback must see the latest "touched"
  const touchedRef = useRef(touched);
  touchedRef.current = touched;

  // reset whenever a different class / session is opened
  useEffect(() => {
    setForm(initial ?? original ?? blank);
    setTouched(!!initial);
    setShowAll(false);
    setSaving(false);
    setSaveError(null);
    setRejected(null);
    setAlternatives([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, mode]);

  // proactive suggestions ("Suggested slots" chips)
  useEffect(() => {
    if (!open || !id) return;
    let cancelled = false;
    setLoadingAlt(true);
    const call = mode === "edit" ? versionsApi.entrySuggestions(version.id, id, 6) : versionsApi.unscheduledSuggestions(version.id, id, 6);
    call
      .then((list) => {
        if (cancelled) return;
        setAlternatives(list);
        // placing: start from the best suggestion unless the coordinator already chose something
        if (mode === "place" && list.length > 0) {
          setForm((cur) => (touchedRef.current ? cur : formFromSuggestion(list[0], cur.teacherId || item?.teacher_id || "")));
        }
      })
      .catch(() => {
        if (!cancelled) setAlternatives([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingAlt(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, id, mode, version.id]);

  const unchanged = mode === "edit" && original !== null && sameForm(form, original);
  const formKey = `${id}|${form.day}|${form.start}|${form.roomId}|${form.teacherId}`;
  const body = { day: form.day, start_period: form.start, room_id: form.roomId, teacher_id: form.teacherId || undefined };
  const live = useLiveCheck(formKey, open && !unchanged && !!form.roomId, () =>
    mode === "edit" ? versionsApi.validateMove(version.id, id, body) : versionsApi.validatePlace(version.id, id, { ...body }),
  );

  // a rejected save (409) is shown until the form changes again
  const shownRejected = rejected && rejected.key === formKey ? rejected.result : null;
  const result: MoveResult | null = shownRejected ?? (live.phase === "done" ? live.result : null);
  const checking = live.phase === "checking" && !shownRejected;
  const valid = !!result && result.valid && !checking;
  const canSave = valid && !unchanged && !saving && open;

  // tell the grid which classes clash / which slot is being proposed
  const clashKey = result && !result.valid ? result.affected_entries.map((e) => e.entry_id).join(",") : "";
  useEffect(() => {
    if (!open) return;
    onPreview({ clashIds: clashKey ? clashKey.split(",") : [], slot: { day: form.day, period: form.start } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, clashKey, form.day, form.start]);
  useEffect(() => () => onPreview({ clashIds: [], slot: null }), []); // eslint-disable-line react-hooks/exhaustive-deps

  const change = (patch: Partial<SlotForm>) => {
    setTouched(true);
    setSaveError(null);
    setForm((f) => ({ ...f, ...patch }));
  };
  const pick = (s: Suggestion) => {
    setTouched(true);
    setSaveError(null);
    setForm(formFromSuggestion(s, form.teacherId));
  };

  const save = async () => {
    if (!canSave || !target) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = mode === "edit" ? await versionsApi.moveEntry(version.id, id, body) : await versionsApi.place(version.id, id, { ...body, teacher_id: form.teacherId || undefined });
      onSaved(res, entry ?? null);
    } catch (err) {
      if (err instanceof ApiError && err.code === "MOVE_REJECTED") {
        const d = err.detail as unknown as MoveResult;
        setRejected({ key: formKey, result: { ...d, message: err.message } });
        setSaveError(err.message);
      } else {
        setSaveError(errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  // ---- option lists: sensible ones first; "show all" lets the coordinator try anything ----
  const rooms = roomOptions(dataset, subjectType, batchId).filter((r) => showAll || r.suitable || r.room.room_id === form.roomId);
  const teachers = teacherOptions(dataset, subjectId, entry?.teacher_id ?? item?.teacher_id ?? "").filter((t) => showAll || t.suitable || t.teacher.teacher_id === form.teacherId);
  const periodChoices = periods.filter((p) => showAll || !p.is_break || p.period === form.start);
  const hiddenCount =
    dataset.rooms.length - rooms.length + (dataset.teachers.length - teachers.length) + (periods.length - periodChoices.length);

  const title = mode === "edit" ? "Edit session" : "Place session";
  const subtitle = target ? `${target.subject_name} · ${target.batch_name} · ${plural(duration, "period")}` : undefined;

  const suggestionsToShow = result && !result.valid && result.suggestions.length > 0 ? result.suggestions : alternatives;
  const suggestionHeading = result && !result.valid && result.suggestions.length > 0 ? "Try one of these instead" : mode === "edit" ? "Other conflict-free slots" : "Suggested slots";

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={title}
      subtitle={subtitle}
      size="lg"
      light
      data-testid="edit-dialog"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500" aria-live="polite">
            {saving ? "Saving..." : canSave ? "Nothing changes until you save." : unchanged ? "No changes yet." : checking ? "Checking..." : "Save is available once the change is valid."}
          </p>
          <div className="flex gap-2">
            <Button onClick={onClose} disabled={saving} data-testid="cancel-edit">
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void save()} disabled={!canSave} loading={saving} icon={<Save className="h-4 w-4" aria-hidden />} data-testid="save-change">
              {mode === "edit" ? "Save change" : "Place session"}
            </Button>
          </div>
        </div>
      }
    >
      {target && (
        <div className="space-y-5" data-testid="edit-form" data-mode={mode} data-entry-id={id}>
          {entry && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600" data-testid="edit-current">
              Now: <strong className="text-slate-900">{dayName(entry.day)}, Period {entry.start_period}</strong> · {entry.room_name} · {entry.teacher_name}
            </p>
          )}
          {entry?.needs_review && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950" data-testid="edit-needs-review">
              <p className="font-semibold">This class needs review</p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-5">
                {entry.review_messages.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-amber-900/80">Pick a new slot, room or teacher below to fix it.</p>
            </div>
          )}
          {item && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900" data-testid="place-reason">
              {item.reasons[0] ?? "This session is not on the timetable yet."}
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel id="ed-day">Day</FieldLabel>
              <select id="ed-day" className="input" value={form.day} onChange={(e) => change({ day: e.target.value as Day })} data-testid="edit-day" data-autofocus>
                {days.map((d) => (
                  <option key={d} value={d}>
                    {dayName(d)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel id="ed-period">{duration > 1 ? `Start period (${duration} periods)` : "Period"}</FieldLabel>
              <select id="ed-period" className="input" value={form.start} onChange={(e) => change({ start: Number(e.target.value) })} data-testid="edit-period">
                {periodChoices.map((p) => (
                  <option key={p.period} value={p.period}>
                    {periodLabel(p)}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <FieldLabel id="ed-room">Room</FieldLabel>
              <select id="ed-room" className="input" value={form.roomId} onChange={(e) => change({ roomId: e.target.value })} data-testid="edit-room">
                {rooms.map((r) => (
                  <option key={r.room.room_id} value={r.room.room_id}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <FieldLabel id="ed-teacher">Teacher</FieldLabel>
              <select id="ed-teacher" className="input" value={form.teacherId} onChange={(e) => change({ teacherId: e.target.value })} data-testid="edit-teacher">
                {mode === "place" && !form.teacherId && <option value="">Keep the assigned teacher</option>}
                {teachers.map((t) => (
                  <option key={t.teacher.teacher_id} value={t.teacher.teacher_id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-600">
            <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} data-testid="show-all-options" />
            <span>
              Show unsuitable options too
              {!showAll && hiddenCount > 0 && <span className="text-slate-400"> ({hiddenCount} hidden: wrong room type, too small, break periods, other subjects' teachers)</span>}
              <span className="block text-xs text-slate-400">SmartSlot will still explain why they do not work.</span>
            </span>
          </label>

          <LiveResult
            unchanged={unchanged}
            checking={checking}
            result={result}
            error={live.phase === "error" ? live.message : null}
            saveError={shownRejected ? null : saveError}
            rejected={!!shownRejected}
            mode={mode}
            onShow={(e) => onShowEntry(e, result?.conflicts ?? [])}
          />

          {(suggestionsToShow.length > 0 || loadingAlt || mode === "place" || (result && !result.valid)) && (
            <SuggestionChips
              suggestions={suggestionsToShow}
              heading={suggestionHeading}
              loading={loadingAlt && suggestionsToShow.length === 0}
              onPick={pick}
              selected={(s) => s.day === form.day && s.start_period === form.start && s.room_id === form.roomId && (s.teacher_id ?? form.teacherId) === form.teacherId}
              hint={suggestionsToShow.length > 0 ? "Click a slot to fill in the form. It is checked again before you can save." : undefined}
            />
          )}
        </div>
      )}
    </Drawer>
  );
}

/** The live pre-validation box: idle / checking / green valid / red blocked / error. */
function LiveResult({
  unchanged,
  checking,
  result,
  error,
  saveError,
  rejected,
  mode,
  onShow,
}: {
  unchanged: boolean;
  checking: boolean;
  result: MoveResult | null;
  error: string | null;
  saveError: string | null;
  rejected: boolean;
  mode: "edit" | "place";
  onShow: (entry: Entry) => void;
}) {
  if (error) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert" data-testid="live-validation" data-state="error">
        Could not check this change: {error}
      </div>
    );
  }
  if (unchanged && !result) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600" data-testid="live-validation" data-state="idle">
        Change the day, period, room or teacher. SmartSlot checks the new slot instantly, before anything is saved.
      </div>
    );
  }
  if (!result) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600" data-testid="live-validation" data-state="checking" aria-live="polite">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Checking this {mode === "edit" ? "change" : "placement"}...
      </div>
    );
  }
  if (result.valid) {
    return (
      <div
        className={`rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-900 transition-opacity ${checking ? "opacity-60" : ""}`}
        data-testid="live-validation"
        data-state={checking ? "checking" : "valid"}
        role="status"
      >
        <p className="flex items-center gap-2 text-sm font-semibold" data-testid="validation-ok">
          <ShieldCheck className="h-5 w-5 text-emerald-600" aria-hidden /> This {mode === "edit" ? "change" : "placement"} is valid
        </p>
        <p className="mt-1 flex items-start gap-2 text-sm text-emerald-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> No teacher, room or batch is double-booked, and the room and availability rules are respected.
        </p>
      </div>
    );
  }
  return (
    <div
      className={`space-y-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 transition-opacity ${checking ? "opacity-60" : ""}`}
      data-testid="live-validation"
      data-state={checking ? "checking" : "blocked"}
      role="alert"
    >
      <BlockedHeading>
        <span data-testid="validation-blocked">{rejected ? `Not saved. This ${mode === "edit" ? "change" : "placement"} is blocked` : `This ${mode === "edit" ? "change" : "placement"} is blocked`}</span>
        <span className="mt-0.5 block text-xs font-normal text-red-800">
          {plural(result.conflicts.length, "problem")} would be created. Nothing has been saved.
        </span>
      </BlockedHeading>
      <ConflictList conflicts={result.conflicts} />
      <AffectedEntries entries={result.affected_entries} onShow={onShow} />
      {saveError && !rejected && (
        <p className="flex items-start gap-2 text-sm text-red-900">
          <OctagonX className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {saveError}
        </p>
      )}
    </div>
  );
}
