import tempfile
import unittest
from unittest.mock import Mock, patch

from kp_mu_editor.engine import Engine
from kp_mu_editor.protocol import bulk, change, request
from kp_mu_editor.schema import PROFILES, SetupScope, read_blocks, setup_read_blocks, supports_setup_write
from kp_mu_editor.session import Session


class ModelAddressTests(unittest.TestCase):
    def test_mu15_xg_blocks_match_tables_1_1_to_1_7(self):
        profile = PROFILES['MU15']
        # System, info, six effect blocks, two blocks per part, two drum maps.
        expected = {(0, 0, 0), (1, 0, 0)}
        expected.update((2, 1, low) for low in (0, 0x10, 0x20, 0x30, 0x40, 0x70))
        expected.update((8, part, low) for part in range(16) for low in (0, 0x30))
        expected.update((group, note, 0) for group in (0x30, 0x31) for note in range(13, 92))
        blocks = read_blocks(profile)
        self.assertEqual(len(blocks), len(expected))
        self.assertEqual(set(blocks), {(0x4c, address) for address in expected})
        for scope in SetupScope:
            self.assertTrue(all(block[0] == 0x4c for block in setup_read_blocks(profile, scope)))
        self.assertIn((0x4c, (8, 15, 0x13), True), setup_read_blocks(profile, SetupScope.EFFECTS))

        class Mu15Transport:
            outputs = {}

            def __init__(self):
                self.requests = []
                self.pending = []

            def send(self, raw, port=0):
                if raw[2] >> 4 != 2:
                    return
                self.requests.append(raw)
                address = tuple(raw[4:7])
                if raw[3] == 0x4c and address in expected:
                    self.pending.append((0, bulk(address, [64]), 0))

            def poll(self):
                pending, self.pending = self.pending, []
                return pending

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, start_worker=False)
            engine.transport = transport = Mu15Transport()
            engine.connected = True
            report = engine._read(blocks, 'read')
            self.assertEqual(report['count'], len(expected))
            self.assertEqual(report['missing'], [])
            first_requests = list(transport.requests)
            engine.finished.connect(lambda *_: engine.shutdown.set())
            engine.reset_xg(blocks)
            engine._run()
            self.assertEqual(transport.requests, first_requests * 2)

    def test_mu10_supplies_no_queries_for_any_read_scope(self):
        for scope in SetupScope:
            self.assertEqual(setup_read_blocks(PROFILES['MU10'], scope), [])

    def test_mu50_and_mu80_use_their_documented_drum_maps(self):
        for model, setups, last_note in (('MU50', 2, 84), ('MU80', 4, 91)):
            with self.subTest(model=model):
                profile = PROFILES[model]
                blocks = setup_read_blocks(profile, SetupScope.DRUM_MAP)
                expected = [(0x4c, (0x30 + setup, note, 0)) for setup in range(setups)
                            for note in range(13, last_note + 1)]
                self.assertEqual(blocks, expected)
                self.assertIn((0x49, (0, 0, 0)), read_blocks(profile))
                self.assertNotIn((0x49, (0, 0, 0x12)), read_blocks(profile))

    def test_older_session_exports_only_supported_model_addresses(self):
        volume = change((8, 0, 0x0b), [80])
        part_receive_bank = change((8, 0, 0x40), [0])
        native_block = bulk((0, 0, 0), [0, 0, 0, 1, 0, 2, 0, 64, 2, 0], model=0x49)
        native_receive_bank = change((0, 0, 4), [0], model=0x49)
        unsupported = [
            change((0, 0, 2), [1], model=0x49),
            change((0, 0, 0x12), [1], model=0x49),
            bulk((2, 0x40, 0), [0, 0x40]),
            bulk((3, 0, 0), [0x49, 0]),
            bulk((8, 16, 0), [0, 0, 0, 0]),
            change((8, 0, 0x72), [65]),
            change((0x0a, 0, 0x20), [65]),
            change((0x10, 0, 0x13), [40]),
            change((0x32, 38, 2), [40]),
            change((0x30, 38, 0x20), [65]),
        ]
        for model in ('MU15', 'MU50'):
            with self.subTest(model=model):
                session = Session(model)
                for raw in [volume, part_receive_bank, native_block, native_receive_bank, *unsupported]:
                    session.receive(raw)
                expected = {volume, part_receive_bank}
                if model == 'MU50':
                    expected.add(native_block)
                self.assertEqual(set(session.export_messages()), expected)

    def test_native_only_switches_follow_the_model_tables(self):
        for model, extra in (
            ('MU90', {0x10}), ('MU90R', {0x10, 0x11}),
            ('MU100', {0x10, 0x12}), ('MU100B', {0x12}),
            ('MU100R', {0x10, 0x11, 0x12}), ('MU128', {0x10, 0x12}),
            ('MU500', {0x12}),
        ):
            with self.subTest(model=model):
                profile = PROFILES[model]
                self.assertEqual({low for low in range(0x10, 0x13)
                                  if supports_setup_write(profile, 0x49, (0, 0, low), 1)}, extra)

    def test_connection_sends_only_the_applicable_model_probe(self):
        for model in ('MU5', 'MU5K', 'MU10', 'MU15', 'MU80', 'MU500'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                engine = Engine(directory, start_worker=False)
                transport = Mock()
                engine.connection.connect(lambda connected: engine.shutdown.set() if connected else None)
                engine.submit('open',([], [1], PROFILES[model]))
                with patch('kp_mu_editor.engine.Transport', return_value=transport):
                    engine._run()
                if model in ('MU5', 'MU5K', 'MU10'):
                    transport.send.assert_not_called()
                else:
                    transport.send.assert_called_once_with(request((1, 0, 0)), 0)

    def test_mu10_worker_sends_reset_without_querying_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, start_worker=False)
            engine.connected = True
            engine.transport = transport = Mock(outputs={})
            applied = Mock()
            def completed(label, details):
                engine.shutdown.set()
                applied(label, details)
            engine.finished.connect(completed)
            engine.reset_xg(read_blocks(PROFILES['MU10']))
            with patch.object(engine, '_read') as read:
                engine._run()
                read.assert_not_called()
            transport.send.assert_called_once_with(bytes.fromhex('F0 43 10 4C 00 00 7E 00 F7'), 0)
            applied.assert_called_once_with('XG初期化', {})


if __name__ == '__main__':
    unittest.main()
