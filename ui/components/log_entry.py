import customtkinter as ctk
from ui.theme import C_BG, C_BORDER, C_MUTED, C_SUCCESS, C_TEXT, C_WARNING, C_ERROR

_PURPLE = "#a78bfa"

_COLORS = {
    "present": C_SUCCESS,
    "late":    C_WARNING,
    "timeout": _PURPLE,
    "error":   C_ERROR,
}

_STATUS_TEXT = {
    "present": "PRESENT",
    "late":    "LATE",
    "timeout": "SIGNED OUT",
    "error":   "ERROR",
}


class LogEntry(ctk.CTkFrame):

    def __init__(self, parent, name, entity_id, status, time_str, index=0):
        bg = "#13151c" if index % 2 == 0 else C_BG
        super().__init__(parent, fg_color=bg, corner_radius=0, height=36)
        self.pack_propagate(False)

        color       = _COLORS.get(status, C_MUTED)
        status_text = _STATUS_TEXT.get(status, status.upper())

        # Left dot
        ctk.CTkFrame(self, fg_color=color,
                     width=3, corner_radius=0).pack(
            side="left", fill="y")

        # Name + ID
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(side="left", padx=(10, 0), fill="y")

        ctk.CTkLabel(
            info, text=name,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_TEXT, anchor="w").pack(anchor="w", pady=(5, 0))

        ctk.CTkLabel(
            info, text=f"ID: {entity_id}",
            font=ctk.CTkFont(size=10),
            text_color=C_MUTED, anchor="w").pack(anchor="w", pady=(0, 5))

        # Time (right side)
        ctk.CTkLabel(
            self, text=time_str,
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED, anchor="e").pack(side="right", padx=(0, 16))

        # Status badge
        ctk.CTkLabel(
            self, text=status_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color, anchor="e").pack(side="right", padx=(0, 12))