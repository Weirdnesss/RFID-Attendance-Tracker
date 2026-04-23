"""
rfid_reader.py
--------------
Pure RFID reader logic for ACR1252U — NO PyQt6 dependency.
Safe to import in test scripts, CLI tools, or anywhere else.

Card data format (MIFARE 1K Block 1):
    e.g. "2025241511213"
          ^^^^   = school_year  (chars 0–3)
              ^  = school_term  (char  4)
               ^ = student_id   (chars 5+)
"""

import time
import logging
from dataclasses import dataclass

from smartcard.System import readers
from smartcard.Exceptions import CardConnectionException, NoCardException
from smartcard.util import toHexString

logger = logging.getLogger(__name__)

CMD_GET_UID    = [0xFF, 0xCA, 0x00, 0x00, 0x00]
CMD_LOAD_KEY   = [0xFF, 0x82, 0x00, 0x00, 0x06,
                  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
CMD_AUTH_BLOCK1 = [0xFF, 0x86, 0x00, 0x00, 0x05,
                   0x01, 0x00, 0x01, 0x60, 0x00]
CMD_READ_BLOCK1 = [0xFF, 0xB0, 0x00, 0x01, 0x10]
SW_SUCCESS = (0x90, 0x00)

@dataclass
class CardData:
    raw: str
    student_id: int
    uid: str

def parse_card_data(raw: str, uid: str) -> CardData | None:
    raw = raw.strip().rstrip('\x00')
    if len(raw) < 6:
        logger.warning(f"Card data too short: '{raw}'")
        return None
    try:
        return CardData(
            raw=raw,
            student_id=int(raw[5:]),
            uid=uid,
        )
    except ValueError as e:
        logger.warning(f"Parse failed for '{raw}': {e}")
        return None

def bytes_to_string(data: list[int]) -> str:
    return bytes(data).decode("ascii", errors="ignore").rstrip("\x00")

_last_reader_state = None  # module-level state

def get_reader():
    global _last_reader_state

    available = readers()
    has_reader = bool(available)

    if has_reader != _last_reader_state:
        if not has_reader:
            logger.warning("No PC/SC readers found.")
        else:
            logger.info(f"Using reader: {available[0]}")

        _last_reader_state = has_reader

    return available[0] if has_reader else None

def read_card(reader) -> tuple[str | None, str | None]:
    connection = reader.createConnection()
    try:
        connection.connect()
    except (CardConnectionException, NoCardException):
        return None, None

    try:
        data, sw1, sw2 = connection.transmit(CMD_GET_UID)
        if (sw1, sw2) != SW_SUCCESS:
            return None, None
        uid = toHexString(data).replace(" ", "")

        _, sw1, sw2 = connection.transmit(CMD_LOAD_KEY)
        if (sw1, sw2) != SW_SUCCESS:
            return uid, None

        _, sw1, sw2 = connection.transmit(CMD_AUTH_BLOCK1)
        if (sw1, sw2) != SW_SUCCESS:
            return uid, None

        data, sw1, sw2 = connection.transmit(CMD_READ_BLOCK1)
        if (sw1, sw2) != SW_SUCCESS:
            return uid, None

        return uid, bytes_to_string(data)

    except Exception as e:
        logger.error(f"Card read error: {e}")
        return None, None
    finally:
        try:
            connection.disconnect()
        except Exception:
            pass
