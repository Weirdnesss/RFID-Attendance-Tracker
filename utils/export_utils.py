"""
export_utils.py
---------------

"""
from collections import OrderedDict
from datetime import datetime
from db.students_db import YEAR_LEVEL_LABELS
from database import (SessionLocal, Session as EventSession,
                      SessionPeriod, Attendance, Student,
                      AcademicPeriod, AcademicYear, AcademicTerm)

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as rl_canvas


# ---------------------------------------------------------------------------
# Export data fetcher
# ---------------------------------------------------------------------------

def fetch_session_report(session_id: int) -> dict:
    db = SessionLocal()
    try:
        session = db.query(EventSession).filter_by(id=session_id).first()
        if not session:
            return {}

        periods    = (db.query(SessionPeriod)
                      .filter_by(session_id=session_id)
                      .order_by(SessionPeriod.sort_order)
                      .all())
        period_map = {p.id: p for p in periods}  # id -> full SessionPeriod object

        records = (
            db.query(Attendance, Student)
            .join(Student, Attendance.student_id == Student.student_id)
            .filter(Attendance.session_id == session_id)
            .order_by(Attendance.time_in)
            .all()
        )

        rows    = []
        present = 0
        late    = 0

        for att, stu in records:
            period_obj = period_map.get(att.period_id) if hasattr(att, "period_id") else None
            rows.append({
                "student_id": stu.student_id,
                "name":      f"{stu.first_name} {stu.last_name}",
                "program":   stu.program.name if stu.program else "—",
                "code":      stu.program.code if stu.program else "—",
                "yearlevel": YEAR_LEVEL_LABELS.get(stu.year_level, "—"),
                "status":     att.status,
                "period_id":  att.period_id if hasattr(att, "period_id") else None,
                "period":     period_obj.name if period_obj else "—",
                "time_in":    att.time_in.strftime("%I:%M:%S %p") if att.time_in else "—",
                "time_out":   att.time_out.strftime("%I:%M:%S %p") if att.time_out else "—",
                "department": stu.program.department.name if stu.program and stu.program.department else "—",
                "dept_code":  stu.program.department.code if stu.program and stu.program.department else "—",
            })
            if att.status == "present":
                present += 1
            elif att.status == "late":
                late += 1
                present += 1  # late attendees are also counted as present for summary purposes 

        est    = session.estimated_attendees or 0
        absent = max(0, est - present - late) if est else 0
        rate   = min(round(((present + late) / est) * 100, 1), 100.0) if est else None

        summary = {
            "present":   present,
            "late":      late,
            "absent":    absent,
            "estimated": est,
            "rate":      rate,
            
        }
        academic_period_str = "—"
        if session.academic_period_id:
            ap = db.query(AcademicPeriod).filter_by(id=session.academic_period_id).first()
            if ap:
                term = db.query(AcademicTerm).filter_by(id=ap.term_id).first()
                year = db.query(AcademicYear).filter_by(id=ap.academic_year_id).first()
                if term and year:
                    academic_period_str = f"{term.name}  •  A.Y. {year.year_start}–{year.year_end}"
        return {
            "session":          session,
            "rows":             rows,
            "summary":          summary,
            "period_map":       period_map,                          # id -> SessionPeriod
            "periods":          periods,                             # ordered list
            "any_late_enabled": any(p.late_enabled for p in periods),
            "academic_period": academic_period_str,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Excel exporter
# ---------------------------------------------------------------------------

XL_HEADER_BG  = "1e3a5f"   # deep navy
XL_HEADER_FG  = "ffffff"
XL_ACCENT     = "2563eb"   # blue
XL_SUCCESS    = "16a34a"   # green
XL_WARNING    = "d97706"   # amber
XL_ERROR      = "dc2626"   # red
XL_ROW_ALT    = "f1f5f9"   # light blue-grey
XL_ROW_NORMAL = "ffffff"
XL_TEXT       = "1e293b"   # dark slate
XL_MUTED      = "64748b"   # slate
XL_SECTION_BG = "e8f0fe"   # light blue — period heading

_XL_STATUS_COLORS = {"present": XL_SUCCESS, "late": XL_WARNING, "absent": XL_ERROR}


def _xl_font(bold=False, color=XL_TEXT, size=10):
    return Font(name="Arial", bold=bold, color=color, size=size)

def _xl_fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def _xl_border():
    s = Side(style="thin", color="cbd5e1")
    return Border(left=s, right=s, top=s, bottom=s)

def _xl_bottom_border():
    b = Side(style="medium", color="2563eb")
    t = Side(style="thin",   color="cbd5e1")
    return Border(left=t, right=t, top=t, bottom=b)

def _xl_center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)

def _xl_left():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)


def _xl_autosize(ws, min_width=8, max_width=60):
    """Fit each column to its longest content."""
    for col_cells in ws.columns:
        max_len    = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                if cell.value:
                    factor  = 1.2 if (cell.font and cell.font.bold) else 1.0
                    max_len = max(max_len, int(len(str(cell.value)) * factor))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 2, max_width))


def _xl_write_header_block(ws, session, summary, num_cols: int,
                           any_late_enabled: bool = True, academic_period="—") -> int:
    """Write title + summary rows. Returns the next free row number."""
    last_col = get_column_letter(num_cols)

    # Row 1 — Title
    ws.merge_cells(f"A1:{last_col}1")
    c = ws["A1"]
    c.value     = "ATTENDANCE REPORT"
    c.font      = _xl_font(bold=True, size=14, color=XL_ACCENT)
    c.fill      = _xl_fill(XL_HEADER_BG)
    c.alignment = _xl_center()
    ws.row_dimensions[1].height = 28

    # Row 2 — Session / date subtitle
    ws.merge_cells(f"A2:{last_col}2")
    c = ws["A2"]
    c.value = f"Session: {session.name}  |  Date: {session.date}  |  {academic_period}" 
    c.font      = _xl_font(size=10, color=XL_MUTED)
    c.fill      = _xl_fill(XL_HEADER_BG)
    c.alignment = _xl_center()
    ws.row_dimensions[2].height = 18

    # Row 3 — Spacer
    ws.merge_cells(f"A3:{last_col}3")
    ws["A3"].fill = _xl_fill(XL_HEADER_BG)
    ws.row_dimensions[3].height = 6

    # Row 4 — Stat cells (Late hidden when any_late_enabled is False)
    stats = [
        (f"Present: {summary['present']}", XL_SUCCESS),
    ]
    if any_late_enabled:
        stats.append((f"Late: {summary['late']}", XL_WARNING))
    stats.append((f"Absent: {summary['absent']}", XL_ERROR))

    n_stats = len(stats)
    chunk   = max(1, num_cols // n_stats)
    for i, (text, color) in enumerate(stats):
        start = i * chunk + 1
        end   = (i + 1) * chunk if i < n_stats - 1 else num_cols
        sc    = get_column_letter(start)
        ec    = get_column_letter(end)
        if sc != ec:
            ws.merge_cells(f"{sc}4:{ec}4")
        c           = ws[f"{sc}4"]
        c.value     = text
        c.font      = _xl_font(bold=True, size=11, color=color)
        c.fill      = _xl_fill(XL_HEADER_BG)
        c.alignment = _xl_center()
    ws.row_dimensions[4].height = 22

    # Row 5 — Expected / Rate
    half = max(1, num_cols // 2)
    sc1  = get_column_letter(1)
    ec1  = get_column_letter(half)
    sc2  = get_column_letter(half + 1)
    ec2  = get_column_letter(num_cols)
    if sc1 != ec1:
        ws.merge_cells(f"{sc1}5:{ec1}5")
    if sc2 != ec2:
        ws.merge_cells(f"{sc2}5:{ec2}5")

    est  = summary.get("estimated")
    rate = summary.get("rate")

    c           = ws[f"{sc1}5"]
    c.value     = f"Expected: {est if est else '—'}"
    c.font      = _xl_font(size=10, color=XL_MUTED)
    c.fill      = _xl_fill(XL_HEADER_BG)
    c.alignment = _xl_center()

    rate_color  = (XL_SUCCESS if rate and rate >= 75
                   else XL_WARNING if rate and rate >= 50
                   else XL_ERROR if rate else XL_MUTED)
    c           = ws[f"{sc2}5"]
    c.value     = f"Attendance rate: {rate}%" if rate else "Attendance rate: —"
    c.font      = _xl_font(bold=True, size=10, color=rate_color)
    c.fill      = _xl_fill(XL_HEADER_BG)
    c.alignment = _xl_center()
    ws.row_dimensions[5].height = 18

    # Row 6 — Spacer
    ws.merge_cells(f"A6:{last_col}6")
    ws.row_dimensions[6].height = 8

    return 7


def _xl_write_period_section(ws, period_obj, period_rows, start_row: int) -> int:
    """
    Write one period block: heading + column headers + data rows.
    Returns the next free row after a trailing spacer.

    Column rules:
      - Time Out column only shown when period_obj.timeout_enabled is True
      - If period_obj.late_enabled is False, late rows are filtered out
        and the Status column will only contain Present / Absent values
    """
    show_timeout = bool(period_obj and period_obj.timeout_enabled)
    late_enabled = period_obj.late_enabled if period_obj else True

    if not late_enabled:
        period_rows = [r for r in period_rows if r["status"] != "late"]

    headers = ["#", "Student ID", "Name", "Department", "Program", "Code", "Year Level", "Status", "Time In"]
    if show_timeout:
        headers.append("Time Out")

    num_cols   = len(headers)
    last_col_l = get_column_letter(num_cols)
    period_name = period_obj.name if period_obj else "Unknown Period"

    # Period heading row
    ws.merge_cells(f"A{start_row}:{last_col_l}{start_row}")
    c           = ws[f"A{start_row}"]
    c.value     = f"{period_name.upper()}  —  {len(period_rows)} student(s)"
    c.font      = _xl_font(bold=True, size=10, color=XL_ACCENT)
    c.fill      = _xl_fill(XL_SECTION_BG)
    c.alignment = _xl_left()
    c.border    = _xl_bottom_border()
    ws.row_dimensions[start_row].height = 20
    current_row = start_row + 1

    # Column headers
    for col, h in enumerate(headers, 1):
        cell           = ws.cell(row=current_row, column=col, value=h)
        cell.font      = _xl_font(bold=True, color=XL_HEADER_FG)
        cell.fill      = _xl_fill(XL_ACCENT)
        cell.alignment = _xl_center()
        cell.border    = _xl_border()
    ws.row_dimensions[current_row].height = 18
    current_row += 1

    # Data rows
    for i, row in enumerate(period_rows, 1):
        bg = XL_ROW_ALT if i % 2 == 0 else XL_ROW_NORMAL
        sc = _XL_STATUS_COLORS.get(row["status"], XL_MUTED)

        values = [i, row["student_id"], row["name"], row["dept_code"], row["program"], row["code"], row["yearlevel"], row["status"].upper(), row["time_in"]]
        if show_timeout:
            values.append(row["time_out"])

        for col, val in enumerate(values, 1):
            is_status      = (col == 8)
            is_name        = (col == 3)
            cell           = ws.cell(row=current_row, column=col, value=val)
            cell.fill      = _xl_fill(bg)
            cell.border    = _xl_border()
            cell.alignment = _xl_left() if is_name else _xl_center()
            cell.font      = _xl_font(
                bold=is_status,
                color=sc if is_status else XL_TEXT,
            )
        ws.row_dimensions[current_row].height = 16
        current_row += 1

    # Trailing spacer between periods
    ws.row_dimensions[current_row].height = 10
    current_row += 1

    return current_row


def export_session_xlsx(data: dict, filepath: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Session Attendance"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = XL_ACCENT

    session    = data["session"]
    rows       = data["rows"]
    summary    = data["summary"]
    period_map = data.get("period_map", {})
    periods    = data.get("periods", [])

    # Group rows by period in sort order
    grouped: dict = OrderedDict()
    for p in periods:
        grouped[p.id] = []
    for row in rows:
        pid = row.get("period_id")
        if pid in grouped:
            grouped[pid].append(row)
        else:
            grouped.setdefault(None, []).append(row)

    # Max columns = 9 (base 8 + possible Time Out)
    # We use 9 so header block merges span correctly even if some
    # periods don't have timeout
    num_cols    = 10
    any_late    = data.get("any_late_enabled", True)
    current_row = _xl_write_header_block(ws, session, summary, num_cols,
                                     any_late_enabled=any_late,
                                     academic_period=data.get("academic_period", "—"))

    for period_id, period_rows in grouped.items():
        if not period_rows:
            continue
        period_obj  = period_map.get(period_id)
        current_row = _xl_write_period_section(
            ws, period_obj, period_rows, current_row)

    ws.freeze_panes = "A7"  # freeze title+summary block
    _xl_autosize(ws)
    wb.save(filepath)


# ---------------------------------------------------------------------------
# PDF exporter — report style
# ---------------------------------------------------------------------------

_PDF_BG      = colors.HexColor("#ffffff")
_PDF_SURFACE = colors.HexColor("#f1f5f9")
_PDF_ACCENT  = colors.HexColor("#2563eb")
_PDF_SUCCESS = colors.HexColor("#16a34a")
_PDF_WARNING = colors.HexColor("#d97706")
_PDF_ERROR   = colors.HexColor("#dc2626")
_PDF_TEXT    = colors.HexColor("#1e293b")
_PDF_MUTED   = colors.HexColor("#64748b")
_PDF_BORDER  = colors.HexColor("#cbd5e1")

_STATUS_PDF   = {"present": _PDF_SUCCESS, "late": _PDF_WARNING, "absent": _PDF_ERROR}
_STATUS_LABEL = {"present": "PRESENT",    "late": "LATE",       "absent": "ABSENT"}


def _pdf_styles() -> dict:
    return {
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold", fontSize=20,
            textColor=_PDF_TEXT,
            alignment=TA_CENTER, spaceAfter=2, leading=24),

        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Helvetica", fontSize=10,
            textColor=_PDF_MUTED,
            alignment=TA_CENTER, spaceAfter=0, leading=14),

        "meta_value": ParagraphStyle(
            "meta_value",
            fontName="Helvetica-Bold", fontSize=9,
            textColor=_PDF_TEXT,
            alignment=TA_LEFT, leading=12),

        "stat_number": ParagraphStyle(
            "stat_number",
            fontName="Helvetica-Bold", fontSize=22,
            textColor=_PDF_TEXT,
            alignment=TA_CENTER, leading=26),

        "stat_label": ParagraphStyle(
            "stat_label",
            fontName="Helvetica", fontSize=8,
            textColor=_PDF_MUTED,
            alignment=TA_CENTER, leading=10),

        "section": ParagraphStyle(
            "section",
            fontName="Helvetica-Bold", fontSize=9,
            textColor=_PDF_MUTED,
            alignment=TA_LEFT, spaceBefore=10, spaceAfter=3,
            leading=11),

        "row_name": ParagraphStyle(
            "row_name",
            fontName="Helvetica-Bold", fontSize=8,
            textColor=_PDF_TEXT,
            alignment=TA_LEFT, leading=10),

        "row_detail": ParagraphStyle(
            "row_detail",
            fontName="Helvetica", fontSize=7,
            textColor=_PDF_MUTED,
            alignment=TA_LEFT, leading=9),

        "row_center": ParagraphStyle(
            "row_center",
            fontName="Helvetica", fontSize=8,
            textColor=_PDF_TEXT,
            alignment=TA_CENTER, leading=10),

        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica", fontSize=7,
            textColor=_PDF_MUTED,
            alignment=TA_CENTER, leading=10),
    }


def _draw_page(canv: rl_canvas.Canvas, doc, session_name: str,
               total_pages_ref: list):
    w, h = A4
    canv.saveState()

    canv.setFillColor(colors.white)
    canv.rect(0, 0, w, h, fill=1, stroke=0)

    canv.setFillColor(_PDF_ACCENT)
    canv.rect(0, h - 6, w, 6, fill=1, stroke=0)

    footer_h = 10 * mm
    canv.setFillColor(_PDF_SURFACE)
    canv.rect(0, 0, w, footer_h, fill=1, stroke=0)

    canv.setStrokeColor(_PDF_BORDER)
    canv.setLineWidth(0.5)
    canv.line(0, footer_h, w, footer_h)

    canv.setFillColor(_PDF_MUTED)
    canv.setFont("Helvetica", 7)
    canv.drawString(15 * mm, 3.5 * mm,
                    f"RFID Attendance Tracker  •  {session_name}")
    canv.drawRightString(w - 15 * mm, 3.5 * mm,
                         f"Page {canv._pageNumber}")

    canv.restoreState()


def _stat_block(number: str, label: str, accent: colors.Color, s: dict) -> Table:
    cell = Table(
        [[Paragraph(number, s["stat_number"])],
         [Paragraph(label,  s["stat_label"])]],
        colWidths=[38 * mm],
    )
    cell.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_BG),
        ("LINECOLOR",     (0, 0), (-1, -1), _PDF_BORDER),
        ("BOX",           (0, 0), (-1, -1), 0.4, _PDF_BORDER),
        ("LINEBEFORE",    (0, 0), (0,  -1), 3,   accent),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return cell


def export_session_pdf(data: dict, filepath: str):
    session    = data["session"]
    rows       = data["rows"]
    summary    = data["summary"]
    period_map = data.get("period_map", {})
    periods    = data.get("periods", [])
    s          = _pdf_styles()

    w, h = A4
    lm = rm = 15 * mm
    tm = 22 * mm
    bm = 16 * mm

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=lm, rightMargin=rm,
        topMargin=tm, bottomMargin=bm,
    )

    session_name = session.name

    def make_page(canv, doc):
        _draw_page(canv, doc, session_name, [])

    story = []

    # Title
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("ATTENDANCE REPORT", s["title"]))
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(
        f"{session.date.strftime('%B %d, %Y')}  •  {session.name}  •  {data.get('academic_period', '')}",
        s["subtitle"]))
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(
        width="100%", color=_PDF_BORDER, thickness=0.5, spaceAfter=6))

    any_late   = data.get("any_late_enabled", True)

    # Stat cards — Late card hidden when no period tracks lateness
    stat_items = [
        _stat_block(str(summary["present"]), "PRESENT", _PDF_SUCCESS, s),
    ]
    if any_late:
        stat_items.append(_stat_block(str(summary["late"]), "LATE", _PDF_WARNING, s))
    stat_items.append(_stat_block(str(summary["absent"]), "ABSENT", _PDF_ERROR,  s))

    n_slots = 3  # always 3 slots: present, late (or empty), absent
    gap     = 3 * mm
    card_w  = (w - lm - rm - (n_slots - 1) * gap) / n_slots

    # pad stat_items to always fill 3 slots with empty spacers
    while len(stat_items) < n_slots:
        empty = Table([[Paragraph("", s["stat_label"])]], colWidths=[card_w])
        empty.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), _PDF_BG)]))
        stat_items.insert(-1, empty)  # insert before absent

    stats_row = Table([stat_items], colWidths=[card_w] * n_slots, hAlign="LEFT")
    stats_row.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), gap / 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap / 2),
        ("LEFTPADDING",  (0, 0), (0,  -1), 0),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
    ]))
    story.append(stats_row)

    # Estimated / rate
    est  = summary.get("estimated")
    rate = summary.get("rate")
    if est:
        story.append(Spacer(1, 3 * mm))
        rate_color = (_PDF_SUCCESS if rate and rate >= 75
                      else _PDF_WARNING if rate and rate >= 50
                      else _PDF_ERROR)
        rate_str = (f'<font color="#{rate_color.hexval()[2:]}">'
                    f'Attendance rate: <b>{rate}%</b></font>'
                    if rate else "Attendance rate: —")
        meta_line = Table(
            [[Paragraph(f"Expected attendees: <b>{est}</b>", s["meta_value"]),
              Paragraph(rate_str, ParagraphStyle(
                  "rate_inline",
                  fontName="Helvetica", fontSize=9,
                  textColor=_PDF_MUTED,
                  alignment=TA_RIGHT, leading=12))]],
            colWidths=[(w - lm - rm) * 0.5] * 2,
        )
        meta_line.setStyle(TableStyle([
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(meta_line)

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(
        width="100%", color=_PDF_BORDER, thickness=0.5, spaceAfter=4))

    dept_summary: dict = {}
    for row in rows:
        dept = row.get("dept_code", "—")
        prog = row.get("code", "—")
        dept_summary.setdefault(dept, {}).setdefault(prog, {"present": 0, "late": 0})
        if row["status"] in ("present", "late"):
            dept_summary[dept][prog]["present"] += 1
        if row["status"] == "late":
            dept_summary[dept][prog]["late"] += 1 # late attendees are also counted as present for summary purposes

    story.append(Paragraph("ATTENDANCE BY DEPARTMENT", s["section"]))

    for dept in sorted(dept_summary):
        story.append(Paragraph(
            f'<b>{dept}</b>',
            ParagraphStyle("dept_hdr", fontName="Helvetica-Bold", fontSize=9,
                        textColor=_PDF_ACCENT, leading=14, spaceBefore=6)))
        for prog in sorted(dept_summary[dept]):
            p_stats = dept_summary[dept][prog]
            if any_late and p_stats["late"] > 0:
                detail = (
                    f'<font color="#16a34a">{p_stats["present"]} present</font>,  '
                    f'<font color="#d97706">{p_stats["late"]} late</font>'
                )
            else:
                detail = f'<font color="#16a34a">{p_stats["present"]} present</font>'
            story.append(Paragraph(
                f'&nbsp;&nbsp;&nbsp;&nbsp;{prog}  —  {detail}',
                ParagraphStyle("prog_row", fontName="Helvetica", fontSize=8,
                            textColor=_PDF_TEXT, leading=12)))

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", color=_PDF_BORDER, thickness=0.5, spaceAfter=4))

    # Group rows by period in sort order
    grouped: dict = OrderedDict()
    for p in periods:
        grouped[p.id] = []
    for row in rows:
        pid = row.get("period_id")
        if pid in grouped:
            grouped[pid].append(row)
        else:
            grouped.setdefault(None, []).append(row)

    usable_w = w - lm - rm

    for period_id, period_rows in grouped.items():
        if not period_rows:
            continue

        period_obj   = period_map.get(period_id)
        show_timeout = bool(period_obj and period_obj.timeout_enabled)
        late_enabled = period_obj.late_enabled if period_obj else True
        period_name  = period_obj.name         if period_obj else "—"

        if not late_enabled:
            period_rows = [r for r in period_rows if r["status"] != "late"]

        # Column widths — name column fills remaining space
        base_cols = [8*mm, 22*mm, 0, 22*mm, 18*mm, 20*mm]
        if show_timeout:
            base_cols.append(20*mm)
        base_cols[2] = usable_w - sum(base_cols)

        labels = ["#", "Student ID", "Name / Program", "Year", "Status", "Time In"]
        if show_timeout:
            labels.append("Time Out")

        def _hrow(labels=labels):
            return [Paragraph(f'<font color="#64748b">{l}</font>', s["row_center"])
                    for l in labels]

        story.append(Paragraph(
            f"— {period_name.upper()}  ({len(period_rows)} students)",
            s["section"]))

        table_data = [_hrow()]

        for i, row in enumerate(period_rows, 1):
            status_color = _STATUS_PDF.get(row["status"], _PDF_MUTED)
            hex_sc       = status_color.hexval()

            name_cell = Table(
                [[Paragraph(row["name"], s["row_name"])],
                 [Paragraph(f'{row["dept_code"]}  •  {row["program"]}  •  {row["code"]}', s["row_detail"])]],
                colWidths=[base_cols[2] - 4],
            )
            name_cell.setStyle(TableStyle([
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))

            status_pill = Table(
                [[Paragraph(
                    f'<font color="#{hex_sc}"><b>'
                    f'{_STATUS_LABEL.get(row["status"], row["status"].upper())}'
                    f'</b></font>',
                    s["row_center"])]],
                colWidths=[base_cols[4] - 4],
            )
            status_pill.setStyle(TableStyle([
                ("BACKGROUND",     (0, 0), (-1, -1), _PDF_BG),
                ("LINECOLOR",      (0, 0), (-1, -1), status_color),
                ("BOX",            (0, 0), (-1, -1), 0.6, status_color),
                ("ROUNDEDCORNERS", [2]),
                ("TOPPADDING",     (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 2),
                ("LEFTPADDING",    (0, 0), (-1, -1), 3),
                ("RIGHTPADDING",   (0, 0), (-1, -1), 3),
            ]))

            data_row = [
                Paragraph(str(i),                 s["row_center"]),
                Paragraph(str(row["student_id"]), s["row_center"]),
                name_cell,
                Paragraph(row["yearlevel"],        s["row_center"]),
                status_pill,
                Paragraph(row["time_in"],          s["row_center"]),
            ]
            if show_timeout:
                data_row.append(Paragraph(row["time_out"], s["row_center"]))

            table_data.append(data_row)

        t = Table(table_data, colWidths=base_cols, repeatRows=1, hAlign="LEFT")

        row_styles = [
            ("BACKGROUND",    (0, 0), (-1, 0), _PDF_SURFACE),
            ("LINEBELOW",     (0, 0), (-1, 0), 0.8, _PDF_ACCENT),
            ("TOPPADDING",    (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW",     (0, 1), (-1, -1), 0.3, _PDF_BORDER),
        ]
        for i in range(1, len(table_data)):
            bg = _PDF_SURFACE if i % 2 == 0 else _PDF_BG
            row_styles.append(("BACKGROUND",    (0, i), (-1, i), bg))
            row_styles.append(("TOPPADDING",    (0, i), (-1, i), 5))
            row_styles.append(("BOTTOMPADDING", (0, i), (-1, i), 5))

        t.setStyle(TableStyle(row_styles))
        story.append(KeepTogether([t]))
        story.append(Spacer(1, 4 * mm))

    # Footer
    story.append(HRFlowable(
        width="100%", color=_PDF_BORDER, thickness=0.5, spaceBefore=4))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        s["footer"]))

    doc.build(story, onFirstPage=make_page, onLaterPages=make_page)