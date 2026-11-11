"""Check Standard MIDI File framing before handing events to mido."""
from .session import read_bounded_file

MAX_SMF_BYTES = 16 * 1024 * 1024
MAX_TRACKS = 512
MAX_EVENTS = 250_000
MAX_EVENT_PAYLOAD = 65_536
INVALID_SMF = 'SMFの構造が不正です。'


def _variable_length(data, position, end):
    value = 0
    for _ in range(4):
        if position >= end:
            raise ValueError(INVALID_SMF)
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, position
    raise ValueError(INVALID_SMF)


def _track_events(data, position, end, event_count, lengths):
    running_status = None
    while position < end:
        event_count += 1
        if event_count > MAX_EVENTS:
            raise ValueError('SMFのイベント数が上限を超えています。')
        _, position = _variable_length(data, position, end)
        if position >= end:
            raise ValueError(INVALID_SMF)
        status = data[position]
        explicit_status = status >= 0x80
        if explicit_status:
            position += 1
            if status != 0xFF:
                running_status = status if status < 0xF0 else None
        elif running_status is not None:
            status = running_status
        else:
            raise ValueError(INVALID_SMF)

        if status in (0xF0, 0xF7, 0xFF):
            if status == 0xFF:
                if position >= end:
                    raise ValueError(INVALID_SMF)
                position += 1
            size, position = _variable_length(data, position, end)
            if size > MAX_EVENT_PAYLOAD:
                raise ValueError('SMFのイベントデータが大きすぎます。')
        else:
            size = lengths.get(status, 0) - 1
            if size < 0 or position + size > end:
                raise ValueError(INVALID_SMF)
            if any(byte >= 0x80 for byte in data[position:position + size]):
                raise ValueError(INVALID_SMF)
        position += size
        if position > end:
            raise ValueError(INVALID_SMF)
    return event_count


def read_smf(path, lengths):
    data = read_bounded_file(path, MAX_SMF_BYTES, 'SMFファイルが大きすぎます。')
    if len(data) < 14 or data[:4] != b'MThd':
        raise ValueError(INVALID_SMF)
    header_size = int.from_bytes(data[4:8], 'big')
    position = 8 + header_size
    if header_size < 6 or position > len(data):
        raise ValueError(INVALID_SMF)
    midi_type = int.from_bytes(data[8:10], 'big')
    if midi_type == 2:
        raise ValueError('SMF Format 2には対応していません。')
    tracks = int.from_bytes(data[10:12], 'big')
    division = int.from_bytes(data[12:14], 'big')
    if (midi_type not in (0, 1) or not 1 <= tracks <= MAX_TRACKS
            or midi_type == 0 and tracks != 1):
        raise ValueError(INVALID_SMF)
    if not 1 <= division < 0x8000:
        raise ValueError('SMFの時間分解能はPPQNで指定してください。')

    event_count = 0
    for _ in range(tracks):
        if position + 8 > len(data) or data[position:position + 4] != b'MTrk':
            raise ValueError(INVALID_SMF)
        size = int.from_bytes(data[position + 4:position + 8], 'big')
        position += 8
        end = position + size
        if end > len(data):
            raise ValueError(INVALID_SMF)
        event_count = _track_events(data, position, end, event_count, lengths)
        position = end
    return data
