# Connection and controls

[README](../README_EN.md) · [日本語ガイド](usage-ja.md)

## Connect the MU

Set up your USB or MIDI connection, select the MU model, and open **Connect**. Select the input from the unit and assign its sound engine outputs to A–D. On the MU500 USB connection, outputs 1–4 address the internal sound engine. Outputs 5–8 route to MIDI OUT.

Use **Read from device** to get the current settings. Unread values are shown using initial values as a reference. If the read reports missing blocks, check the ports and read again.

## Edit and audition

- Select a part in the mixer and double-click a voice in the browser. Search by name or an identifier such as `99-0-42`. Program numbers on screen are 1–128.
- Drag numeric fields up or down, double-click them, or type a value. Bold green values differ from their initial settings.
- Edit model-specific settings on the Part, Drums and Effects pages. Parts that use the same Drum Setup share per-note changes.
- Use the audition keyboard and its octave control to reach lower drum notes. **ALL NOTES OFF** releases sounding notes.

## Save and restore

Device reads are backed up under `userdata/backups/`. Use **Save** for JSON sets or SMF Format 1. The Library handles SysEx import and export.

Opening a set loads it on the PC. Choose **Send to device** to apply it. A bulk send first backs up the current device state, then verifies bulk blocks by reading them back.

**XG RESET** confirms the action, backs up the settings currently held on the PC, resets the unit to its XG initial state and reads it again. Read and save any changes made on the hardware before resetting.

## Play MIDI files

Select an SMF Format 0 or 1 file and play it through the connected MU. **Use song voices/settings** also sends supported bank, program and setup messages. A song with a GM, GM2 or XG reset may change device settings.

## Display and troubleshooting

On first launch, the menus are in Japanese. To switch to English, open **編集 → 環境設定 → Language** and select **英語（Eng）**. The top bar switches between light and dark modes.

If a device read is slow or the connection drops, check the model and MIDI port assignments. Open **MIDI Log** from the top bar to check MIDI traffic.

### Submit a log

If you are asked for a log to help troubleshoot a problem, choose **Edit → Preferences → Diagnostics → Export diagnostic logs**. Share the ZIP and the time the problem occurred. [Stored data and sharing](security-en.md)
