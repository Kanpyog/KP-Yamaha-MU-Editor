# ソースからの起動とビルド

> このページはAIにより記載されました

[README](../README.md) · [English](build-en.md)

通常は [GitHub Releases](https://github.com/Kanpyog/KP-Yamaha-MU-Editor/releases) のWindows 11用ZIPを展開してEXEを起動します。ソースを変更したい場合や、自分で動作を確認したい場合は、ソースからの起動やビルドもできます。

## ソースから起動する場合

Windows x64版のPythonを用意し、ソースのルートフォルダーでPowerShellを開きます。GitHub ReleasesのWindows 11版は、Python 3.14.10とPySide6 6.12.0でビルドしています。

```powershell
python -m venv work\venv
.\work\venv\Scripts\python.exe -m pip install -r requirements.txt
.\Start_Python.cmd
```

## EXEをビルドする場合

上の手順で作成した環境にPyInstallerを追加してビルドします。

```powershell
.\work\venv\Scripts\python.exe -m pip install PyInstaller
.\build.ps1
```

ビルド後は `outputs/KP_YAMAHA_MUeditor/KP_YAMAHA_MUeditor.exe` を起動できます。`outputs/` には、EXEと実行に必要なファイルをまとめたWindows 11用ZIP、ソースコードのZIP、各ZIPのSHA-256一覧も作成されます。

テストを実行する場合は `.\work\venv\Scripts\python.exe -m unittest discover -s tests` を使います。

## 音色表の再生成

通常の起動とビルドには同梱の音色表を使います。音色表を再生成する場合に限り、ヤマハのMU500とMU1000／MU2000のPDFをそれぞれ `work/MU500J.pdf` と `work/MU2000J2.pdf` に置きます。`pymupdf` を追加し、`work/make_catalog.py` を実行します。 [ヤマハのMIDI資料](compatibility.md#ヤマハのmidi資料)
