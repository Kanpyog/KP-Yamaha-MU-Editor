# KP YAMAHA MU Editor

[日本語](README.md)

![KP YAMAHA MU Editor screenshot](images/kp_yamaha_mu_editor.jpg)

## Overview

This is a standalone MIDI editor and controller for operating Yamaha's “MU Series” hardware sound modules on Windows 11. It was created based on the idea of developing an MU version of “Mix88,” the editor software for the SC-88Pro.

## Supported models

| Models | Verification |
| --- | --- |
| MU500 | Tested on hardware |
| MU5, MU5K, MU10, MU15, MU50, MU80, MU90, MU90B, MU90R, MU100, MU100B, MU100Bs, MU100R, MU128, MU128 V2 | Based on the documentation and untested on hardware (note 1) |
| MU1000, MU2000, and their EX and EX R1 variants | Based on the documentation, untested on hardware, and unsupported (notes 1 and 2) |

- Note 1. Due to hardware availability and demand, we do not plan to test PLG-compatible models (MU100, MU128, MU1000/MU2000 series) on actual units. The PLG part assignments are test functions for VL, SG, and DX implemented based on the specifications. The operation of the PLG board has not been verified, and editing sounds within the board is not supported.
- Note 2. The differences from the MU500 that remain unverified include EFX 3/4, 27 additional variation effects, and 54 additional insertion effects. MU2000 sample editing and waveform transfer are unsupported.

## System requirements

- Supported Versions of Windows 11 64-bit (x64)
- A USB connection to the MU unit itself, or a MIDI interface compatible with Windows 11.
- About 135 MB of disk space after extraction. Startup memory use is approximately 220 MB.

## Features

- Edit part voices, volume, pan, filters, and envelopes, and switch between the Basic and Native voice maps on supported models.
- Edit insertion effects, Multi EQ, and per-note drum settings.
- Find voices by name or `Program-MSB-LSB`, layer parts, audition sounds on the keyboard, and play SMF files.
- Read and send device settings, save MU sets, SysEx, and SMF Format 1 files, and copy the last SysEx message sent.
- Switch between Japanese and English and between light and dark themes.

## Getting started

1. Download the Windows 11 ZIP from [GitHub Releases](https://github.com/Kanpyog/KP-Yamaha-MU-Editor/releases) and extract the entire folder.
2. Start `KP_YAMAHA_MUeditor.exe` in the extracted folder and select your model at the top of the window.
3. Click **Connect** and select the MU MIDI input and outputs. If the read does not start automatically, choose **Read from device**.

Edits are sent to the MU immediately while connected. To keep a copy of the current settings, read them from the device and save them as an MU set before editing.

## Documentation

- [Connection, basic controls, and troubleshooting](docs/usage-en.md)
- [Model compatibility and hardware testing](docs/compatibility-en.md)
- [Run and build from source](docs/build-en.md)

Released under [GPL-3.0-or-later](LICENSE). [Third-party notices](THIRD_PARTY_NOTICES.md)

## Development

Kanpyog (干瓢碁) designed the architecture, tested the editor on an MU500, and directed revisions based on the results. The code was implemented using OpenAI Codex.
