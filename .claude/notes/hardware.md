# Verified hardware facts

## HP EliteBook 840 G6 (the user's unit, BIOS R70 01.35.02) - Hungarian ISO
Sources: real test runs 2026-11-04 (reports/), photo https://laptopozz.hu/termek/hp-elitebook-840-g6/
(that photo shows a US-physical / HU-legend board; the user's board is ISO: has Í = KEY_102ND).

- Input devices: "AT Translated Set 2 keyboard" (i8042), "HP WMI hotkeys", "Video Bus".
- Layout: top row Esc, F1-F12, Screen (monitor icon), Call, Hangup, Delete; right column Home/PgUp/PgDn/End;
  bottom row Ctrl, Fn, Win, Alt, Space, AltGr, Menu, Ctrl, Left, Up/Down (half height), Right.
  Fn lock printed on Left Shift, prt scr on Right Shift, num lock on F10.

| Key | Action mode ON (no Fn) | Action mode OFF (no Fn) | Fn + key (mode OFF) |
|---|---|---|---|
| F1 display | KEY_SWITCHVIDEOMODE | KEY_F1 (scan 0x3b) | KEY_SWITCHVIDEOMODE |
| F2 (blank) | KEY_F2 | KEY_F2 | - |
| F3 / F4 | BRIGHTNESSDOWN / UP | F3 / F4 | BRIGHTNESSDOWN / UP |
| F5 mute | KEY_MUTE | F5 | KEY_MUTE |
| F6 / F7 | VOLUMEDOWN / UP | F6 / F7 | VOLUMEDOWN / UP |
| F8 mic mute | KEY_MICMUTE | F8 | KEY_MICMUTE |
| F9 (blank) | nothing | KEY_F9 (scan 0x43) | ? |
| F10 num lock | KEY_NUMLOCK | F10 | ? |
| F11 airplane | nothing | KEY_F11 | SCAN_f8 (unmapped) |
| F12 calendar | Ctrl+Alt + unknown | KEY_F12 (scan 0x58) | ? |

- Screen key: Ctrl+Alt + SCAN_6d (unmapped). Call: Alt + KEY_PICKUP_PHONE (scan 0x66) + Meta.
  Hangup: Ctrl+Alt + KEY_HANGUP_PHONE (scan 0x65).
- Unverified: Fn + Right Shift = Print Screen; F12 scancode in action mode ON.

## HP EliteBook 840 G5
Assumed same keyboard as G6 (same template) - not tested on a real G5 yet.
