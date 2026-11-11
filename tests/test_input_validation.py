"""Regression checks for imported settings and file boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mido

from kp_mu_editor.engine import load_midi
from kp_mu_editor.protocol import bulk, change
from kp_mu_editor.session import Session


class InputValidationTests(unittest.TestCase):
    def test_imported_identity_is_retained_but_not_exported_as_a_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'set.mu.json'
            session = Session()
            identity = bulk((1, 0, 0), b'MU500')
            voice = change((8, 0, 3), [1])
            session.import_sysex(identity + voice)
            session.save(path)
            restored = Session.load(path)
            self.assertEqual(restored.get_bytes(0x4C, (1, 0, 0), 5), b'MU500')
            self.assertEqual(restored.export_messages(), [voice])

    def test_setup_export_validates_the_complete_system_field(self):
        session = Session()
        session.put(0x4C, (0, 0, 7), [64])
        self.assertEqual(session.export_messages(), [])

    def test_truncated_smf_is_rejected_before_mido_parses_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'song.mid'
            midi = mido.MidiFile(type=0)
            track = midi.add_track()
            track.append(mido.Message('note_on', note=60, velocity=80))
            midi.save(path)
            path.write_bytes(path.read_bytes()[:-1])
            with patch('mido.MidiFile') as parser:
                with self.assertRaises(ValueError):
                    load_midi(path)
                parser.assert_not_called()

    def test_song_setup_can_keep_normal_voice_changes_and_omit_device_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'song.mid'
            midi = mido.MidiFile(type=0)
            track = midi.add_track()
            voice = change((8, 0, 3), [1])
            for raw in (bulk((1, 0, 0), b'MU500'), voice):
                track.append(mido.Message('sysex', data=raw[1:-1]))
            midi.save(path)
            self.assertEqual([event[3] for event in load_midi(path)], [voice])


if __name__ == '__main__':
    unittest.main()
