# Keyboard tester (/srv/keyboardtest)

Linux laptop keyboard tester: asks every key with a beep + 5 s countdown while the keyboard
is grabbed, then Fn/action keys, then writes TXT/JSON/HTML/keylog reports. Read these before you continue:

- `.claude/context.md`: one-page summary (what it is, where it stands, next steps). Start here.
- `.claude/notes/working.md`: how it works and how to work here: flow, template format, code map, testing, gotchas.
- `.claude/notes/hardware.md`: verified facts per laptop model (key codes, scancodes, quirks).
- `.claude/scripts/README.md`: simulation / test scripts. Reuse and extend them; don't write ad-hoc ones.

## Hard rules (never break these)

- **`keyboardtest.py` stays one file, Python stdlib only** (no python-evdev, no pip). It must run on a minimal live USB.
- **Templates come from evidence, not guesses.** Real reports/keylogs, photos of the keyboard, `--monitor`/`--learn` output.
  When something is a guess, mark it as unverified in the template `notes` and in `notes/hardware.md`.
- **Never release the grab while keys are held** (`Input.wait_release`), and always ungrab on exit/abort.
- **Reports in `reports/` are the user's test data.** Don't delete or edit them unasked; the user decides which runs are bad.
- I can't read `/dev/input` (not root, no sudo password). Test with the fake-input simulations in `.claude/scripts/`,
  and let the user run the real test in a separate terminal (`!` commands can't do sudo or curses).
- `.claude/settings.json` (permission allowlist) only changes when the user explicitly asks for it.
- **The GitHub repo is public** (github.com/SzaZo-Halycomp/keyboard_tester). Never commit reports, serial numbers,
  hostnames, internal IPs or passwords. Commit as `SzaZo-Halycomp <84787263+SzaZo-Halycomp@users.noreply.github.com>`
  (repo-local git config); never put the user's private e-mail in commits or send it to outside services.
- Commit/push/release only when the user asks. Releases: annotated tag `vX.Y.Z` = `VERSION` in `keyboardtest.py`.

## How the user works

- Plans first, then builds step by step; tests on the real laptop and asks me to read the newest report.
- Wants the software improved from the data: analyse the keylog (`*.keylog.csv`), separate tester mistakes from
  real faults and from template/software errors, then fix the template/code.
- Talk to the user in English, short and concrete. After a change, say what to try on the next run.
