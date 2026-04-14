"""
rfid_listener.py
----------------
Pure Python threading wrapper around rfid_reader.py.

Usage:
    listener = RFIDListener(
        on_card=my_card_handler,
        on_error=my_error_handler,
        on_connected=my_connected_handler,
        on_disconnected=my_disconnected_handler,
    )
    listener.start()
    ...
    listener.stop()


"""

import threading
import logging
from hardware.rfid_reader import get_reader, read_card, parse_card_data, CardData

logger = logging.getLogger(__name__)


class RFIDListener:
    POLL_INTERVAL   = 0.4
    RESCAN_COOLDOWN = 2.0
    RETRY_INTERVAL  = 3.0

    def __init__(self, on_card=None, on_error=None,
                 on_connected=None, on_disconnected=None):
        self._on_card         = on_card
        self._on_error        = on_error
        self._on_connected    = on_connected
        self._on_disconnected = on_disconnected

        self._running_event = threading.Event()
        self._thread        = None
        self._last_uid      = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return  # already running

        self._running_event.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running_event.clear()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)  # wait for clean shutdown

    def _emit(self, callback, *args):
        if not self._running_event.is_set():
            return  # don't emit after stop

        if callback:
            try:
                callback(*args)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _run(self):
        reader_present = False

        while self._running_event.is_set():
            reader = get_reader()

            # ── No reader ─────────────────────────────
            if reader is None:
                if reader_present:
                    self._emit(self._on_disconnected)
                    reader_present = False

                if not self._running_event.wait(self.RETRY_INTERVAL):
                    break
                continue

            # ── Reader connected ──────────────────────
            if not reader_present:
                self._emit(self._on_connected)
                reader_present = True

            uid, block1_str = read_card(reader)

            # ── No card ───────────────────────────────
            if uid is None:
                self._last_uid = None
                if not self._running_event.wait(self.POLL_INTERVAL):
                    break
                continue

            # ── Duplicate scan ────────────────────────
            if uid == self._last_uid:
                if not self._running_event.wait(self.POLL_INTERVAL):
                    break
                continue

            self._last_uid = uid

            # ── Read error ────────────────────────────
            if block1_str is None:
                self._emit(self._on_error,
                    f"Card UID {uid} — Block 1 could not be read.")
                if not self._running_event.wait(self.RESCAN_COOLDOWN):
                    break
                continue

            card = parse_card_data(block1_str, uid)

            if card is None:
                self._emit(self._on_error,
                    f"Card UID {uid} — invalid format.")
                if not self._running_event.wait(self.RESCAN_COOLDOWN):
                    break
                continue

            # ── Success ───────────────────────────────
            logger.info(
                f"Scanned — UID: {card.uid} | "
                f"Student: {card.student_id}"
            )

            self._emit(self._on_card, card)

            if not self._running_event.wait(self.RESCAN_COOLDOWN):
                break
