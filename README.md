# KP YAMAHA MU Editor

[English](README_EN.md)

![KP YAMAHA MU Editorの画面](images/kp_yamaha_mu_editor.jpg)

## 概要

YAMAHAのハードウェア音源「MUシリーズ」をWindows 11で操作する、スタンドアロンのMIDIエディター・コントローラーです。SC-88Pro向けのエディターソフト「Mix88」のMU版が欲しい、という発想から作成されました。

## 対象機種

| 機種 | 確認範囲 |
| --- | --- |
| MU500 | 実機確認済み・開発環境 |
| MU5、MU5K、MU10、MU15、MU50、MU80、MU90、MU90B、MU90R、MU100、MU100B、MU100Bs、MU100R、MU128、MU128 V2 | 仕様書ベース・実機未確認（注1） |
| MU1000、MU2000、各EX／EX R1 | 仕様書ベース・実機未確認（注1、注2） |

- **注1**　ハードの入手性と需要から、PLG対応機種（MU100、MU128、MU1000／MU2000系）の実機確認は予定していません。PLGのパート割り当ては、仕様書をもとに実装したVL／SG／DX用の試験機能です。PLGボードの動作は未確認、ボード内部の音色編集は非対応です。
- **注2**　MU500との差分にあたるEFX 3／4、追加のバリエーションエフェクト27種、インサーションエフェクト54種は未確認です。MU2000のサンプル編集・波形転送は非対応です。

## 動作環境

- Windows 11 64ビット（x64）。バージョン26H2で起動を確認しています。
- MU本体へのUSB接続、またはWindows 11で使えるMIDIインターフェース。USB直結の場合は、機種に対応するMIDIドライバーを使用します。
- 展開後の容量は約135 MBです。起動時のメモリ使用量は約220 MBが目安です。
- 配布版EXEの起動にPythonのインストールは不要です。

## 主な機能

- パートの音色、音量、パン、フィルター、EGの編集と、Basic／Nativeの音色マップ切り替え（対応機種）
- インサーションエフェクト、Multi EQ、ドラムのノート別設定の編集
- 音色名や `Program-MSB-LSB` での検索、レイヤー、試聴、SMF再生
- 本体設定の取得・送信、MUセット・SysEx・SMF Format 1の保存、最後に送信したSysExのコピー
- 日本語／英語とライト／ダークの切り替え

## 起動と接続

1. [GitHub Releases](https://github.com/Kanpyog/KP-Yamaha-MU-Editor/releases) からWindows 11用ZIPをダウンロードし、フォルダーごと展開します。
2. 展開したフォルダー内の `KP_YAMAHA_MUeditor.exe` を起動し、画面上部で機種を選びます。
3. **接続** でMUのMIDI入出力を選びます。自動取得が始まらない場合は **本体から取得** を選びます。

接続中の編集は本体に即時送信されます。現在の設定を残すには、編集前に本体から取得し、MUセットとして保存してください。

## ドキュメント

- [接続・基本操作・トラブル時の確認](docs/usage-ja.md)
- [対応機種と実機確認の範囲](docs/compatibility.md)
- [ソースからの起動とビルド](docs/build.md)

[GPL-3.0-or-later](LICENSE) で配布します。 [第三者ライセンス](docs/third-party-notices-ja.md)

## 開発

Kanpyog(干瓢碁)がアーキ設計、MU500での実機テスト、検証結果をもとにした修正指示を担当し、コードの実装にはOpenAI Codexを使用しました。
