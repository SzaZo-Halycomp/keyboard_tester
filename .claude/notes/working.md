# How it works / how to work here

## Files
- `keyboardtest.py` - the program (single file, stdlib only).
- `templates/*.json` - one per keyboard (model + layout), picked by matching `match` strings against
  `/sys/class/dmi/id/product_name` (`--template FILE` / `--layout` override).
- `reports/` - output. `.claude/scripts/` - simulations.

## Test flow
start screen (beep check) -> layout check (tester confirms on-screen map) -> key test (beep, 5 s/key) ->
retry failed keys -> tester feedback per failed key ("did you press the right key?") ->
Fn/action keys (keyboard released, tester confirms) -> reports.
Emergency exit: Esc 3x within 1.5 s. CLI: `--learn`, `--monitor`, `--list`, `--timeout N`, `--no-fn`,
`--no-retry`, `--include-usb`, `--device X`, `--beep auto|sound|pcspkr|bell|off`.

## Code map (keyboardtest.py)
- Input layer: `scan_devices` (parses /proc/bus/input/devices), `is_keyboard_like`, `Device.read`
  (EV_KEY + MSC_SCAN; an MSC_SCAN without EV_KEY = "orphan": resolved with EVIOCGKEYCODE to the real key,
  or pseudo code `SCAN_xx` = SCAN_BASE+scancode if unmapped), `Input` (select over devices, Esc-abort, keystroke log).
- `Beeper` - sound via pw-play/paplay/aplay run as SUDO_USER (root can't reach the desktop audio session),
  fallback PC speaker (EV_SND) then terminal bell.
- `UI` - curses screens + keyboard map. `test_one_key`, `run_keys` (with early-press via `gap`),
  `run_retry_phase`, `ask_failed_keys`, `run_fn_phase`/`run_fn_step`, `summary`, `write_*` reports, `learn`.

## Template format
- `rows`: rows of keys `{label, name?, codes:[KEY_*|SCAN_xx], w, x?, test?, hint?, combo?, accept_scan?,
  silent_in_action_mode?, mode_probe?, mirror_of?}`. `w`/`x` in key units (map drawing).
  `label` = short text on the map; `name` = full text in prompts ("Right Shift", not "Shift R": the user once read
  "Shift R" as Shift+R).
- Codes are evdev names by physical position (HU: `Z` = `KEY_Y`, `Y` = `KEY_Z`, `Í` = `KEY_102ND`, `0` = `KEY_GRAVE`).
- F-keys list the plain code + the action code. `mode_probe` (F1) detects the action-keys mode at runtime;
  `silent_in_action_mode` keys are then asked as "Fn + Fx".
- Macro keys send modifiers too: modifiers are ignored for non-modifier keys. `combo` = modifier set that alone
  counts as the key (fallback when the scancode is unknown); `accept_scan` = any unmapped SCAN_xx not used by another key.
- `mirror_of`: display-only part of a key (ISO Enter lower half). Fn alone is invisible to the OS: `test: false`.
- `fn_tests`: `{fkey|keys, mode: confirm|signal, see, codes|codes_action|codes_plain}`; `fkey` becomes
  "F3" or "Fn + F3" by the detected mode.

## Reports
- Results per key: status (PASS/TIMEOUT/WRONG/STUCK), received code, wrong presses, attempts history,
  `events` (keylog lines for that prompt), `early`, `user_pressed_right_key`.
- Keylog columns: t, time, event (down/up), key, code, scan, device, phase, asked, orphan, dropped.
  Analyse with grep on the CSV: `phase` main/main-gap/retry/fn/confirm-failed, `asked` = key being asked.

## Testing
- No root here: run `.claude/scripts/` simulations (fake Input driven from `UI.render` inside `script` for a pty).
  Always run `.claude/scripts/run_sims.sh` after a change (exit 0 = OK); extend the sims for new behaviour.
- The real test is run by the user; then read the newest `reports/*.txt` + `*.keylog.csv`.

## Gotchas
- `!` commands in Claude Code have no TTY: sudo can't ask a password and curses can't draw.
- Grabbing while a key is held leaves the OS with a stuck key: `grab_all`/`ungrab_all` wait for release.
- When ungrabbed, the kernel sometimes sends only MSC_SCAN for a release (its key state was out of sync);
  handled by the orphan resolution in `Device._flush_scan`.
- No `/dev/input/event*` = the `evdev` module isn't loaded (minimal/live systems). `ensure_input_modules()` loads
  evdev (+ hp_wmi on HP) as root; if `/lib/modules/$(uname -r)` is missing it reports a kernel/modules mismatch
  (seen on a network-booted live image whose boot menu served an older kernel).
- HP action-keys mode can flip between runs (Fn lock = Fn + Left Shift).
