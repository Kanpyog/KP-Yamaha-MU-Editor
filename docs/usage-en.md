# Connection, basic controls, and troubleshooting

> This page was written by AI.

[README](../README_EN.md) · [日本語](usage-ja.md)

## Connect the MU

Connect the unit by USB or MIDI and select your model at the top of the window. Open **Connect** and choose the **Input from device** and the outputs for the sound engine. Reading settings requires an input from the device.

For a direct USB connection to the MU500, set its **HOST SELECT** switch to **USB**. Assign USB outputs 1–4 to outputs A–D in the editor to access all 64 parts. USB ports 5–8 can route to an external sound module through MIDI OUT using the Thru Port setting. [Yamaha USB-MIDI driver](https://usa.yamaha.com/support/updates/usb-midi-driver-win.html)

## Read from the device

Choose **Read from device**, then select all settings, effects only, or drum map only. The editor requests each block once and reports the number of unread blocks when it finishes. Unread settings keep their previous or initial values.

## Voices and parts

- Select a part in the mixer and double-click a voice in the browser. Search by name or an identifier such as `99-0-42`. Program numbers on screen run from 1 to 128.
- On the MU500 in TG300B mode, you can also select variation voices and drum kits. Parts that use the same Drum Setup share the kit and per-note settings.
- Drag numeric fields up or down, double-click them, or type a value. Values that differ from their initial settings appear in bold green.
- Use the keyboard at the bottom to audition sounds. Lower the octave to reach lower drum notes. Use **ALL NOTES OFF** to release sounding notes.

## Save and send settings

Use **Save** to export an MU set (JSON) or an SMF Format 1 file. Use the **Library** to import and export SysEx. Data read from the device is also saved in `userdata/backups/`.

SMF export and **Send to device** offer the same scopes as device reads. Effects include assignments, send levels, and EQ. Drum maps contain per-note settings for each Drum Setup. Both partial scopes preserve voice and drum kit selections when exporting or sending. In a sequencer, place the drum map SysEx after the Program Change that selects the kit.

Open the saved MU set, connect to the unit, then choose **Send to device**. A bulk send first reads and backs up the device settings, then reads back the settings sent in bulk to verify them.

After confirmation, **XG RESET** backs up the settings held on the PC, returns the unit to its XG initial state, and reads the settings again. To keep changes made on the device, read and save them before resetting.

## Play MIDI files

Use **MIDI file** at the bottom to select an SMF Format 0 or 1 file and play it through the connected MU. Enable **Use song voices/settings** to send supported Bank Select, Program Change, and setup SysEx messages as well. A song containing an initialization message may change device settings.

## Display and troubleshooting

On first launch, the editor uses Japanese and the dark theme. Change the language under **編集 (Edit) → 環境設定 (Preferences) → Language**. Use the top bar to switch themes.

- **The MU is missing from the port list** — Check the power, connection, and MIDI driver.
- **Some settings are unread** — Check the model, MIDI inputs and outputs, and Device Number, then read the required settings again. Open **MIDI Log** from the top bar to check MIDI traffic.
