# ソースからの起動とビルド / Build from source

[日本語](../README.md) · [English](../README_EN.md)

WindowsでPython 3.11以降のセキュリティ修正版を使います。Windows配布版はPython 3.14.10とPySide6 6.12.0でビルドしています。

Use a security-patched Python 3.11 or later on Windows. The Windows release uses Python 3.14.10 and PySide6 6.12.0.

## 起動 / Run

```powershell
python -m venv work\venv
.\work\venv\Scripts\python.exe -m pip install -r requirements.txt
.\Start_Python.cmd
```

## テストとビルド / Test and package

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\work\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
Remove-Item Env:QT_QPA_PLATFORM
.\work\venv\Scripts\python.exe -m pip install PyInstaller
.\build.ps1
```

配布用ZIPとSHA-256は `outputs/` に作成されます。Windows版ZIPは展開したフォルダー全体で動作します。ソースZIPにはビルドに必要なファイルとライセンスを含めています。

The release ZIPs and their SHA-256 hashes are written to `outputs/`. Keep the extracted Windows folder together. The source ZIP contains the build files and licenses.

音色表の再生成時は、[Yamaha MIDI資料](compatibility.md)からMU500とMU1000／MU2000のPDFを取得し、`work/MU500J.pdf` と `work/MU2000J2.pdf` として置きます。`pymupdf` を追加で導入して `work/make_catalog.py` を実行してください。通常の起動とビルドは同梱の音色表を使います。

To regenerate the catalog, obtain the MU500 and MU1000/2000 PDFs from the [Yamaha references](compatibility.md) and place them at `work/MU500J.pdf` and `work/MU2000J2.pdf`. Install `pymupdf` and run `work/make_catalog.py`. Regular use and packaging use the included catalog.
