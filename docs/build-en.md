# Run and build from source

[README](../README_EN.md) · [日本語](build.md)

Use a security-patched version of Python 3.11 or later on Windows. The Windows release uses Python 3.14.10 and PySide6 6.12.0.

## Run

```powershell
python -m venv work\venv
.\work\venv\Scripts\python.exe -m pip install -r requirements.txt
.\Start_Python.cmd
```

## Test and build

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\work\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
Remove-Item Env:QT_QPA_PLATFORM
.\work\venv\Scripts\python.exe -m pip install PyInstaller
.\build.ps1
```

The release ZIPs and SHA-256 checksums are written to `outputs/`. Keep the extracted Windows folder together. The source ZIP includes the files and licenses needed to build the editor.

To regenerate the voice catalog, download the MU500 and MU1000/MU2000 PDFs and save them as `work/MU500J.pdf` and `work/MU2000J2.pdf`. Install `pymupdf` and run `work/make_catalog.py`. Regular launches and builds use the included catalog. [Yamaha MIDI documentation](compatibility-en.md)
