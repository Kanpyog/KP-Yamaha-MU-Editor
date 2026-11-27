"""Validate Standard MIDI Files and insert timed XG display events."""
from heapq import merge
from io import BytesIO
from pathlib import Path

from .dependencies import midi_library
from .lcd import LCD_MESSAGE_INTERVAL, is_lcd_packet
from .protocol import TG300B_SYSTEM_ON, parse
from .session import atomic_write, read_bounded_file

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
    _validate_smf(data, lengths)
    return data


def _validate_smf(data, lengths):
    if len(data) > MAX_SMF_BYTES:
        raise ValueError('SMFファイルが大きすぎます。')
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


def _status_lengths():
    from mido.messages.specs import SPEC_BY_STATUS
    return {status: spec['length'] for status, spec in SPEC_BY_STATUS.items()}


def load_smf_file(path):
    mido = midi_library()
    return mido.MidiFile(file=BytesIO(read_smf(path, _status_lengths())))


def _at_ticks(track):
    tick = 0
    for message in track:
        tick += message.time
        yield tick, message


def _is_synth_reset(raw):
    if raw == TG300B_SYSTEM_ON:
        return True
    if len(raw) == 6 and raw[1] == 0x7E and raw[3] == 0x09 and raw[4] in (1, 2, 3):
        return True
    return (len(raw) == 9 and raw[1] == 0x43 and raw[2] & 0xF0 == 0x10
            and raw[3:6] == bytes((0x4C, 0, 0)) and raw[6] in (0x7E, 0x7F) and raw[7] == 0)


def _tick_after(tick, delay_us, ticks_per_beat, tempos):
    remaining = delay_us * ticks_per_beat
    tempo = 500_000
    for change_tick, new_tempo in tempos:
        if change_tick > tick:
            span = (change_tick - tick) * tempo
            if remaining <= span:
                break
            remaining -= span
            tick = change_tick
        tempo = new_tempo
    return tick + (remaining + tempo - 1) // tempo


def _display_start(midi):
    tempos = []
    first_note = None
    last_reset = None
    for tick, message in merge(*(_at_ticks(track) for track in midi.tracks), key=lambda event: event[0]):
        if message.type == 'set_tempo':
            if not message.tempo:
                raise ValueError('MIDIのテンポが不正です。')
            tempos.append((tick, message.tempo))
        elif message.type == 'note_on' and message.velocity and first_note is None:
            first_note = tick
        elif (message.type == 'sysex' and (first_note is None or tick <= first_note)
              and _is_synth_reset(bytes(message.bytes()))):
            last_reset = tick
    start = first_note or 0
    if last_reset is not None:
        start = max(start, _tick_after(last_reset, 100_000, midi.ticks_per_beat, tempos))
    return start, tempos


def _delta_track(mido, events):
    track = mido.MidiTrack()
    previous = end = 0
    for tick, message in events:
        end = tick
        if message.type != 'end_of_track':
            track.append(message.copy(time=tick - previous))
            previous = tick
    track.append(mido.MetaMessage('end_of_track', time=end - previous))
    return track


def embed_lcd_midi(source, destination, packets):
    """Preserve the song while adding LCD messages near the first played note."""
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('元のMIDIファイルとは別の名前で保存してください。')
    packets = tuple(packets)
    if not packets or any(not is_lcd_packet(parse(raw)) for raw in packets):
        raise ValueError('組み込めるLCD用SysExがありません。')

    mido = midi_library()
    midi = load_smf_file(source)
    tick, tempos = _display_start(midi)
    events = []
    for raw in packets:
        events.append((tick, mido.Message.from_bytes(raw)))
        tick = _tick_after(tick, round(LCD_MESSAGE_INTERVAL * 1_000_000), midi.ticks_per_beat, tempos)

    if midi.type == 0 and not any(msg.type == 'midi_port' and msg.port for msg in midi.tracks[0]):
        midi.tracks[0] = _delta_track(mido, merge(_at_ticks(midi.tracks[0]), events,
                                                 key=lambda event: event[0]))
    else:
        # Port A gets its own track when musical events have independent routing.
        midi.type = 1
        header = ((0, mido.MetaMessage('track_name', name='LCD')), (0, mido.MetaMessage('midi_port', port=0)))
        midi.tracks.append(_delta_track(mido, (*header, *events)))

    output = BytesIO()
    midi.save(file=output)
    data = output.getvalue()
    _validate_smf(data, _status_lengths())
    atomic_write(destination, data)
