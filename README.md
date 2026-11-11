# KP YAMAHA MU Editor

[English](README_EN.md)

YAMAHA MUシリーズの設定を、Windows 11から編集・保存するスタンドアロンMIDIエディターです。MU500を基準に開発・実機確認しています。

## 起動と接続

1. GitHubの **Releases** から Windows 11用ZIPを取得し、フォルダーごと展開します。
2. `KP_YAMAHA_MUeditor.exe` を起動し、上部で機種を選びます。
3. **接続** でMUのMIDI入出力を選び、設定の取得が完了するまで待ちます。

接続中の編集は本体に即時送信されます。現在の設定を残すには、編集前に **本体から取得** して保存してください。

## 主な機能

- パートの音色、音量、パン、フィルター、EG、エフェクトを編集
- 音色ブラウザーで名前や `Program-MSB-LSB` を検索
- ドラムのノート別設定、レイヤー、試聴鍵盤、SMF再生
- 本体設定の取得・復元、MUセット・SysEx・SMF Format 1の保存
- 日本語／英語とライト／ダークの切替

## ドキュメント

- [接続・基本操作・トラブル時の確認](docs/usage-ja.md)
- [対応機種と実機確認の範囲](docs/compatibility.md)
- [ソースからの起動とビルド](docs/build.md)
- [診断ログとセキュリティ](docs/security.md)

[GPL-3.0-or-later](LICENSE)で配布します。著作者は干瓢碁です。[第三者ライセンス](THIRD_PARTY_NOTICES.md)
