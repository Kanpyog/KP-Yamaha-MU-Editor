# 第三者ライセンス

[README](../README.md) · [English](../THIRD_PARTY_NOTICES.md)

`kp_mu_editor/data/catalog.json` に収録している基本の音色名・ドラム音色名、一部のエフェクトパラメーター定義、変換表は、QXGEditの `src/XGParam.cpp` に由来します。

QXGEdit copyright (C) 2005-2023 Rui Nuno Capela (rncbc).

QXGEditのライセンスはGNU General Public Licenseバージョン2、または利用者が選択するそれ以降のバージョンです。本プロジェクトではバージョン3を選択しています。抽出スクリプトと使用した上流ソースファイルは、本プロジェクトの対応するソースに同梱しています。 [QXGEdit](https://github.com/rncbc/qxgedit) · [XGParam.cpp](https://github.com/rncbc/qxgedit/blob/master/src/XGParam.cpp)

その他のパラメーターアドレスや機種固有の一覧は、Yamahaが公開しているMIDI資料から独自に転記または抽出しました。Yamahaおよび各製品名は、それぞれの権利者の商標です。Yamahaのマニュアルは参照資料として使用し、配布用のアプリZIPへの収録対象外です。

実行時に使用する主なコンポーネントは、Python（PSF License）、PySide6／Shiboken6／Qt（LGPL／GPL。詳細は同梱のライセンス文書を参照）、mido（MIT License）です。PyInstallerのブートローダーには、アプリの同梱配布を認めるライセンス例外があります。

各コンポーネントのライセンス文書は `licenses/` に、ビルド時のバージョンは `licenses/versions.json` に収録しています。実行時コンポーネントは改変せずに使用しています。 [Qt for Pythonのソース](https://code.qt.io/cgit/pyside/pyside-setup.git/) · [Qtのソースと権利表示](https://code.qt.io/cgit/qt/qtbase.git/) · [Qtのソースアーカイブ](https://download.qt.io/archive/qt/) · [Pythonのソース](https://www.python.org/downloads/source/) · [midoのソース](https://github.com/mido/mido)

アプリの対応するソースはソースZIPに収録しています。Qtの共有DLLは `_internal` から動的に読み込まれ、置き換え可能です。
