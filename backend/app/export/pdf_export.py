"""PDF export: one landscape A4 page per batch / teacher / room.

Each page shows a weekly grid (days across, periods down, breaks shaded), with
multi-period practicals merged into one tall cell, plus a header with the
version label and a published / draft badge and a colour legend.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..engine.labels import day_name
from ..engine.models import Dataset
from ..schemas import EntryOut
from .fonts import pdf_fonts

PAGE = landscape(A4)
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 24, 22, 30
VIEWS = ("batch", "teacher", "room")

_PALETTE = ["#dbeafe", "#dcfce7", "#fef3c7", "#fce7f3", "#e0e7ff", "#ccfbf1", "#ffedd5", "#ede9fe", "#fae8ff", "#ecfccb"]
_BADGE = {"published": "#15803d", "draft": "#b45309", "archived": "#6b7280"}
INK, MUTED, GRID, HEAD_BG, SIDE_BG, BREAK_BG, CLASH_BG = (
    "#0f172a", "#475569", "#cbd5e1", "#1e293b", "#f1f5f9", "#e2e8f0", "#fecaca")


@dataclass
class PdfMeta:
    dataset_name: str
    semester: str
    version_label: str
    status: str  # draft | published | archived
    incomplete: bool  # some required sessions are not scheduled
    generated_on: str = ""

    def __post_init__(self) -> None:
        if not self.generated_on:
            self.generated_on = datetime.now().strftime("%d %b %Y")


@dataclass
class Entity:
    entity_id: str
    title: str
    subtitle: str


def list_entities(dataset: Dataset, view: str) -> list[Entity]:
    if view == "batch":
        return [Entity(b.batch_id, b.name, f"{b.student_count} students" + (f" - {b.department_id}" if b.department_id else ""))
                for b in dataset.batches]
    if view == "teacher":
        return [Entity(t.teacher_id, t.name, t.department_id and f"Department {t.department_id}" or "Teacher")
                for t in dataset.teachers]
    if view == "room":
        return [Entity(r.room_id, r.name, f"{'Laboratory' if r.room_type == 'lab' else 'Classroom'} - {r.capacity} seats")
                for r in dataset.rooms]
    raise ValueError(f"unknown view {view!r}")


def _esc(text: object) -> str:
    return escape(str(text))


class _Styles:
    def __init__(self, compact: bool) -> None:
        regular, bold = pdf_fonts()
        big = 8.6 if compact else 9.6
        small = 7.0 if compact else 7.8
        self.title = ParagraphStyle("t", fontName=bold, fontSize=18, leading=21, textColor=colors.HexColor(INK))
        self.sub = ParagraphStyle("s", fontName=regular, fontSize=9.5, leading=12, textColor=colors.HexColor(MUTED))
        self.right = ParagraphStyle("r", parent=self.sub, alignment=TA_RIGHT)
        self.right_bold = ParagraphStyle("rb", parent=self.right, fontName=bold, textColor=colors.HexColor(INK))
        self.badge = ParagraphStyle("b", fontName=bold, fontSize=8.5, leading=10, textColor=colors.white, alignment=TA_CENTER)
        self.day = ParagraphStyle("d", fontName=bold, fontSize=9.5, leading=11, textColor=colors.white, alignment=TA_CENTER)
        self.side = ParagraphStyle("p", fontName=regular, fontSize=7.8, leading=9.6, textColor=colors.HexColor(MUTED))
        self.cell_title = ParagraphStyle("ct", fontName=bold, fontSize=big, leading=big + 1.6, textColor=colors.HexColor(INK), alignment=TA_CENTER)
        self.cell_meta = ParagraphStyle("cm", fontName=regular, fontSize=small, leading=small + 1.8, textColor=colors.HexColor("#334155"), alignment=TA_CENTER)
        self.brk = ParagraphStyle("k", fontName=regular, fontSize=8.5, leading=10, textColor=colors.HexColor(MUTED), alignment=TA_CENTER)
        self.legend = ParagraphStyle("l", fontName=regular, fontSize=7.6, leading=9.2, textColor=colors.HexColor("#334155"))
        self.note = ParagraphStyle("n", fontName=regular, fontSize=8, leading=10, textColor=colors.HexColor("#b91c1c"))


def _entry_cell(e: EntryOut, view: str, st: _Styles) -> list:
    if view == "batch":
        meta = f"{e.teacher_name} - {e.room_name}"
    elif view == "teacher":
        meta = f"{e.batch_name} - {e.room_name}"
    else:
        meta = f"{e.batch_name} - {e.teacher_name}"
    out = [Paragraph(_esc(e.subject_name), st.cell_title), Paragraph(_esc(meta), st.cell_meta)]
    if e.subject_type == "practical":
        out.append(Paragraph("Practical / Lab", st.cell_meta))
    return out


def _filter(entries: list[EntryOut], view: str, entity_id: str) -> list[EntryOut]:
    key = {"batch": "batch_id", "teacher": "teacher_id", "room": "room_id"}[view]
    return [e for e in entries if getattr(e, key) == entity_id]


def _header(meta: PdfMeta, entity: Entity, view: str, st: _Styles, width: float) -> Table:
    left = [Paragraph(_esc(entity.title), st.title),
            Paragraph(_esc(f"{view.capitalize()} timetable - {entity.subtitle}"), st.sub),
            Paragraph(_esc(f"{meta.dataset_name}" + (f" - Semester {meta.semester}" if meta.semester else "")), st.sub)]
    right_w = width * 0.38
    chips = [(meta.status.upper(), _BADGE.get(meta.status, "#6b7280"))]
    if meta.incomplete:
        chips.append(("INCOMPLETE", "#b91c1c"))
    badge_table = Table([[""] + [Paragraph(text, st.badge) for text, _c in chips]],
                        colWidths=[right_w - 78 * len(chips)] + [78] * len(chips))
    badge_style = [("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]
    for i, (_text, colour_hex) in enumerate(chips, start=1):
        badge_style.append(("BACKGROUND", (i, 0), (i, 0), colors.HexColor(colour_hex)))
        badge_style.append(("LINEBEFORE", (i, 0), (i, 0), 4, colors.white))
    badge_table.setStyle(TableStyle(badge_style))
    right = [badge_table, Spacer(1, 4),
             Paragraph(_esc(meta.version_label), st.right_bold),
             Paragraph(_esc(f"Generated {meta.generated_on}"), st.right)]
    table = Table([[left, right]], colWidths=[width * 0.62, right_w])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return table


def _grid(dataset: Dataset, entries: list[EntryOut], view: str, colour: dict[str, str], st: _Styles,
          width: float, height: float) -> tuple[Table, list[EntryOut]]:
    """Weekly grid table and the entries that could not be drawn (outside the grid)."""
    days = list(dataset.config.days)
    periods = sorted(dataset.config.periods, key=lambda p: p.period)
    row_of = {p.period: i + 1 for i, p in enumerate(periods)}  # row 0 is the day header
    is_break = {p.period: p.is_break for p in periods}
    side_w = 74.0
    col_w = (width - side_w) / max(len(days), 1)

    taken: dict[tuple[str, int], EntryOut] = {}
    extras: dict[tuple[str, int], list[EntryOut]] = {}
    undrawn: list[EntryOut] = []
    for e in entries:
        span = list(range(e.start_period, e.end_period + 1))
        if e.day not in days or e.start_period not in row_of:
            undrawn.append(e)
        elif all(p in row_of and not is_break[p] and (e.day, p) not in taken for p in span):
            for p in span:
                taken[(e.day, p)] = e
        else:  # overlaps something else (a clash) or runs over a break: show it, flagged
            host = next((taken[(e.day, p)] for p in span if (e.day, p) in taken), None)
            key = (host.day, host.start_period) if host else (e.day, e.start_period)
            extras.setdefault(key, []).append(e)

    data: list[list] = [[""] + [Paragraph(_esc(day_name(d)), st.day) for d in days]]
    style: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD_BG)),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor(SIDE_BG)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(GRID)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    teaching_rows = sum(1 for p in periods if not p.is_break)
    break_rows = len(periods) - teaching_rows
    break_h = 20.0
    head_h = 22.0
    row_h = max(34.0, min(64.0, (height - head_h - break_rows * break_h) / max(teaching_rows, 1)))
    heights = [head_h]
    for p in periods:
        r = row_of[p.period]
        side = Paragraph(f"<b>{'Break' if p.is_break else f'Period {p.period}'}</b><br/>{_esc(p.start)} - {_esc(p.end)}", st.side)
        row: list = [side] + [""] * len(days)
        if p.is_break:
            row[1] = Paragraph("Break", st.brk)
            style += [("SPAN", (1, r), (len(days), r)), ("BACKGROUND", (1, r), (len(days), r), colors.HexColor(BREAK_BG))]
            heights.append(break_h)
        else:
            heights.append(row_h)
            for c, d in enumerate(days, start=1):
                e = taken.get((d, p.period))
                if e is not None and e.start_period == p.period:
                    cell = _entry_cell(e, view, st)
                    for extra in extras.get((d, p.period), []):
                        cell += _entry_cell(extra, view, st)
                    row[c] = cell
                    bg = CLASH_BG if extras.get((d, p.period)) else colour.get(e.subject_id, "#ffffff")
                    style.append(("BACKGROUND", (c, r), (c, r + e.duration - 1), colors.HexColor(bg)))
                    if e.duration > 1:
                        style.append(("SPAN", (c, r), (c, r + e.duration - 1)))
                elif e is None and extras.get((d, p.period)):
                    row[c] = [flow for x in extras[(d, p.period)] for flow in _entry_cell(x, view, st)]
                    style.append(("BACKGROUND", (c, r), (c, r), colors.HexColor(CLASH_BG)))
        data.append(row)
    table = Table(data, colWidths=[side_w] + [col_w] * len(days), rowHeights=heights)
    table.setStyle(TableStyle(style))
    return table, undrawn


def _legend(dataset: Dataset, entries: list[EntryOut], colour: dict[str, str], st: _Styles, width: float) -> Optional[Table]:
    names = {s.subject_id: s for s in dataset.subjects}
    order = list(names)
    used = sorted({e.subject_id for e in entries}, key=lambda sid: order.index(sid) if sid in names else len(order))
    if not used:
        return None
    per_row = 4
    cells = []
    for sid in used:
        subject = names.get(sid)
        label = f"{sid} - {subject.name}" if subject else sid
        if subject is not None and subject.session_type == "practical":
            label += " (practical)"
        chip = f'<font backColor="{colour.get(sid, "#ffffff")}">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</font>&nbsp;&nbsp;'
        cells.append(Paragraph(chip + _esc(label), st.legend))
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    rows = [r + [""] * (per_row - len(r)) for r in rows]
    table = Table(rows, colWidths=[width / per_row] * per_row)
    table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return table


def build_pdf(
    meta: PdfMeta, dataset: Dataset, entries: list[EntryOut], view: str, entity_id: Optional[str] = None
) -> bytes:
    """Render the timetable.  ``entity_id=None`` -> one page per entity of the view."""
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}")
    entities = list_entities(dataset, view)
    if entity_id is not None:
        entities = [e for e in entities if e.entity_id == entity_id]
    if not entities:
        raise LookupError(entity_id or view)

    colour = {s.subject_id: _PALETTE[i % len(_PALETTE)] for i, s in enumerate(dataset.subjects)}
    n_rows = len(dataset.config.periods)
    st = _Styles(compact=n_rows > 8 or len(dataset.config.days) > 5)
    regular, _bold = pdf_fonts()

    page_w, page_h = PAGE
    frame_w = page_w - 2 * MARGIN_X
    frame_h = page_h - MARGIN_TOP - MARGIN_BOTTOM
    grid_h = frame_h - 96 - 40  # header + legend allowance

    def footer(canvas, doc) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(MARGIN_X, 14, f"SmartSlot  |  {meta.dataset_name}  |  {meta.version_label}  |  {meta.status}")
        canvas.drawRightString(page_w - MARGIN_X, 14, f"Page {doc.page}")
        canvas.setStrokeColor(colors.HexColor(GRID))
        canvas.line(MARGIN_X, 24, page_w - MARGIN_X, 24)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=PAGE, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
        title=f"Timetable - {meta.dataset_name} - {meta.version_label}", author="SmartSlot",
        subject=f"{view.capitalize()} timetable", creator="SmartSlot",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[Frame(MARGIN_X, MARGIN_BOTTOM, frame_w, frame_h, id="f",
                                                                leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=footer, pagesize=PAGE)])
    story: list = []
    for i, entity in enumerate(entities):
        mine = _filter(entries, view, entity.entity_id)
        if i:
            story.append(PageBreak())
        story.append(_header(meta, entity, view, st, frame_w))
        grid, undrawn = _grid(dataset, mine, view, colour, st, frame_w, grid_h)
        story.append(grid)
        story.append(Spacer(1, 8))
        legend = _legend(dataset, mine, colour, st, frame_w)
        if legend is not None:
            story.append(legend)
        elif not mine:
            story.append(Paragraph("No classes are scheduled for this " + view + " in this version.", st.legend))
        if undrawn:
            story.append(Paragraph(f"{len(undrawn)} class(es) are outside the configured days/periods and cannot be drawn "
                                   "in this grid; check the validation report.", st.note))
    doc.build(story)
    return buf.getvalue()
