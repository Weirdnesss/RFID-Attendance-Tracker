import tkinter as tk
import customtkinter as ctk
from ui.theme import C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED
from ui.components.pagination_bar import PaginationBar


class PaginatedListScreen(ctk.CTkFrame):
    """
    Base class for entity list screens (Students, Staff, etc.)
    Subclasses must implement:
        _title() -> str
        _search_placeholder() -> str
        _empty_text() -> str
        _id_key() -> str
        _page_size() -> int
        _placeholder() -> dict
        _item_cls()              — list item class
        _detail_cls()            — detail panel class
        _build_filters(left)     — add filter widgets to left panel
        _fetch_page(search, offset, limit) -> (list, int)
        _fetch_filters()         — reload filter option menus
        _get_filter_kwargs() -> dict  — current filter values for fetch
        _count_label(total) -> str
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)

        self._page          = 0
        self._total_count   = 0
        self._selected_id   = None
        self._selected_item = None
        self._list_items    = []
        self._loading       = False

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)

        self._init_filter_vars()
        self._build_ui()
        self.after(600, self.refresh)

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def _title(self) -> str:
        raise NotImplementedError

    def _search_placeholder(self) -> str:
        return "Search name or ID..."

    def _empty_text(self) -> str:
        raise NotImplementedError

    def _id_key(self) -> str:
        raise NotImplementedError

    def _page_size(self) -> int:
        raise NotImplementedError

    def _placeholder(self) -> dict:
        raise NotImplementedError

    def _item_cls(self):
        raise NotImplementedError

    def _detail_cls(self):
        raise NotImplementedError

    def _init_filter_vars(self):
        """Initialize any filter StringVars and trace them."""
        pass

    def _build_filters(self, left: ctk.CTkFrame):
        """Add filter rows to the left panel (rows 2, 3)."""
        pass

    def _fetch_page(self, search: str, offset: int, limit: int):
        raise NotImplementedError

    def _reload_filter_options(self):
        """Reload filter option menus from DB and reset their values."""
        pass

    def _count_label(self, total: int) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ── Left panel ────────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=C_SURFACE,
                            corner_radius=0, width=300)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(5, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(left, fg_color=C_SURFACE,
                           corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text=self._title(),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT).grid(
            row=0, column=0, sticky="w", padx=16, pady=14)

        self._count_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._count_lbl.grid(row=0, column=1, padx=(0, 16))

        # Search
        ctk.CTkEntry(
            left, textvariable=self._search_var,
            placeholder_text=self._search_placeholder(),
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32, corner_radius=8,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 4))

        # Filters (subclass fills rows 2, 3)
        self._build_filters(left)

        ctk.CTkFrame(left, fg_color=C_BORDER,
                     height=1).grid(row=4, column=0, sticky="ew")

        # Scrollable list
        self._list_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0)
        self._list_scroll.grid(row=5, column=0, sticky="nsew")
        self._list_scroll.grid_columnconfigure(0, weight=1)

        self._build_list_pool()

        # Pagination bar
        self._pbar = PaginationBar(
            left, on_prev=self._prev_page, on_next=self._next_page)
        self._pbar.grid(row=6, column=0, sticky="ew")

        # ── Right panel ───────────────────────────────────────────────
        self._detail = self._detail_cls()(self)
        self._detail.grid(row=0, column=1, sticky="nsew")

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self):
        self._loading = True
        self._reload_filter_options()
        self._search_var.set("")
        self._loading = False

        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._detail.clear()
        self._load_page()

    def _load_page(self):
        offset = self._page * self._page_size()
        items, total = self._fetch_page(
            search=self._search_var.get().strip(),
            offset=offset,
            limit=self._page_size(),
        )
        self._total_count = total
        self._render_list(items)
        self._update_pagination()

    def _build_list_pool(self):
        self._list_items = []
        for _ in range(self._page_size()):
            item = self._item_cls()(
                self._list_scroll, self._placeholder(),
                on_select=self._on_select)
            item.pack(fill="x", padx=10, pady=4)
            item.pack_forget()
            self._list_items.append(item)

    def _render_list(self, items: list):
        self._selected_item = None
        self._count_lbl.configure(text=self._count_label(self._total_count))

        for i, slot in enumerate(self._list_items):
            if i < len(items):
                data   = items[i]
                is_sel = data[self._id_key()] == self._selected_id
                slot.update_data(data, selected=is_sel)
                slot.pack(fill="x", padx=10, pady=4)
                if is_sel:
                    self._selected_item = slot
            else:
                slot.pack_forget()

        if not items:
            if not hasattr(self, "_empty_lbl"):
                self._empty_lbl = ctk.CTkLabel(
                    self._list_scroll, text=self._empty_text(),
                    font=ctk.CTkFont(size=13), text_color=C_MUTED)
            self._empty_lbl.pack(pady=40)
        else:
            if hasattr(self, "_empty_lbl"):
                self._empty_lbl.pack_forget()

    def _update_pagination(self):
        total_pages = max(1, -(-self._total_count // self._page_size()))
        self._pbar.update(self._page, total_pages)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._load_page()

    def _next_page(self):
        total_pages = max(1, -(-self._total_count // self._page_size()))
        if self._page < total_pages - 1:
            self._page += 1
            self._load_page()

    def _on_search_changed(self, *_):
        if self._loading:
            return
        if hasattr(self, "_search_job"):
            self.after_cancel(self._search_job)
        self._search_job = self.after(400, self._reset_and_load)

    def _apply_filters(self, *_):
        if self._loading:
            return
        self._reset_and_load()

    def _reset_and_load(self):
        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._load_page()

    def _on_select(self, data: dict):
        if data[self._id_key()] == self._selected_id:
            return
        if self._selected_item is not None:
            self._selected_item.deselect()

        self._selected_id = data[self._id_key()]
        new_item = next(
            (s for s in self._list_items
             if s._data[self._id_key()] == self._selected_id), None)
        if new_item:
            new_item.select()
            self._selected_item = new_item

        self._detail.load(data)