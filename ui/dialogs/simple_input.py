import tkinter as tk
import customtkinter as ctk
from ui.theme import C_SURFACE, C_BORDER, C_BG, C_TEXT, C_MUTED, C_ACCENT, C_ERROR


class SimpleInputDialog(ctk.CTkToplevel):
    """
    Single or dual field input dialog.
    If second_label is provided, result is a tuple (val1, val2).
    Otherwise result is a string.
    """

    def __init__(self, parent, title: str, label: str, value: str = "",
                 second_label: str = None, second_value: str = "", **kwargs):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("360x200" if second_label else "360x160")
        self.configure(fg_color=C_SURFACE)
        self.grab_set()
        self.resizable(False, False)

        self.result = None
        self._second = second_label is not None

        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=20, pady=(16, 8))

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(body, text=label,
                     font=ctk.CTkFont(size=11), text_color=C_MUTED).pack(anchor="w")
        self._entry = ctk.CTkEntry(body, fg_color=C_BG, border_color=C_BORDER,
                                   text_color=C_TEXT, height=32)
        self._entry.pack(fill="x", pady=(2, 8))
        self._entry.insert(0, value)

        if second_label:
            ctk.CTkLabel(body, text=second_label,
                         font=ctk.CTkFont(size=11), text_color=C_MUTED).pack(anchor="w")
            self._entry2 = ctk.CTkEntry(body, fg_color=C_BG, border_color=C_BORDER,
                                        text_color=C_TEXT, height=32)
            self._entry2.pack(fill="x", pady=(2, 0))
            self._entry2.insert(0, second_value)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=10)

        ctk.CTkButton(foot, text="Cancel", width=80,
                      fg_color="transparent", border_color=C_BORDER,
                      border_width=1, text_color=C_MUTED,
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(foot, text="Save", width=80,
                      fg_color=C_ACCENT, text_color="#fff",
                      command=self._confirm).pack(side="right")

        self._entry.bind("<Return>", lambda e: self._confirm())

    def _confirm(self):
        val = self._entry.get().strip()
        if not val:
            self._entry.configure(border_color=C_ERROR)
            return
        if self._second:
            val2 = self._entry2.get().strip()
            if not val2:
                self._entry2.configure(border_color=C_ERROR)
                return
            self.result = (val, val2)
        else:
            self.result = val
        self.destroy()