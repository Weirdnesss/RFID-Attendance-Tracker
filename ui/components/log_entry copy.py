import customtkinter as ctk
from ui.theme import C_ERROR, C_MUTED, C_SUCCESS, C_SURFACE, C_TEXT, C_WARNING

class LogEntry(ctk.CTkFrame):
    _COLORS = {"present": C_SUCCESS, "late": C_WARNING,
               "error": C_ERROR, "timeout": "#a78bfa"}

    def __init__(self, parent, name, student_id, status, time_str):
        color = self._COLORS.get(status, C_MUTED)
        super().__init__(parent, fg_color=C_SURFACE,
                         corner_radius=8, border_width=1,
                         border_color=color)
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="y", padx=(12, 0), pady=10)
        ctk.CTkLabel(left, text=name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(left, text=f"ID: {student_id}",
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED, anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", fill="y", padx=(0, 12), pady=10)
        ctk.CTkLabel(right, text=status.upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=color, anchor="e").pack(anchor="e")
        ctk.CTkLabel(right, text=time_str,
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED, anchor="e").pack(anchor="e")
