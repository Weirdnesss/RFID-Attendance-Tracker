import customtkinter as ctk
from ui.theme import C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED, C_ACCENT, C_SUCCESS, C_WARNING
from ui.components.pagination_bar import PaginationBar

_COLS = [
    ("Session", 220), ("Date", 100), ("Period", 90),
    ("Status",   90), ("Time In", 110), ("Time Out", 110),
]

class HistoryTable(ctk.CTkFrame):
    """
    Reusable paginated attendance history table.
    fetch_fn: callable(entity_id, offset, limit) -> (total, records)
    page_size: number of records per page
    """

    def __init__(self, parent, fetch_fn, page_size: int, **kwargs):
        super().__init__(parent, fg_color="transparent", corner_radius=0, **kwargs)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._fetch_fn   = fetch_fn
        self._page_size  = page_size
        self._entity_id  = None
        self._page       = 0
        self._total      = 0

        # Column headers
        col_hdr = ctk.CTkFrame(self, fg_color=C_ACCENT, corner_radius=0, height=30)
        col_hdr.grid(row=0, column=0, sticky="ew")
        for text, w in _COLS:
            ctk.CTkLabel(col_hdr, text=text, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_TEXT).pack(side="left", padx=4)

        # Scrollable area
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._scroll.grid(row=1, column=0, sticky="nsew")

        # Pagination
        self._pbar = PaginationBar(
            self, on_prev=self._prev_page, on_next=self._next_page)
        self._pbar.grid(row=2, column=0, sticky="ew")

    def load(self, entity_id):
        self._entity_id = entity_id
        self._page      = 0
        self._render()

    def clear(self):
        self._entity_id = None
        self._page      = 0
        self._total     = 0
        for w in self._scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self._scroll, text="No attendance records found.",
            font=ctk.CTkFont(size=13), text_color=C_MUTED).pack(pady=40)
        self._pbar.update(0, 1)

    def _render(self):
        for w in self._scroll.winfo_children():
            w.destroy()

        offset = self._page * self._page_size
        total, records = self._fetch_fn(self._entity_id, offset=offset, limit=self._page_size)
        self._total = total
        pages = max(1, -(-total // self._page_size))

        if not records:
            ctk.CTkLabel(
                self._scroll, text="No attendance records found.",
                font=ctk.CTkFont(size=13), text_color=C_MUTED).pack(pady=40)
            self._pbar.update(0, 1)
            return

        for i, rec in enumerate(records):
            bg = "#13151c" if i % 2 == 0 else C_BG
            sc = {"present": C_SUCCESS, "late": C_WARNING}.get(rec["status"], C_MUTED)

            r = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=0, height=32)
            r.pack(fill="x")
            r.pack_propagate(False)

            for text, w, color, bold in [
                (rec["session_name"],   220, C_TEXT,   False),
                (rec["date"],           100, C_MUTED,  False),
                (rec["period_name"],     90, C_ACCENT, False),
                (rec["status"].upper(),  90, sc,       True),
                (rec["time_in"],        110, C_TEXT,   False),
                (rec["time_out"],       110, C_MUTED,  False),
            ]:
                ctk.CTkLabel(r, text=text, width=w, anchor="w",
                             font=ctk.CTkFont(size=11,
                                             weight="bold" if bold else "normal"),
                             text_color=color).pack(side="left", padx=4)

            ctk.CTkFrame(self._scroll, fg_color=C_BORDER,
                         height=1, corner_radius=0).pack(fill="x")

        self._pbar.update(self._page, pages)
        self._scroll._parent_canvas.yview_moveto(0)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render()

    def _next_page(self):
        pages = max(1, -(-self._total // self._page_size))
        if self._page < pages - 1:
            self._page += 1
            self._render()

    @property
    def total(self):
        return self._total