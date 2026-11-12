# Run and build from source

> This page was written by AI.

[README](../README_EN.md) · [日本語](build.md)

For regular use, extract the Windows 11 ZIP from [GitHub Releases](https://github.com/Kanpyog/KP-Yamaha-MU-Editor/releases) and run the EXE. You can also run or build from source to modify the editor or test it yourself.

## Run from source

Install Python for Windows x64 and open PowerShell in the source root. The Windows 11 version on GitHub Releases is built with Python 3.14.10 and PySide6 6.12.0.

```powershell
python -m venv work\venv
.\work\venv\Scripts\python.exe -m pip install -r requirements.txt
.\Start_Python.cmd
```

## Build the EXE

Install PyInstaller in the environment created above and run the build script.

```powershell
.\work\venv\Scripts\python.exe -m pip install PyInstaller
.\build.ps1
```

After building, you can run `outputs/KP_YAMAHA_MUeditor/KP_YAMAHA_MUeditor.exe`. The build also writes a Windows 11 ZIP containing the EXE and the files it needs, a source code ZIP, and SHA-256 checksums for both archives to `outputs/`.

To run the tests, use `.\work\venv\Scripts\python.exe -m unittest discover -s tests`.

## Regenerate the voice catalog

Regular launches and builds use the bundled voice catalog. To regenerate the catalog, save the Yamaha MU500 and MU1000/MU2000 PDFs as `work/MU500J.pdf` and `work/MU2000J2.pdf`, respectively. Install `pymupdf` and run `work/make_catalog.py`. [Yamaha MIDI documentation](compatibility-en.md#yamaha-midi-documentation)
