"""LCD encoding, model eligibility and MIDI embedding regression tests."""
import tempfile
import unittest
from pathlib import Path

import mido

from kp_mu_editor.engine import load_midi
from kp_mu_editor.lcd import LCD_BITMAP_ADDRESS, is_lcd_packet, lcd_bitmap, lcd_text
from kp_mu_editor.protocol import bulk, change, is_setup_packet, parse
from kp_mu_editor.schema import PROFILES
from kp_mu_editor.session import Session
from kp_mu_editor.smf import embed_lcd_midi


def midi_message(raw, time=0):
    return mido.Message.from_bytes(raw).copy(time=time)


class LCDTests(unittest.TestCase):
    def test_text_and_bitmap_use_xg_parameter_changes(self):
        self.assertEqual(lcd_text('MU', 3), bytes.fromhex('F0 43 13 4C 06 00 00 4D 55 F7'))
        pixels = {(0, 0), (6, 0), (7, 1), (13, 15), (14, 3), (15, 15)}
        message = lcd_bitmap(pixels, 3)
        self.assertEqual(message[:7], bytes.fromhex('F0 43 13 4C 07 00 00'))
        self.assertEqual(message[-1], 0xF7)
        expected = bytearray(48)
        for offset, value in ((0, 0x41), (17, 0x40), (31, 0x01), (35, 0x40), (47, 0x20)):
            expected[offset] = value
        self.assertEqual(message[7:-1], expected)
        self.assertEqual(parse(lcd_bitmap((), 0)).data, bytes(48))
        for invalid in ('', 'a' * 33, '音', 'a\n'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                lcd_text(invalid, 0)
        with self.assertRaises(ValueError):
            lcd_bitmap({(16, 0)}, 0)

    def test_display_writes_are_separate_from_setup_packets(self):
        session = Session('MU80')
        for raw in (lcd_text('MU', 0), lcd_bitmap({(2, 3)}, 0),
                    change((6, 0, 31), [0x7F]), change((7, 0, 47), [0x20])):
            self.assertTrue(is_lcd_packet(parse(raw)))
            self.assertFalse(is_setup_packet(parse(raw)))
            self.assertIsNone(session.receive(raw))
        self.assertEqual(session.memory, {})
        for raw in (change((6, 0, 31), b'MU'), change((6, 0, 0), [0x1F]),
                    change((7, 0, 47), [0x20, 0x40]), change((7, 1, 0), [0x40]),
                    bulk(LCD_BITMAP_ADDRESS, [0] * 48), change((6, 0, 0), b'MU', model=0x49)):
            self.assertFalse(is_lcd_packet(parse(raw)))

    def test_model_capabilities_do_not_follow_tone_generation(self):
        for model in ('MU15', 'MU50', 'MU80', 'MU90', 'MU90R', 'MU100',
                      'MU100R', 'MU128', 'MU128 V2', 'MU1000', 'MU2000 EX R1'):
            self.assertTrue(PROFILES[model].lcd, model)
        for model in ('MU5', 'MU5K', 'MU10', 'MU90B', 'MU100B', 'MU100Bs', 'MU500'):
            self.assertFalse(PROFILES[model].lcd, model)

    def test_playback_filters_display_independently_of_sound_settings(self):
        text = lcd_text('MU', 0)
        setup = change((0, 0, 4), [93])
        invalid = change((6, 0, 31), b'MU')
        note = mido.Message('note_on', note=65)
        midi = mido.MidiFile(type=0)
        midi.tracks.append(mido.MidiTrack([midi_message(raw) for raw in (text, setup, invalid)] + [note]))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'song.mid'
            midi.save(path)
            for keep_setup, allow_lcd, expected in (
                (False, True, [text, bytes(note.bytes())]),
                (True, True, [text, setup, bytes(note.bytes())]),
                (False, False, [bytes(note.bytes())]),
                (True, False, [setup, bytes(note.bytes())]),
            ):
                rows = load_midi(path, keep_setup, allow_lcd=allow_lcd)
                self.assertEqual([row[3] for row in rows], expected)

    def test_format_zero_insert_preserves_source_notes_and_end_time(self):
        text = lcd_text('SONG', 0)
        image = lcd_bitmap({(15, 15)}, 0)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.mid'
            destination = Path(folder) / 'with-lcd.mid'
            midi = mido.MidiFile(type=0, ticks_per_beat=480)
            midi.tracks.append(mido.MidiTrack([
                mido.MetaMessage('lyrics', text='Intro', time=12),
                mido.Message('note_on', note=60, time=108),
                mido.Message('note_off', note=60, time=480),
                mido.MetaMessage('end_of_track', time=72),
            ]))
            midi.save(source)
            original = source.read_bytes()
            with self.assertRaises(ValueError):
                embed_lcd_midi(source, source, (text,))
            embed_lcd_midi(source, destination, (text, image))
            self.assertEqual(source.read_bytes(), original)
            actual = mido.MidiFile(destination)
            self.assertEqual(actual.type, 0)

            def timestamps(track):
                tick = 0
                result = []
                for msg in track:
                    tick += msg.time
                    if msg.type != 'sysex':
                        result.append((tick, msg.copy(time=0)))
                return result

            self.assertEqual(timestamps(actual.tracks[0]), timestamps(midi.tracks[0]))
            output = [(time, raw) for time, _, _, raw in load_midi(destination, False, allow_lcd=True)
                      if raw[0] == 0xF0]
            self.assertEqual([raw for _, raw in output], [text, image])
            self.assertAlmostEqual(output[0][0], 0.125)
            self.assertGreaterEqual(output[1][0] - output[0][0], 0.039999)

    def test_format_one_uses_port_a_and_accounts_for_reset_and_tempo_change(self):
        reset = change((0, 0, 0x7E), [0])
        text = lcd_text('TITLE', 0)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'multi.mid'
            destination = Path(folder) / 'copy.mid'
            midi = mido.MidiFile(type=1, ticks_per_beat=480)
            midi.tracks.extend([
                mido.MidiTrack([midi_message(reset), mido.MetaMessage('set_tempo', tempo=250000, time=48)]),
                mido.MidiTrack([mido.MetaMessage('midi_port', port=1),
                                mido.Message('note_on', channel=3, note=60),
                                mido.Message('note_off', channel=3, note=60, time=480)]),
            ])
            midi.save(source)
            embed_lcd_midi(source, destination, (text,))
            copied = mido.MidiFile(destination)
            self.assertEqual(copied.tracks[:2], mido.MidiFile(source).tracks)
            self.assertEqual(copied.tracks[2][1], mido.MetaMessage('midi_port', port=0))
            schedule = load_midi(destination, allow_lcd=True)
            lcd_event = next(row for row in schedule if row[3] == text)
            self.assertAlmostEqual(lcd_event[0], 0.1)
            self.assertEqual(lcd_event[2], 0)
            self.assertEqual([port for _, _, port, raw in schedule if raw[0] < 0xF0], [1, 1])

    def test_format_zero_with_port_b_keeps_music_and_lcd_on_separate_ports(self):
        message = lcd_text('PORT', 0)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'port-b.mid'
            destination = Path(folder) / 'port-a-lcd.mid'
            midi = mido.MidiFile(type=0)
            midi.tracks.append(mido.MidiTrack([
                mido.MetaMessage('midi_port', port=1), mido.Message('note_on', note=41),
            ]))
            midi.save(source)
            embed_lcd_midi(source, destination, (message,))
            self.assertEqual(mido.MidiFile(destination).type, 1)
            self.assertEqual([(port, raw) for _, _, port, raw in load_midi(destination, allow_lcd=True)],
                             [(1, bytes.fromhex('90 29 40')), (0, message)])
