"""Bounded Ogg/Opus voice-note framing and encoded duration, without decoding.

Only a complete, single-stream mono/stereo Opus recording is accepted. This is
a framing/duration check, not a speech recognizer or an audio-quality claim.
RFC 7845 sections 3-5; RFC 6716 section 3.1 and table 2.
"""
from __future__ import annotations

MAX_VOICE_SECONDS = 60
MAX_PACKET_BYTES = 64 * 1024
SAMPLE_RATE = 48000


def _crc_table():
    table = []
    for byte in range(256):
        value = byte << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(value)
    return tuple(table)


_CRC_TABLE = _crc_table()


def _page_crc(page):
    value = 0
    for index, byte in enumerate(page):
        if 22 <= index < 26:
            byte = 0
        value = ((value << 8) ^ _CRC_TABLE[((value >> 24) ^ byte) & 255]) & 0xFFFFFFFF
    return value


def _packet_samples(packet):
    if not packet:
        raise ValueError("voice_empty_opus_packet")
    config, code = packet[0] >> 3, packet[0] & 3
    frame = ((480, 960, 1920, 2880)[config % 4] if config < 12 else
             (480, 960)[config % 2] if config < 16 else
             (120, 240, 480, 960)[config % 4])
    if code == 3:
        if len(packet) < 2:
            raise ValueError("voice_invalid_opus_frame_count")
        count = packet[1] & 63
    else:
        count = 1 if code == 0 else 2
    if not count or count * frame > 5760:
        raise ValueError("voice_invalid_opus_packet_duration")
    return count * frame


def validate_ogg_opus_duration(data, *, max_seconds=MAX_VOICE_SECONDS):
    """Bound encoded packet work as well as the claimed final granule position.

    Unsupported chained/multiplexed streams and truncated pages fail closed.
    A codec decoder/provider still owns validation of compressed audio frames.
    """
    offset = sequence = packet_count = samples = 0
    serial = None
    pending = bytearray()
    pre_skip = final_granule = 0
    ended = False
    while offset < len(data):
        if ended or len(data) - offset < 27 or data[offset:offset + 5] != b"OggS\x00":
            raise ValueError("voice_invalid_ogg_page")
        flags = data[offset + 5]
        granule = int.from_bytes(data[offset + 6:offset + 14], "little", signed=True)
        page_serial = int.from_bytes(data[offset + 14:offset + 18], "little")
        page_sequence = int.from_bytes(data[offset + 18:offset + 22], "little")
        segment_count = data[offset + 26]
        header_end = offset + 27 + segment_count
        if header_end > len(data) or not segment_count or flags & ~7:
            raise ValueError("voice_invalid_ogg_segments")
        lacing = data[offset + 27:header_end]
        page_end = header_end + sum(lacing)
        if page_end > len(data):
            raise ValueError("voice_truncated_ogg_page")
        if serial is None:
            serial = page_serial
        if (page_serial != serial or page_sequence != sequence
                or bool(flags & 2) != (sequence == 0)
                or bool(flags & 1) != bool(pending)):
            raise ValueError("voice_discontinuous_ogg_stream")
        page = data[offset:page_end]
        if _page_crc(page) != int.from_bytes(page[22:26], "little"):
            raise ValueError("voice_ogg_checksum_mismatch")
        cursor = header_end
        for index, length in enumerate(lacing):
            pending.extend(data[cursor:cursor + length])
            cursor += length
            if len(pending) > MAX_PACKET_BYTES:
                raise ValueError("voice_ogg_packet_too_large")
            if length == 255:
                continue
            packet = bytes(pending)
            pending.clear()
            if packet_count == 0:
                if (len(packet) != 19 or packet[:8] != b"OpusHead" or packet[8] != 1
                        or packet[9] not in (1, 2) or packet[18] != 0
                        or sequence != 0 or index != len(lacing) - 1 or granule != 0):
                    raise ValueError("voice_unsupported_opus_header")
                pre_skip = int.from_bytes(packet[10:12], "little")
            elif packet_count == 1:
                if (len(packet) < 16 or packet[:8] != b"OpusTags"
                        or index != len(lacing) - 1 or granule != 0):
                    raise ValueError("voice_invalid_opus_tags")
            else:
                samples += _packet_samples(packet)
                # Encoder pre-roll and last-packet trimming are bounded too.
                if samples > max_seconds * SAMPLE_RATE + pre_skip + 5760:
                    raise ValueError("voice_duration_exceeded")
            packet_count += 1
        if packet_count <= 2 and granule not in (0, -1):
            raise ValueError("voice_invalid_header_granule")
        if packet_count > 2 and granule != -1:
            if granule < final_granule or granule > samples:
                raise ValueError("voice_invalid_audio_granule")
            final_granule = granule
        ended = bool(flags & 4)
        if ended and (pending or granule < pre_skip):
            raise ValueError("voice_incomplete_ogg_stream")
        offset = page_end
        sequence += 1
    if not ended or pending or packet_count < 3 or final_granule <= pre_skip:
        raise ValueError("voice_incomplete_ogg_stream")
    duration = (final_granule - pre_skip) / SAMPLE_RATE
    if duration > max_seconds:
        raise ValueError("voice_duration_exceeded")
    return {"duration_seconds": duration, "encoded_samples": samples,
            "audio_format": "ogg_opus", "audio_decoded": False}
