# KP YAMAHA MU Editor

[日本語](README.md)

A standalone MIDI editor for Yamaha MU tone generators on Windows 11. It edits and saves hardware settings and is developed and tested with the MU500.

## Quick start

1. Download the Windows 11 ZIP from **Releases** and extract the entire folder.
2. Start `KP_YAMAHA_MUeditor.exe` and select your model.
3. Choose the MU MIDI input and outputs under **Connect**, then wait for the settings read to finish.

Edits are sent to the device immediately while connected. To keep a copy of the current state, use **Read from device** and save it before editing.

For English, open **編集 → 環境設定 → Language**, then choose **英語（Eng）**.

## Features

- Edit part voices, levels, pan, filters, envelopes and effects
- Find voices by name or `Program-MSB-LSB`
- Per-note drum editing, layers, audition keyboard and SMF playback
- Read and restore device settings, and export MU sets, SysEx or SMF Format 1
- Japanese and English UI with light and dark themes

## Documentation

- [Connection, controls and troubleshooting](docs/usage-en.md)
- [Model compatibility and hardware testing](docs/compatibility.md)
- [Run from source and build](docs/build.md)
- [Diagnostic logs and security](docs/security.md)

Released under [GPL-3.0-or-later](LICENSE) by 干瓢碁. [Third-party notices](THIRD_PARTY_NOTICES.md)
