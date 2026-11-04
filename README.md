# keyboard_tester

Laptop keyboard tester for Linux. It asks for every key one by one, with a beep and a countdown,
while it holds the keyboard exclusively so the system doesn't react to the presses. Then it tests the
Fn / action keys (brightness, volume, mute, ...) and writes a report.

- Single file, **Python 3 standard library only**: it also runs on a minimal live USB system.
- Reads the keyboard directly from `/dev/input` and grabs it (`EVIOCGRAB`) for the duration of the key test.
- Templates per laptop model and layout, picked automatically from the DMI model name.

## Usage

Run it in a real terminal (it needs root to grab the keyboard and to read the serial number):

```
sudo python3 keyboardtest.py
```

1. **Layout check:** confirm that the keyboard drawn on screen matches the laptop.
2. **Key test:** on each beep press the key shown (5 s per key). A low tone means the key failed.
   Failed keys can be retried, then you are asked for each failed key whether you really pressed it.
3. **Fn / action keys:** the keyboard is released so the system reacts; press the combination shown and
   confirm what happened (Enter = yes, Backspace = no, Space = skip).
4. **Report:** `reports/<serial>_<model>_<time>.txt / .json / .html / .keylog.csv`.
   The keylog contains every key event (time, key, scancode, device, test phase, key being asked).

Emergency exit during the test: press **Esc 3 times** quickly. The keyboard is always released on exit.

### Options

| Option | Meaning |
|---|---|
| `--list` | List input devices; `*` marks the ones the test uses |
| `--monitor` | Print raw key events (key, code, scancode, device); Ctrl+C to quit |
| `--learn` | Press every key on a known-good unit; saves `templates/learned_*.json` |
| `--template FILE`, `--layout hu` | Choose the template instead of auto-detection |
| `--timeout N` | Seconds per key (default: from the template, 5) |
| `--beep auto\|sound\|pcspkr\|bell\|off` | Beep method (sound = speakers via pw-play/paplay/aplay) |
| `--no-fn`, `--no-retry` | Skip the Fn tests / the retry of failed keys |
| `--include-usb`, `--device X` | Also use USB keyboards / only use the given device |

Without sudo, add your user to the `input` group (the serial number is then not shown in the report).
As root the script loads the `evdev` kernel module if needed (minimal live systems), and `hp_wmi` on HP machines.

## Supported keyboards

| Template | Models | Layout |
|---|---|---|
| `hp_elitebook_840_g5_g6_hu.json` | HP EliteBook 840 G5, 840 G6 | Hungarian (ISO) |

Verified on a real 840 G6. HP's "action keys" mode (F-keys do the action without Fn) is detected automatically.

## Adding a keyboard

Copy a template, set `match` to the model name (`/sys/class/dmi/id/product_name`), and describe the rows of keys
with their evdev key codes (by physical position). Use `--monitor` or `--learn` to find the codes.
The template format is described in `.claude/notes/working.md`.

## Development

Simulations with fake key input (no root needed): `.claude/scripts/run_sims.sh`.

## License

MIT - see [LICENSE](LICENSE).
