"""Validated Yamaha MIDI 1.0 messages, address space and bulk framing."""
from __future__ import annotations
from dataclasses import dataclass


def _seven(values):
    values = tuple(values)
    if any(not isinstance(x, int) or not 0 <= x <= 127 for x in values):
        raise ValueError("MIDIデータは0～127で指定してください。")
    return bytes(values)


def checksum(values):
    return (-sum(values)) & 127


def change(address, data, device=0, model=0x4C):
    if not 0 <= device <= 15 or len(address) != 3:
        raise ValueError("デバイス番号またはアドレスが不正です。")
    body = _seven((*address, *data))
    if model == 0x44:  # MU5 native includes a checksum in parameter changes.
        return bytes((0xF0, 0x43, 0x10 | device, model)) + body + bytes((checksum(body), 0xF7))
    return bytes((0xF0, 0x43, 0x10 | device, model)) + body + b"\xf7"


def request(address, device=0, model=0x4C, parameter=False, count=None):
    if len(address) != 3 or not 0 <= device <= 15:
        raise ValueError("リクエストが不正です。")
    if model==0x44:
        if count is None:
            if parameter:count=2 if (address[0]==0 and address[2]==0) or (address[0]==2 and address[2]==10) else 1
            else:count=7 if address==(0,0,0) else 22 if address[0]==2 else 16 if address==(3,0,0) else 1
        body=_seven(address)+encode(count,3)
        return bytes((0xf0,0x43,0x30|device,model))+body+bytes((checksum(body),0xf7))
    return bytes((0xF0, 0x43, (0x30 if parameter else 0x20) | device, model)) + _seven(address) + b"\xf7"


def bulk(address, data, device=0, model=0x4C):
    data = _seven(data)
    body = _seven((len(data) >> 7, len(data) & 127, *address)) + data
    return bytes((0xF0, 0x43, device, model)) + body + bytes((checksum(body), 0xF7))


@dataclass(frozen=True)
class Packet:
    model: int
    device: int
    address: tuple[int, int, int]
    data: bytes
    bulk: bool


def is_setup_write(model, address, size):
    """Allow writable MU parameter pages, excluding reset, identity and display."""
    high, middle, low = address
    end = low + size
    if not 1 <= size <= 128 or not 0 <= low < end <= 128:
        return False
    if model == 0x44:
        return (high == 0 and middle == 0 and end <= 7
                or high == 2 and 0 <= middle < 16 and end <= 22)
    if model == 0x49:
        return high == 0 and middle == 0 and end <= 0x13
    if model != 0x4C:
        return False
    if high == 0:
        return middle == 0 and end <= 7
    if high == 2:
        return middle in (1, 0x40)
    if high == 3:
        return 0 <= middle < 4
    if high in (8, 0x0A):
        return 0 <= middle < 64
    if high == 0x10:
        return 0 <= middle < 2
    if 0x30 <= high <= 0x33:
        return 13 <= middle <= 91
    return high == 0x70 and 0 <= middle < 3 and low < 16 and size == 1


def is_setup_packet(packet):
    return packet is not None and is_setup_write(packet.model, packet.address, len(packet.data))


def parse(data):
    data = bytes(data)
    if len(data) < 8 or data[:2] != b"\xf0\x43" or data[-1] != 0xF7:
        return None
    if any(x > 127 for x in data[1:-1]):
        raise ValueError("SysEx内に不正なデータバイトがあります。")
    command = data[2] & 0xF0
    if command == 0:
        if len(data) < 11:
            raise ValueError("バルクデータが短すぎます。")
        count = data[4] * 128 + data[5]
        if len(data) != count + 11 or sum(data[4:-1]) & 127:
            raise ValueError("バルクデータの長さまたはチェックサムが一致しません。")
        return Packet(data[3], data[2] & 15, tuple(data[6:9]), data[9:-2], True)
    if command == 0x10:
        payload = data[7:-1]
        if data[3] == 0x44:
            if sum(data[4:-1]) & 127:
                raise ValueError("MU5チェックサムが一致しません。")
            payload = data[7:-2]
        return Packet(data[3], data[2] & 15, tuple(data[4:7]), payload, False)
    return None


def split_sysex(data):
    result, current = [], None
    for b in bytes(data):
        if b == 0xF0:
            if current is not None:
                raise ValueError("途中で切れたSysExがあります。")
            current = bytearray((b,))
        elif b == 0xF7:
            if current is None:
                raise ValueError("SysExの開始がありません。")
            current.append(b)
            result.append(bytes(current))
            current = None
        elif b >= 0xF8:
            continue
        elif current is not None:
            if b > 127:
                raise ValueError("SysEx内部に不正なステータスがあります。")
            current.append(b)
        elif b not in (9, 10, 13, 32):
            raise ValueError("SysEx以外のデータがあります。")
    if current is not None:
        raise ValueError("最後のSysExが途中で切れています。")
    return result


def encode(value, size=1, nibble=False):
    base = 16 if nibble else 128
    if not 0 <= value < base ** size:
        raise ValueError("値がデータサイズに収まりません。")
    return bytes((value // base ** i) % base for i in reversed(range(size)))


def decode(data, nibble=False):
    base, result = (16 if nibble else 128), 0
    for b in data:
        if b >= base:
            raise ValueError("データの桁が範囲外です。")
        result = result * base + b
    return result


def cc(channel, number, value):
    if not 0 <= channel < 16:
        raise ValueError("MIDIチャンネルが不正です。")
    return bytes((0xB0 | channel,)) + _seven((number, value))


def rpn(channel, msb, lsb, value, nrpn=False, fine=None):
    result = [cc(channel, 99 if nrpn else 101, msb),
              cc(channel, 98 if nrpn else 100, lsb), cc(channel, 6, value)]
    if fine is not None:
        result.append(cc(channel, 38, fine))
    result += [cc(channel, 101, 127), cc(channel, 100, 127)]
    return result
