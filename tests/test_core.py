import json,tempfile,unittest
from pathlib import Path
from kp_mu_editor import protocol as p
from kp_mu_editor.schema import PROFILES,PART_BY_KEY,part_params,DRUM,read_blocks
from kp_mu_editor.session import Session
from kp_mu_editor.engine import load_midi,write_midi
from kp_mu_editor.catalog import Catalog


class ProtocolTests(unittest.TestCase):
    def test_documented_xg_message(self):
        self.assertEqual(p.change((8,0,0x4d),[0x42]).hex(),'f043104c08004d42f7')

    def test_documented_request(self):
        self.assertEqual(p.request((8,63,0x30)).hex(),'f043204c083f30f7')

    def test_bulk_capture_checksum(self):
        raw=bytes.fromhex('f0 43 00 4c 00 07 00 00 00 00 04 00 00 7f 00 40 36 f7')
        packet=p.parse(raw);self.assertEqual(packet.address,(0,0,0));self.assertEqual(packet.data,bytes([0,4,0,0,127,0,64]))
        self.assertEqual(p.bulk(packet.address,packet.data),raw)

    def test_corruption_rejected(self):
        raw=bytearray(p.bulk((8,0,0),[1,2,3]));raw[-2]^=1
        with self.assertRaises(ValueError):p.parse(raw)

    def test_truncated_bulk_rejected(self):
        raw=p.bulk((8,0,0),[1,2,3]);raw=raw[:9]+raw[10:]
        with self.assertRaises(ValueError):p.parse(raw)

    def test_invalid_data(self):
        for val in (-1,128,256):
            with self.assertRaises(ValueError):p.change((8,0,0),[val])

    def test_nibble_signed_center(self):
        self.assertEqual(p.encode(128,2,True),bytes([8,0]));self.assertEqual(p.decode(bytes([8,1]),True),129)

    def test_14bit_delay(self):
        self.assertEqual(p.encode(14860,2),bytes([116,12]));self.assertEqual(p.decode(bytes([116,12])),14860)

    def test_mu5_checksum(self):
        raw=p.change((2,0,5),[90],model=0x44);self.assertEqual(sum(raw[4:-1])&127,0)
        self.assertEqual(p.parse(raw).data,b'Z')

    def test_mu5_request_has_count_and_checksum(self):
        raw=p.request((2,1,0),model=0x44)
        self.assertEqual(raw[:4],bytes.fromhex('F0 43 30 44'))
        self.assertEqual(raw[7:10],bytes([0,0,22]));self.assertEqual(sum(raw[4:-1])&127,0)

    def test_mu5_part10_is_block0(self):
        params={x.key:x for x in part_params(PROFILES['MU5'])}
        self.assertEqual(params['volume'].address(0),(2,1,5))
        self.assertEqual(params['volume'].address(9),(2,0,5))

    def test_sysex_split(self):
        first=p.change((8,0,0xb),[95]);second=p.change((8,1,0xb),[100])
        self.assertEqual(p.split_sysex(first+b'\xf8'+second),[first,second])
        with self.assertRaises(ValueError):p.split_sysex(first[:-1])

    def test_rpn_clear(self):
        messages=p.rpn(3,0,0,12)
        self.assertEqual(messages[-2:], [bytes([0xb3,101,127]),bytes([0xb3,100,127])])


class SessionTests(unittest.TestCase):
    def test_unknown_is_not_a_read_value(self):
        s=Session();param=PART_BY_KEY['volume'];self.assertEqual(s.get(param),100)
        self.assertTrue(s.origin(param).startswith('未取得'));self.assertEqual(s.export_messages(),[])

    def test_only_edited_field_exported(self):
        s=Session();s.set(PART_BY_KEY['volume'],90,63)
        self.assertEqual(s.export_messages(),[p.change((8,63,11),[90])])

    def test_multibyte_field_survives_save(self):
        from kp_mu_editor.schema import Param
        s=Session();s.set(Param('type','type',0,high=3,size=2,maximum=16383,default=0),640,1)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'a.mu.json';s.save(path);other=Session.load(path)
        self.assertEqual(other.export_messages(),[p.change((3,1,0),p.encode(640,2))])

    def test_parts_precede_drums(self):
        s=Session();s.receive(p.bulk((0x30,38,0),bytes([64]*16)));s.receive(p.bulk((8,9,0),bytes([0]*41)))
        messages=s.export_messages();self.assertEqual(p.parse(messages[0]).address,(8,9,0));self.assertEqual(p.parse(messages[-1]).address,(0x30,38,0))

    def test_import_transaction(self):
        s=Session();s.set(PART_BY_KEY['volume'],90)
        before=dict(s.memory)
        with self.assertRaises(ValueError):s.import_sysex(p.change((8,0,11),[80])+b'\xf0\xf7')
        self.assertEqual(s.memory,before)

    def test_import_no_reset(self):
        with self.assertRaises(ValueError):Session().import_sysex(p.change((0,0,0x7e),[0]))

    def test_undo_redo(self):
        s=Session();param=PART_BY_KEY['volume'];s.receive(p.bulk((8,0,0x0b),[100]));s.checkpoint('Volume');s.set(param,90)
        s.restore_history();self.assertEqual(s.get(param),100);s.restore_history(True);self.assertEqual(s.get(param),90)

    def test_reject_invalid_load(self):
        obj=Session().to_dict();obj['memory']=[[76,8,0,11,999]]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.mu.json';path.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):Session.load(path)

    def test_roundtrip_all_models(self):
        for profile in PROFILES.values():
            s=Session(profile.name)
            for param in part_params(profile):
                if param.minimum<=param.default<=param.maximum:s.set(param,param.default)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'set.mu.json';s.save(path);other=Session.load(path)
            self.assertEqual(s.memory,other.memory,profile.name)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=Catalog()

    def test_capital_voices(self):
        for model in ('MU5','MU50','MU80','MU100','MU128','MU500','MU2000'):
            voices=self.catalog.voices(PROFILES[model]);programs={v['program'] for v in voices if not v['msb'] and not v['lsb']}
            self.assertEqual(programs,set(range(128)),model)

    def test_no_duplicate_addresses(self):
        rows=self.catalog.voices(PROFILES['MU500']);keys=[(v['msb'],v['lsb'],v['program']) for v in rows]
        self.assertEqual(len(keys),len(set(keys)))

    def test_mu500_effect_counts(self):
        self.assertEqual(len(self.catalog.effects(PROFILES['MU500'],'reverb')),19)
        self.assertEqual(len(self.catalog.effects(PROFILES['MU500'],'chorus')),21)
        self.assertEqual(len(self.catalog.effects(PROFILES['MU500'],'insertion')),44)

    def test_delay_limits(self):
        fx=next(x for x in self.catalog.effects(PROFILES['MU500'],'variation') if (x['msb'],x['lsb'])==(5,0))
        var=self.catalog.effect_params(fx,'variation');ins=self.catalog.effect_params(fx,'insertion')
        self.assertEqual(var[0]['maximum'],14860);self.assertEqual(ins[0]['maximum'],7429)

    def test_schema_addresses_no_overlap(self):
        for profile in PROFILES.values():
            addresses=set()
            for param in part_params(profile):
                for low in range(param.low,param.low+param.size):
                    key=(param.model,param.high,low);self.assertNotIn(key,addresses,(profile.name,param.key));addresses.add(key)


class MidiFileTests(unittest.TestCase):
    def test_setup_export(self):
        raw=p.change((8,0,11),[90])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'setup.mid';write_midi(path,[raw]);events=load_midi(path,True)
        self.assertEqual(events[0][3],raw)

    def test_track_ports_are_not_global(self):
        import mido
        file=mido.MidiFile(type=1)
        for port,note in ((0,60),(1,64)):
            track=mido.MidiTrack();file.tracks.append(track)
            track.append(mido.MetaMessage('midi_port',port=port));track.append(mido.Message('note_on',note=note,time=0));track.append(mido.Message('note_off',note=note,time=480))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ports.mid';file.save(path);events=load_midi(path)
        self.assertEqual([(x[2],x[3][1]) for x in events[:2]],[(0,60),(1,64)])

    def test_edit_priority_strips_program_changes(self):
        import mido
        file=mido.MidiFile(type=0);track=mido.MidiTrack();file.tracks.append(track)
        track.extend([mido.Message('program_change',program=5),mido.Message('note_on',note=60)])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'a.mid';file.save(path);events=load_midi(path,False)
        self.assertEqual(len(events),1);self.assertEqual(events[0][3][0],0x90)

if __name__=='__main__':unittest.main()
