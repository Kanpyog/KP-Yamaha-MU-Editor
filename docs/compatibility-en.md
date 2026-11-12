# Model compatibility and hardware testing

[README](../README_EN.md) · [日本語](compatibility.md)

| Models | Verification |
| --- | --- |
| MU500 | Tested on hardware |
| MU5, MU5K, MU10, MU15, MU50, MU80, MU90, MU90B, MU90R, MU100, MU100B, MU100Bs, MU100R, MU128, MU128 V2 | Based on the documentation and untested on hardware (note 1) |
| MU1000, MU2000, and their EX and EX R1 variants | Based on the documentation, untested on hardware, and unsupported (notes 1 and 2) |

- Note 1. Hardware testing of PLG-capable models (the MU100, MU128, MU1000, and MU2000 families) is unscheduled due to availability and demand. PLG part assignment for VL, SG, and DX boards is experimental and based on the documentation. Board operation is untested, and editing the boards' internal voices is outside the scope of the editor.
- Note 2. The differences from the MU500 that remain unverified include EFX 3/4, 27 additional variation effects, and 54 additional insertion effects. MU2000 sample editing and waveform transfer are unsupported.

The MU5 family uses its own MIDI format. The editor focuses on XG. Part counts, voice maps, effects, and A/D inputs vary by model and operating mode.

## Yamaha MIDI documentation

- [MU500](https://data.yamaha.com/files/download/other_assets/8/316818/MU500J.PDF)
- [MU1000 / MU2000](https://data.yamaha.com/files/download/other_assets/2/316512/MU2000J2.pdf)
- [MU5](https://data.yamaha.com/files/download/other_assets/6/318376/MU5S.pdf)
- [MU50](https://data.yamaha.com/files/download/other_assets/2/318072/MU50E2.pdf)
- [MU80](https://data.yamaha.com/files/download/other_assets/5/317065/MU80F2.pdf)
- [MU90 / MU90R](https://data.yamaha.com/files/download/other_assets/8/316488/MU90RJ1.pdf)
- [MU100B](https://data.yamaha.com/files/download/other_assets/1/316751/MU100BJ.pdf)
- [MU128](https://data.yamaha.com/files/download/other_assets/2/316732/MU128J2.pdf)
