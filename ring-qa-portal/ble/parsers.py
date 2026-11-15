"""Encode/decode BLE characteristic bytes according to the ring-model profile."""
import struct

FORMATS = {
    "uint8": "<B",
    "int8": "<b",
    "uint16_le": "<H",
    "int16_le": "<h",
    "uint32_le": "<I",
    "int32_le": "<i",
    "unix_time_le": "<I",  # seconds since 1970-01-01 UTC, 4 bytes little-endian
}
PARSER_NAMES = list(FORMATS) + ["hr_measurement", "ascii", "raw_hex"]


def decode(parser, data: bytes):
    if parser == "hr_measurement":  # Bluetooth SIG Heart Rate Measurement (0x2A37)
        return struct.unpack_from("<H", data, 1)[0] if data[0] & 0x01 else data[1]
    if parser == "ascii":
        return data.decode(errors="replace").strip("\x00 ")
    if parser == "raw_hex":
        return data.hex()
    if parser not in FORMATS:
        raise ValueError(f"unknown parser '{parser}'")
    return struct.unpack_from(FORMATS[parser], data, 0)[0]


def encode(parser, value) -> bytes:
    if parser == "hr_measurement":
        return bytes([0, int(value) & 0xFF])
    if parser == "ascii":
        return str(value).encode()
    if parser == "raw_hex":
        return bytes.fromhex(str(value))
    if parser not in FORMATS:
        raise ValueError(f"unknown parser '{parser}'")
    return struct.pack(FORMATS[parser], int(value))
