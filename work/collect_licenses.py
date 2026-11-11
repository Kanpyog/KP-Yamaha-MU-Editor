from pathlib import Path
import importlib.metadata as md
import argparse,sys,shutil,json
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--destination',type=Path,default=root/'licenses')
dest=parser.parse_args().destination
dest.mkdir(parents=True,exist_ok=True)
for name in ('LGPL-3.0.txt','QXGEdit-GPL-2.0.txt'):
    source=root/'licenses'/name
    if source.resolve()!=(dest/name).resolve():shutil.copy2(source,dest/name)
versions={}
for name in ('PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','mido','packaging','pyinstaller'):
    dist=md.distribution(name);versions[name]=dist.version
    for entry in dist.files or []:
        lower=str(entry).lower()
        if 'license' not in lower and 'copying' not in lower and 'copyright' not in lower:continue
        source=Path(dist.locate_file(entry))
        if source.is_file() and source.suffix.lower() not in ('.py','.pyc','.pyd','.dll'):
            if entry.is_absolute() or '..' in entry.parts:continue
            target=dest/name/entry
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
pythonroot=Path(sys.base_prefix)
for name in ('LICENSE.txt','LICENSE','COPYRIGHT'):
    if (pythonroot/name).is_file():shutil.copy2(pythonroot/name,dest/('Python-'+name))
(dest/'versions.json').write_text(json.dumps({'Python':sys.version,**versions},indent=2),encoding='utf-8')
print('License files',len(list(dest.rglob('*'))),'versions',versions)
