import customtkinter as ctk
from ui.theme import C_SURFACE, C_MUTED


class StatsPills(ctk.CTkFrame):
    """
    A row of stat pills. Each pill shows a value and a label.
    pills: list of (key, label, color)
    """

    def __init__(self, parent, pills: list, height=72, **kwargs):
        super().__init__(parent, fg_color="transparent", height=height, **kwargs)
        self.grid_propagate(False)

        self._labels = {}

        for key, label, color in pills:
            pill = ctk.CTkFrame(self, fg_color=C_SURFACE,
                                corner_radius=8, border_width=1, border_color=color)
            pill.pack(side="left", padx=(0, 8))

            val = ctk.CTkLabel(pill, text="—",
                               font=ctk.CTkFont(size=18, weight="bold"),
                               text_color=color)
            val.pack(padx=14, pady=(8, 0))

            ctk.CTkLabel(pill, text=label,
                         font=ctk.CTkFont(size=10),
                         text_color=C_MUTED).pack(padx=14, pady=(0, 8))

            self._labels[key] = val

    def set(self, key: str, value):
        lbl = self._labels.get(key)
        if lbl:
            lbl.configure(text=str(value))

    def reset(self):
        for lbl in self._labels.values():
            lbl.configure(text="—")