"""Golden manual addresses and consistent entrypoint interpreter selection."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kp_mu_editor.bootstrap import preferred_python,main
from kp_mu_editor.catalog import Catalog
from kp_mu_editor.schema import PROFILES
from kp_mu_editor.dependencies import midi_library


class BellCatalogTests(unittest.TestCase):
    def test_bell_search_matches_printed_program_numbers_and_has_one_chorbell(self):
        rows=[r for r in Catalog().voices(PROFILES['MU500']) if 'bell' in r['name'].casefold()]
        expected=[('Bell Pad',66,88),('TinyBell',18,98),('ChorBell',42,98),('VibeBell',68,98),
                  ('DigiBell',69,98),('AirBells',70,98),('BellHarp',71,98),('Ana Bell',74,98),
                  ('EchoBell',64,102),('TnklBell',0,112),('TcklBell',64,112),('ThaiBell',98,114)]
        self.assertEqual([(r['name'],r['lsb'],r['program']) for r in rows],expected)
        self.assertTrue(all(r['msb']==0 for r in rows))

    def test_unverified_epiano_fallback_addresses_are_not_reintroduced(self):
        rows=Catalog().voices(PROFILES['MU500'])
        self.assertFalse(any(r['source']=='QXGEdit' for r in rows))
        self.assertFalse(any(r['lsb']==18 and r['program']==3 and r['msb']==0 for r in rows))
        self.assertTrue(any(r['name']=='MelloEP1' and r['program']==4 for r in rows))


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'folder with spaces'
        self.env=self.root/'work/venv';self.scripts=self.env/'Scripts';self.scripts.mkdir(parents=True)
        for name in ('python.exe','pythonw.exe'):(self.scripts/name).touch()

    def tearDown(self):self.temp.cleanup()

    def test_global_python_selects_project_environment(self):
        self.assertEqual(preferred_python(self.root,Path('base')/'python.exe','base'),self.scripts/'python.exe')

    def test_pythonw_remains_windowless(self):
        self.assertEqual(preferred_python(self.root,Path('base')/'pythonw.exe','base'),self.scripts/'pythonw.exe')

    def test_project_environment_does_not_launch_itself_recursively(self):
        self.assertIsNone(preferred_python(self.root,self.scripts/'python.exe',self.env))

    def test_frozen_app_and_missing_environment_keep_current_interpreter(self):
        self.assertIsNone(preferred_python(self.root,Path('base')/'python.exe','base',True))
        self.assertIsNone(preferred_python(self.root/'other',Path('base')/'python.exe','base'))

    def test_relaunch_preserves_argument_boundaries_and_exit_code(self):
        preferred=self.scripts/'pythonw.exe'
        with patch('kp_mu_editor.bootstrap.preferred_python',return_value=preferred),patch('kp_mu_editor.bootstrap.subprocess.call',return_value=17) as child,patch.object(sys,'argv',['run_editor.pyw','--data-dir','a folder with spaces','--smoke']):
            self.assertEqual(main(),17)
        args=child.call_args.args[0]
        self.assertEqual(args[0],str(preferred));self.assertTrue(args[1].endswith('run_editor.pyw'))
        self.assertEqual(args[2:],['--data-dir','a folder with spaces','--smoke'])

    def test_missing_mido_reports_how_to_restart(self):
        with patch.dict(sys.modules,{'mido':None}):
            with self.assertRaisesRegex(RuntimeError,'Start_Python.cmd'):midi_library()


if __name__=='__main__':unittest.main()
