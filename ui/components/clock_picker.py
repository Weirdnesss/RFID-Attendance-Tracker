"""
clock_picker.py — Clock-style time picker for customtkinter.

Drop this file into your project and import ClockPickerDialog.
Then replace plain CTkEntry time fields with TimeEntry (a CTkEntry
subclass that opens the clock on click).
"""

import math
import tkinter as tk
import customtkinter as ctk

_HAND      = "#7c9ef8"   # C_ACCENT
_SEL_BG    = "#1e2a4a"   # dark teal circle behind selected value
_SEL_FG    = "#7c9ef8"
_FACE_OUT  = "#2a2d3a"   # C_BORDER
_TICK_COL  = "#3a3d4a"
_LBL_COL   = "#6b7280"   # C_MUTED
_TEXT_PRI  = "#e2e8f0"   # C_TEXT
_DARK_BG   = "#0f1117"   # card bg (same as PeriodRow)
_SURF      = "#161b27"   # C_SURFACE


class ClockPickerDialog(ctk.CTkToplevel):
    """
    Modal clock-style time picker.

    Usage:
        dlg = ClockPickerDialog(parent, initial="07:30")
        parent.wait_window(dlg)
        if dlg.result:          # "HH:MM"  (24-hour string)
            print(dlg.result)
    """

    SIZE   = 260
    CENTER = 130
    RADIUS = 106
    LBL_R  = 84

    def __init__(self, parent, initial: str = "07:00", title: str = "Pick a time"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=_DARK_BG)
        self.grab_set()
        self.result: str | None = None

        # Parse initial value
        try:
            parts = initial.strip().split(":")
            h24, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            h24, m = 7, 0

        self._hour24  = h24 % 24
        self._minute  = m % 60
        self._is_am   = self._hour24 < 12
        # 12-hour display value
        self._hour12  = self._hour24 % 12 or 12
        self._mode    = "hour"   # "hour" | "minute"

        self._build_ui()
        self._refresh()
        self._center_on(parent)

    # ------------------------------------------------------------------ layout

    def _build_ui(self):
        pad = {"padx": 20}

        # Time display
        self._display_var = tk.StringVar()
        ctk.CTkLabel(
            self, textvariable=self._display_var,
            font=ctk.CTkFont(family="Courier New", size=38, weight="bold"),
            text_color=_TEXT_PRI
        ).pack(pady=(20, 0), **pad)

        # AM / PM row
        ampm = ctk.CTkFrame(self, fg_color="transparent")
        ampm.pack(pady=(6, 0))
        self._am_btn = self._pill(ampm, "AM", lambda: self._set_ampm(True))
        self._am_btn.pack(side="left", padx=4)
        self._pm_btn = self._pill(ampm, "PM", lambda: self._set_ampm(False))
        self._pm_btn.pack(side="left", padx=4)

        # Hour / Minute mode
        mode_row = ctk.CTkFrame(self, fg_color="transparent")
        mode_row.pack(pady=(8, 0))
        self._hr_btn  = self._pill(mode_row, "Hour",   lambda: self._set_mode("hour"))
        self._hr_btn.pack(side="left", padx=4)
        self._min_btn = self._pill(mode_row, "Minute", lambda: self._set_mode("minute"))
        self._min_btn.pack(side="left", padx=4)

        # Clock canvas
        self._canvas = tk.Canvas(
            self,
            width=self.SIZE, height=self.SIZE,
            bg=_DARK_BG, highlightthickness=0
        )
        self._canvas.pack(pady=(10, 4), **pad)
        self._canvas.bind("<Button-1>",        self._on_click)
        self._canvas.bind("<B1-Motion>",        self._on_drag)

        # Separator
        ctk.CTkFrame(self, fg_color=_FACE_OUT, height=1).pack(fill="x")

        # Footer
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=10)

        ctk.CTkButton(
            foot, text="Cancel",
            fg_color="transparent",
            border_color=_FACE_OUT, border_width=1,
            text_color=_LBL_COL, hover_color=_SURF,
            width=80, height=32,
            command=self.destroy
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            foot, text="Set time",
            fg_color=_HAND, hover_color="#8aabff",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=90, height=32,
            command=self._confirm
        ).pack(side="right")

    def _pill(self, parent, text, cmd):
        return ctk.CTkButton(
            parent, text=text, width=64, height=26,
            fg_color="transparent",
            border_color=_FACE_OUT, border_width=1,
            text_color=_LBL_COL, hover_color=_SURF,
            font=ctk.CTkFont(size=11),
            command=cmd
        )

    # ------------------------------------------------------------------ state

    def _set_ampm(self, am: bool):
        self._is_am = am
        # Recompute hour24
        self._hour24 = (self._hour12 % 12) + (0 if am else 12)
        self._refresh()

    def _set_mode(self, mode: str):
        self._mode = mode
        self._refresh()

    def _refresh(self):
        h = str(self._hour12).zfill(2)
        m = str(self._minute).zfill(2)
        self._display_var.set(f"{h}:{m}")
        self._style_pills()
        self._draw_clock()

    def _style_pills(self):
        active   = {"fg_color": _SEL_BG,   "text_color": _SEL_FG,   "border_color": _SEL_FG}
        inactive = {"fg_color": "transparent", "text_color": _LBL_COL, "border_color": _FACE_OUT}

        for btn, is_active in [
            (self._am_btn,  self._is_am),
            (self._pm_btn,  not self._is_am),
            (self._hr_btn,  self._mode == "hour"),
            (self._min_btn, self._mode == "minute"),
        ]:
            btn.configure(**(active if is_active else inactive))

    # ------------------------------------------------------------------ drawing

    def _draw_clock(self):
        cv = self._canvas
        cv.delete("all")
        cx = cy = self.CENTER
        R  = self.RADIUS

        # Face
        cv.create_oval(cx-R, cy-R, cx+R, cy+R,
                       outline=_FACE_OUT, width=1, fill=_DARK_BG)

        if self._mode == "hour":
            self._draw_hours(cx, cy)
        else:
            self._draw_minutes(cx, cy)

        # Hand
        a  = self._hand_angle()
        lr = self.LBL_R
        hx = cx + math.cos(a) * lr
        hy = cy + math.sin(a) * lr
        cv.create_line(cx, cy, hx, hy,
                       fill=_HAND, width=2, capstyle="round")
        cv.create_oval(cx-4, cy-4, cx+4, cy+4,
                       fill=_HAND, outline="")

    def _draw_hours(self, cx, cy):
        for h in range(1, 13):
            a  = (h / 12) * 2 * math.pi - math.pi / 2
            x  = cx + math.cos(a) * self.LBL_R
            y  = cy + math.sin(a) * self.LBL_R
            sel = (h == self._hour12)
            if sel:
                r = 15
                self._canvas.create_oval(x-r, y-r, x+r, y+r,
                                         fill=_SEL_BG, outline="")
            self._canvas.create_text(
                x, y, text=str(h),
                font=("Helvetica", 13, "bold" if sel else "normal"),
                fill=_SEL_FG if sel else _LBL_COL
            )

    def _draw_minutes(self, cx, cy):
        # Fine tick marks
        for t in range(60):
            if t % 5 == 0:
                continue
            a  = (t / 60) * 2 * math.pi - math.pi / 2
            tx = cx + math.cos(a) * self.LBL_R
            ty = cy + math.sin(a) * self.LBL_R
            self._canvas.create_oval(tx-1.5, ty-1.5, tx+1.5, ty+1.5,
                                     fill=_TICK_COL, outline="")
        # 5-minute labels
        for step in range(0, 60, 5):
            a   = (step / 60) * 2 * math.pi - math.pi / 2
            x   = cx + math.cos(a) * self.LBL_R
            y   = cy + math.sin(a) * self.LBL_R
            sel = (step == self._minute)
            if sel:
                r = 15
                self._canvas.create_oval(x-r, y-r, x+r, y+r,
                                         fill=_SEL_BG, outline="")
            self._canvas.create_text(
                x, y, text=str(step).zfill(2),
                font=("Helvetica", 12, "bold" if sel else "normal"),
                fill=_SEL_FG if sel else _LBL_COL
            )

    def _hand_angle(self) -> float:
        if self._mode == "hour":
            return ((self._hour12 % 12) / 12) * 2 * math.pi - math.pi / 2
        return (self._minute / 60) * 2 * math.pi - math.pi / 2

    # ------------------------------------------------------------------ events

    def _angle_from_event(self, event) -> float:
        cx = cy = self.CENTER
        a = math.degrees(math.atan2(event.y - cy, event.x - cx)) + 90
        return a % 360

    def _on_click(self, event):
        angle = self._angle_from_event(event)
        if self._mode == "hour":
            raw = round(angle / 30) % 12
            self._hour12  = raw or 12
            self._hour24  = (self._hour12 % 12) + (0 if self._is_am else 12)
            self._set_mode("minute")   # auto-advance
        else:
            self._minute = round(angle / 6) % 60
            self._refresh()

    def _on_drag(self, event):
        """Allow dragging the hand to scrub through values."""
        angle = self._angle_from_event(event)
        if self._mode == "hour":
            raw = round(angle / 30) % 12
            self._hour12 = raw or 12
            self._hour24 = (self._hour12 % 12) + (0 if self._is_am else 12)
        else:
            self._minute = round(angle / 6) % 60
        self._refresh()

    def _confirm(self):
        # Always return 24-hour "HH:MM" string — matches your _parse_time format
        self.result = f"{self._hour24:02d}:{self._minute:02d}"
        self.destroy()

    # ------------------------------------------------------------------ helpers

    def _center_on(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

class TimeEntry(ctk.CTkFrame):
    """
    A CTkEntry that opens a ClockPickerDialog when clicked.

    Matches the look of your existing CTkEntry time fields.
    Returns a 24-hour "HH:MM" string via .get() / .set() / textvariable.

    Replace:
        ctk.CTkEntry(parent, textvariable=self._window_start, ...)
    With:
        TimeEntry(parent, textvariable=self._window_start, ...)
    """

    def __init__(self, parent, textvariable: tk.StringVar = None,
                 label: str = "", **kwargs):
        # Strip kwargs that don't apply to CTkFrame
        height    = kwargs.pop("height", 28)
        fg_color  = kwargs.pop("fg_color",      _SURF)
        border_color = kwargs.pop("border_color", _FACE_OUT)
        text_color   = kwargs.pop("text_color",   _TEXT_PRI)
        font         = kwargs.pop("font", ctk.CTkFont(size=12))
        kwargs.pop("placeholder_text", None)

        super().__init__(
            parent,
            fg_color=fg_color,
            border_color=border_color,
            border_width=1,
            corner_radius=6,
            height=height,
            **kwargs
        )

        self._var   = textvariable or tk.StringVar(value="07:00")
        self._label = label

        # Inner entry (read-only display)
        self._entry = ctk.CTkEntry(
            self,
            textvariable=self._var,
            fg_color="transparent",
            border_width=0,
            text_color=text_color,
            font=font,
            height=height,
            state="normal"
        )
        self._entry.pack(side="left", fill="both", expand=True, padx=(8, 2))

        # Clock icon button
        self._icon_btn = ctk.CTkButton(
            self,
            text="◷",
            width=26, height=height,
            fg_color="transparent",
            text_color=_LBL_COL,
            hover_color=_SEL_BG,
            font=ctk.CTkFont(size=13),
            command=self._open_picker
        )
        self._icon_btn.pack(side="right", padx=(0, 4))

        # Clicking the entry text also opens the picker
        self._entry.bind("<Button-1>", lambda e: self._open_picker())

    def _open_picker(self):
        dlg = ClockPickerDialog(
            self.winfo_toplevel(),
            initial=self._var.get(),
            title=self._label or "Pick a time"
        )
        self.winfo_toplevel().wait_window(dlg)
        if dlg.result:
            self._var.set(dlg.result)

    # Convenience API mirrors StringVar
    def get(self) -> str:
        return self._var.get()

    def set(self, value: str):
        self._var.set(value)
        