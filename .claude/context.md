# Context: Keyboard tester (one-page summary)

Last updated: 2026-11-05. Details: `notes/working.md` (how it works), `notes/hardware.md` (model facts).

## What it is

`keyboardtest.py` (v1.4.2) tests a laptop keyboard key by key on Linux, for refurbishing/service use.
- Grabs the keyboard devices exclusively (EVIOCGRAB) so the OS doesn't react, shows the key to press on a
  curses screen with an on-screen keyboard map, beeps, and waits 5 s.
- Then releases the keyboard and tests Fn/action keys (brightness, volume, mute…): the tester confirms what happened.
- Writes `reports/<serial>_<model>_<time>.{txt,json,html,keylog.csv}`; the keylog has every key event.

Run: `sudo python3 /srv/keyboardtest/keyboardtest.py` in a real terminal (not via `!`).

## Where it stands

- **Released:** v1.4.2 (latest) and v1.4.1 on github.com/SzaZo-Halycomp/keyboard_tester (public, MIT).
  v1.4 release + tag were deleted at the user's request.
- **Template done and verified:** HP EliteBook 840 G5/G6, Hungarian ISO
  (`templates/hp_elitebook_840_g5_g6_hu.json`). The user's 840 G6 passed 86/86 keys on 2026-11-04.
- **Features:** layout check, beep on prompt + low tone on fail, retry of failed keys, tester feedback per failed key,
  early-press acceptance, action-keys mode auto-detect, macro-key and unmapped-scancode support, learn and monitor modes.
- **Reports in `reports/`:** the 15:40–15:45 runs were made with the old v1.0 layout (kept for its F-key data);
  the 16:26 run is the first good one. The user deleted two runs full of tester mistakes.

## Next steps / open items

1. Check on the next real run: the beep is audible under sudo (`sound` method runs pw-play as SUDO_USER).
2. Fn + Right Shift = Print Screen? Unverified (the user pressed R last time due to an unclear label, now fixed).
3. F12 (calendar) code in action-keys mode ON: sends Ctrl+Alt + an unknown scancode, capture it from a keylog.
4. The network-booted 840 G5 test machine had a kernel/modules mismatch (evdev couldn't load); the user fixed the
   boot server on 2026-11-05. Next: a real run on the G5 to verify the shared template.
5. More models/layouts when the user asks (start from a photo + one `--monitor`/test run).
