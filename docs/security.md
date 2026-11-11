# 診断ログとセキュリティ / Diagnostics and security

[日本語](../README.md) · [English](../README_EN.md)

## 設定とログ / Settings and logs

個人の設定・保存セット・取得バックアップ・MIDIログは `userdata/` に保存します。配布用のソースZIPとWindows版ZIPは、公開用に指定したファイルから作成します。

Preferences, saved sets, device backups and MIDI logs are stored in `userdata/`. The source and Windows ZIPs are assembled from files selected for distribution.

診断ZIPにはPC内のパス、MIDIポート名、ドライバー情報、送受信したMIDIデータが含まれる場合があります。公開のIssueなどへ添付する前に内容を確認してください。

Diagnostic ZIPs may include local paths, MIDI port names, driver details and MIDI data. Review their contents before attaching them to a public issue.

## 入力の検証 / Input validation

- MUセット・SysEx・SMFには読込上限があり、形式やメッセージ長を検証します。
- 設定の書き出しと一括送信は、対応する設定領域を対象にします。曲の設定を反映するSMF再生では、GM／GM2／XGの初期化メッセージも扱います。
- 診断の書き出しは所定のログフォルダー内の通常ファイルを対象にします。

- File loads enforce size and structural checks for MU sets, SysEx and SMF.
- Set export and bulk send use supported setup regions. SMF playback with song settings enabled also supports standard GM, GM2 and XG reset messages.
- Diagnostic exports collect regular files from the designated log folders.

Windows版1.2.1の同梱環境はPython 3.14.10、PySide6／Qt 6.12.0です。公開情報は各プロジェクトの案内を参照してください。[Python 3.14.10](https://www.python.org/downloads/release/python-31410/) · [Qtのセキュリティ情報](https://wiki.qt.io/List_of_known_vulnerabilities_in_Qt_products)
