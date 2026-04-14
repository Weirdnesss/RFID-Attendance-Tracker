"""
period_row.py
-------------
Drop-in replacement for the PeriodRow class in scan_screen.py.

Fields per period:
    name, time_in_start, time_in_end,
    late_enabled, late_start,
    absent_enabled, absent_start,
    grace_minutes,
    timeout_enabled, timeout_start, timeout_end
"""

import tkinter as tk
import customtkinter as ctk
from datetime import datetime, time as dtime

from ui.theme import C_BG, C_BORDER, C_ACCENT, C_MUTED, C_SURFACE, C_TEXT, C_WARNING, PERIOD_COLORS
from ui.components.clock_picker import TimeEntry

def _section_label(parent, text: str):
    """Small all-caps muted section divider."""
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=9, weight="bold"),
        text_color=C_MUTED
    ).pack(anchor="w", padx=12, pady=(10, 2))

def _divider(parent):
    ctk.CTkFrame(parent, fg_color=C_BORDER, height=1).pack(
        fill="x", padx=12, pady=(2, 0))

class _TimeRow(ctk.CTkFrame):
    """
    A toggle + one or two TimeEntry fields in a single row.

        [● toggle label]   [label]  [TimeEntry]   [label]  [TimeEntry]
    """

    def __init__(self, parent, toggle_text: str,
                 fields: list[tuple[str, str, str]],   # (label, default, attr)
                 default_enabled: bool = False,
                 accent: str = C_ACCENT):
        super().__init__(parent, fg_color="transparent")

        self._enabled_var = tk.BooleanVar(value=default_enabled)
        self._field_widgets: dict[str, tk.StringVar] = {}

        # Toggle
        self._toggle = ctk.CTkCheckBox(
            self,
            text=toggle_text,
            variable=self._enabled_var,
            font=ctk.CTkFont(size=11),
            text_color=C_TEXT,
            fg_color=accent,
            hover_color=accent,
            checkmark_color="#ffffff",
            border_color=C_BORDER,
            width=16, height=16,
            command=self._on_toggle,
        )
        self._toggle.pack(side="left", padx=(0, 12))

        # Time fields (hidden when disabled)
        self._field_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._field_frame.pack(side="left", fill="x", expand=True)

        for label_text, default_val, attr_name in fields:
            col = ctk.CTkFrame(self._field_frame, fg_color="transparent")
            col.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(
                col, text=label_text,
                font=ctk.CTkFont(size=9),
                text_color=C_MUTED
            ).pack(anchor="w")

            var = tk.StringVar(value=default_val)
            self._field_widgets[attr_name] = var

            TimeEntry(
                col, textvariable=var, label=label_text,
                fg_color=C_SURFACE, border_color=C_BORDER,
                text_color=C_TEXT, height=26,
                font=ctk.CTkFont(size=11),
                width=90,
            ).pack()

        self._on_toggle()   # set initial visibility

    def _on_toggle(self):
        state = "normal" if self._enabled_var.get() else "disabled"
        # Visually dim field frame when disabled
        alpha = C_TEXT if self._enabled_var.get() else C_MUTED
        for w in self._field_frame.winfo_children():
            try:
                w.configure(fg_color="transparent")
            except Exception:
                pass
        # We don't disable TimeEntry (still readable) — just mute labels
        for child in self._field_frame.winfo_children():
            for sub in child.winfo_children():
                try:
                    if isinstance(sub, ctk.CTkLabel):
                        sub.configure(text_color=alpha)
                except Exception:
                    pass

    @property
    def enabled(self) -> bool:
        return self._enabled_var.get()

    def get_time(self, attr_name: str) -> str:
        return self._field_widgets[attr_name].get()

class PeriodRow(ctk.CTkFrame):
    """One period card inside the New Session dialog."""

    def __init__(self, parent, index: int, on_delete, defaults: dict = None):
        super().__init__(
            parent,
            fg_color=C_BG,
            corner_radius=10,
            border_width=1,
            border_color=C_BORDER,
        )
        self._on_delete = on_delete
        self._index     = index
        d = defaults or {}
        color = PERIOD_COLORS[index % len(PERIOD_COLORS)]

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=38)
        hdr.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkFrame(hdr, width=8, height=8,
                     fg_color=color, corner_radius=4).pack(
            side="left", padx=(0, 8))

        self._name_var = tk.StringVar(value=d.get("name", f"Attendance Period {index + 1}"))
        ctk.CTkEntry(
            hdr, textvariable=self._name_var,
            fg_color=C_BORDER, border_width=0,
            text_color=C_TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
            width=200,
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text="✕", width=28, height=28,
            fg_color="transparent", text_color=C_MUTED,
            hover_color="#2a1a1a",
            font=ctk.CTkFont(size=12),
            command=lambda: on_delete(self),
        ).pack(side="right")

        # ── Attendance window ─────────────────────────────────────────────────
        _section_label(self, "ATTENDANCE WINDOW")
        win_row = ctk.CTkFrame(self, fg_color="transparent")
        win_row.pack(fill="x", padx=12, pady=(0, 4))

        def _time_col(parent, label, default):
            col = ctk.CTkFrame(parent, fg_color="transparent")
            col.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(col, text=label,
                         font=ctk.CTkFont(size=9),
                         text_color=C_MUTED).pack(anchor="w")
            var = tk.StringVar(value=default)
            TimeEntry(col, textvariable=var, label=label,
                      fg_color=C_SURFACE, border_color=C_BORDER,
                      text_color=C_TEXT, height=26,
                      font=ctk.CTkFont(size=11),
                      width=90).pack()
            return var

        self._time_in_start = _time_col(win_row, "TIME IN START",
                                         d.get("time_in_start", "07:00"))
        self._time_in_end   = _time_col(win_row, "TIME IN END",
                                         d.get("time_in_end",   "09:00"))

        _divider(self)

        # ── Late ──────────────────────────────────────────────────────────────
        _section_label(self, "LATE")
        self._late_row = _TimeRow(
            self,
            toggle_text="Enable late marking",
            fields=[("LATE AFTER", d.get("late_start", "07:30"), "late_start")],
            default_enabled=d.get("late_enabled", False),
            accent=C_WARNING,
            
        )
        self._late_row.pack(anchor="w", padx=12, pady=(0, 6))

        late_inner = ctk.CTkFrame(self._late_row, fg_color="transparent")
        late_inner.pack(anchor="w")
        
        grace_col = ctk.CTkFrame(late_inner, fg_color="transparent")
        grace_col.pack(side="left")

        ctk.CTkLabel(
            grace_col, text="GRACE (mins)",
            font=ctk.CTkFont(size=9),
            text_color=C_MUTED
        ).pack(anchor="w")

        self._grace_var = tk.StringVar(value=str(d.get("grace_minutes", "0")))

        ctk.CTkEntry(
            grace_col,
            textvariable=self._grace_var,
            fg_color=C_SURFACE,
            border_color=C_BORDER,
            text_color=C_TEXT,
            height=26,
            font=ctk.CTkFont(size=11),
            width=70,
        ).pack()

        _divider(self)

        # ── Timeout ───────────────────────────────────────────────────────────
        _section_label(self, "TIME OUT")
        self._timeout_row = _TimeRow(
            self,
            toggle_text="Track time-out",
            fields=[
                ("TIMEOUT START", d.get("timeout_start", "11:00"), "timeout_start"),
                ("TIMEOUT END",   d.get("timeout_end",   "12:00"), "timeout_end"),
            ],
            default_enabled=d.get("timeout_enabled", False),
            accent=C_ACCENT,
        )
        self._timeout_row.pack(fill="x", padx=12, pady=(0, 12))

    # ── parsing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_time(value: str, field_name: str) -> dtime:
        for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
            try:
                return datetime.strptime(value.strip(), fmt).time()
            except ValueError:
                continue
        raise ValueError(f"Invalid time in '{field_name}': '{value}'")

    def get_data(self) -> dict:
        """Return validated period dict. Raises ValueError on bad input."""
        pt = self._parse_time   # shorthand
        data = {
            "name":           self._name_var.get().strip() or f"Attendance Period {self._index + 1}",
            "time_in_start":  pt(self._time_in_start.get(), "Time In Start"),
            "time_in_end":    pt(self._time_in_end.get(),   "Time In End"),
            "grace_minutes":  int(self._grace_var.get().strip() or "0"),

            "late_enabled":   self._late_row.enabled,
            "late_start":     pt(self._late_row.get_time("late_start"), "Late After") if self._late_row.enabled else None,

            "timeout_enabled": self._timeout_row.enabled,
            "timeout_start":   pt(self._timeout_row.get_time("timeout_start"), "Timeout Start") if self._timeout_row.enabled else None,
            "timeout_end":     pt(self._timeout_row.get_time("timeout_end"), "Timeout End") if self._timeout_row.enabled else None,
        }
        return data