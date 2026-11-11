"""Build release archives from application assets and public source files."""
import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kp_mu_editor import __version__ as VERSION

APP_DOCS = (
    'README.md', 'README_EN.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'docs/build.md', 'docs/build-en.md', 'docs/compatibility.md', 'docs/compatibility-en.md',
    'docs/security.md', 'docs/security-en.md', 'docs/usage-ja.md', 'docs/usage-en.md',
    'docs/third-party-notices-ja.md', 'images/kp_yamaha_mu_editor.jpg',
)
PUBLIC_FILES = (
    *APP_DOCS, '.gitignore', 'Start_Python.cmd', 'build.ps1', 'requirements.txt', 'run_editor.py', 'run_editor.pyw',
    'third_party/qxgedit/XGParam.cpp', 'work/collect_licenses.py', 'work/package_release.py',
    'work/make_catalog.py', 'work/voice_table.py',
)
APP_DATA = (
    'catalog.json', 'i18n_en.json', 'mu500_defaults.json',
    'check.svg', 'check_lcd.svg', 'down.svg', 'down_dark.svg', 'up.svg', 'up_dark.svg',
)
PRIVATE_DIRS = {'userdata', 'logs', 'diagnostics', 'backups', 'sessions', '__pycache__', '.git'}


def checked_file(path, base):
    if (not path.is_file() or path.resolve() != path.absolute()
            or not path.resolve().is_relative_to(base.resolve())
            or PRIVATE_DIRS.intersection(part.lower() for part in path.relative_to(base).parts)):
        raise ValueError(f'Unexpected release file: {path.name}')
    return path


def source_files(root):
    files = [root / name for name in PUBLIC_FILES]
    files.extend((root / 'kp_mu_editor').glob('*.py'))
    files.extend(root / 'kp_mu_editor' / 'data' / name for name in APP_DATA)
    files.extend((root / 'tests').glob('test_*.py'))
    return sorted(checked_file(path, root) for path in files)


def tree_files(base):
    return sorted(checked_file(path, base) for path in base.rglob('*') if path.is_file())


def archive(path, entries):
    with NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as file:
        temporary = Path(file.name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for source, name in entries:
                bundle.write(source, name)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir', required=True, type=Path, help='fresh PyInstaller application folder')
    args = parser.parse_args()
    app = args.app_dir.resolve(strict=True)
    out = ROOT / 'outputs'
    out.mkdir(exist_ok=True)
    prefix = 'KP_YAMAHA_MUeditor'
    appzip = out / f'{prefix}_v{VERSION}_Windows11.zip'
    sourcezip = out / f'{prefix}_v{VERSION}_source.zip'

    runtime = [checked_file(app / name, app) for name in ('KP_YAMAHA_MUeditor.exe', *APP_DOCS)]
    runtime.extend(tree_files(app / '_internal'))
    data_dir = app / '_internal' / 'kp_mu_editor' / 'data'
    if set(path.relative_to(data_dir).as_posix() for path in tree_files(data_dir)) != set(APP_DATA):
        raise ValueError('Unexpected bundled application data')
    licenses = tree_files(app / 'licenses')
    archive(appzip, [(path, f'{prefix}/{path.relative_to(app).as_posix()}')
                    for path in (*runtime, *licenses)])
    source = [(path, f'{prefix}_source/{path.relative_to(ROOT).as_posix()}')
              for path in source_files(ROOT)]
    source.extend((path, f'{prefix}_source/{path.relative_to(app).as_posix()}') for path in licenses)
    archive(sourcezip, source)

    hashes = {}
    for path in (appzip, sourcezip):
        with path.open('rb') as file:
            hashes[path.name] = hashlib.file_digest(file, 'sha256').hexdigest()
    (out / 'SHA256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(hashes, indent=2))


if __name__ == '__main__':
    main()
