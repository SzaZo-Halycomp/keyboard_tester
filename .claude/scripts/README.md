# Test scripts (no root needed)

**Run everything with one command** (allowed in `.claude/settings.json`, no permission prompt):

```
/srv/keyboardtest/.claude/scripts/run_sims.sh [output-dir]
```

It compiles `keyboardtest.py`, runs both scripts below in a 100x32 pseudo terminal, checks the expected
results and exits 0 if all is as expected (prints OK/FAIL per test and the output dir). Run it after every change.
When behaviour changes on purpose, update the expected values in `run_sims.sh` too.

Both scripts drive `keyboardtest.py` with a fake `Input` (queue of `Event`s) instead of /dev/input.

- `sim_full_run.py <report-dir>` - full run (layout check, all keys, retry, failed-key feedback, Fn steps,
  reports) with the real 840 G6 behaviour in action-keys mode ON (`ACTION` table). Has deliberate faults:
  Q sends Left Shift (tester says "yes, pressed right key"), W sends E (tester says "no"), Screen sends only Ctrl+Alt.
  Expected: 83/86, failed Screen, Q, W. Writes screen dumps `screen_layout.txt` / `screen_failed.txt` to the cwd.
- `test_scan_and_early.py` - unit checks: orphan MSC_SCAN decoding (mapped -> real key, unmapped -> SCAN_xx)
  and early press of the next key during the pause.

Keep the fake behaviour tables in sync with `notes/hardware.md` when new facts arrive.
