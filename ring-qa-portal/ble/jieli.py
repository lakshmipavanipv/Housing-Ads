"""Jieli 0xAB framing used by SR16 / Sadhana rings (service a00a, write b002, notify b003).

  [0] 0xAB  [1] flag (0x01 request, 0x11 reply/ACK)  [2..3] dataLen BE  [4..5] CRC16/ARC BE
  [6] CMD   [7] Key   [8] KeyFlag   [9..] payload          dataLen = 3 + len(payload)
"""
MAGIC = 0xAB
FLAG_REQUEST = 0x01
FLAG_REPLY = 0x11


def crc16arc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build(body: bytes, flag: int = FLAG_REQUEST) -> bytes:
    """body = CMD + Key + KeyFlag + payload."""
    if len(body) < 3:
        raise ValueError("Jieli body needs at least CMD, Key and KeyFlag bytes")
    crc = crc16arc(body)
    return bytes([MAGIC, flag, len(body) >> 8, len(body) & 0xFF, crc >> 8, crc & 0xFF]) + body


def parse(pkt: bytes):
    """Returns (flag, cmd, key, key_flag, payload) for a complete single-packet frame, else None."""
    if len(pkt) < 9 or pkt[0] != MAGIC:
        return None
    n = (pkt[2] << 8) | pkt[3]
    body = pkt[6:6 + n]
    return pkt[1], body[0], body[1], body[2], bytes(body[3:])


def ack(cmd: int, key: int, key_flag: int) -> bytes:
    """Auto-reply the app must send for every ring-originated (non-reply) frame."""
    return build(bytes([cmd, key, key_flag]) + (b"\x00" if (cmd, key) == (6, 9) else b""), FLAG_REPLY)
