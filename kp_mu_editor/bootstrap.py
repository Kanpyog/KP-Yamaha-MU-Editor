"""Use the project interpreter regardless of the Windows file association."""
import os
from pathlib import Path
import subprocess
import sys


def preferred_python(root,executable,prefix,frozen=False):
    if frozen:return None
    env=Path(root)/'work'/'venv'
    name='pythonw.exe' if Path(executable).stem.lower()=='pythonw' else 'python.exe'
    candidate=env/'Scripts'/name
    if not candidate.is_file():return None
    if os.path.normcase(str(Path(prefix).resolve()))==os.path.normcase(str(env.resolve())):return None
    return candidate


def main():
    root=Path(__file__).resolve().parents[1]
    preferred=preferred_python(root,sys.executable,sys.prefix,getattr(sys,'frozen',False))
    if preferred:
        script=root/('run_editor.pyw' if preferred.name=='pythonw.exe' else 'run_editor.py')
        return subprocess.call([str(preferred),str(script),*sys.argv[1:]])
    from .app import main as run_application
    return run_application()
