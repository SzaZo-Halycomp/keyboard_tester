#!/usr/bin/env python3
"""
Laptop keyboard tester for Linux.

Asks for every key of the laptop keyboard one by one (default 3 s each),
while the keyboard is grabbed exclusively (the OS / desktop does not receive
the key presses). At the end it runs the Fn-combination tests (keyboard
released so the system can react, you confirm what you saw) and writes a
TXT / JSON / HTML report.

Pure Python standard library - reads /dev/input/event* directly.
Needs root (sudo) or membership in the 'input' group.

Usage:
  sudo python3 keyboardtest.py              # run the test (template auto-detected)
  sudo python3 keyboardtest.py --learn      # record key codes on a known-good unit
  sudo python3 keyboardtest.py --monitor    # print raw key events (Ctrl+C to quit)
  sudo python3 keyboardtest.py --list       # list detected keyboard devices
"""

import argparse
import curses
import datetime
import fcntl
import glob
import html
import json
import locale
import os
import re
import math
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

VERSION = "1.4"
HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Linux input layer
# --------------------------------------------------------------------------

EV_SYN, EV_KEY, EV_MSC = 0, 1, 4
MSC_RAW, MSC_SCAN = 3, 4
EVENT_FMT = "llHHi"                      # struct input_event (native long)
EVENT_SIZE = struct.calcsize(EVENT_FMT)

# Keys the kernel has no key code for (e.g. HP calendar/screen keys) only
# produce an MSC_SCAN event. They are reported as pseudo codes SCAN_BASE+scancode.
SCAN_BASE = 0x10000


def _ioc(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (ord(typ) << 8) | nr


EVIOCGRAB = _ioc(1, "E", 0x90, 4)        # _IOW('E', 0x90, int)
EVIOCGKEYCODE = _ioc(2, "E", 0x04, 8)    # _IOR('E', 0x04, unsigned int[2])
KEY_BYTES = 0x300 // 8                   # KEY_CNT / 8
EVIOCGKEY = _ioc(2, "E", 0x18, KEY_BYTES)  # _IOC_READ, 'E', 0x18, len

BUS_USB = 0x03
EXCLUDED_DEVICES = ("Power Button", "Sleep Button", "Lid Switch", "PC Speaker")

# Fallback key-code table (used when /usr/include/linux/input-event-codes.h
# is not available, e.g. on a minimal live system).
_BUILTIN_CODES = {
    "KEY_ESC": 1, "KEY_1": 2, "KEY_2": 3, "KEY_3": 4, "KEY_4": 5, "KEY_5": 6,
    "KEY_6": 7, "KEY_7": 8, "KEY_8": 9, "KEY_9": 10, "KEY_0": 11,
    "KEY_MINUS": 12, "KEY_EQUAL": 13, "KEY_BACKSPACE": 14, "KEY_TAB": 15,
    "KEY_Q": 16, "KEY_W": 17, "KEY_E": 18, "KEY_R": 19, "KEY_T": 20,
    "KEY_Y": 21, "KEY_U": 22, "KEY_I": 23, "KEY_O": 24, "KEY_P": 25,
    "KEY_LEFTBRACE": 26, "KEY_RIGHTBRACE": 27, "KEY_ENTER": 28,
    "KEY_LEFTCTRL": 29, "KEY_A": 30, "KEY_S": 31, "KEY_D": 32, "KEY_F": 33,
    "KEY_G": 34, "KEY_H": 35, "KEY_J": 36, "KEY_K": 37, "KEY_L": 38,
    "KEY_SEMICOLON": 39, "KEY_APOSTROPHE": 40, "KEY_GRAVE": 41,
    "KEY_LEFTSHIFT": 42, "KEY_BACKSLASH": 43, "KEY_Z": 44, "KEY_X": 45,
    "KEY_C": 46, "KEY_V": 47, "KEY_B": 48, "KEY_N": 49, "KEY_M": 50,
    "KEY_COMMA": 51, "KEY_DOT": 52, "KEY_SLASH": 53, "KEY_RIGHTSHIFT": 54,
    "KEY_KPASTERISK": 55, "KEY_LEFTALT": 56, "KEY_SPACE": 57,
    "KEY_CAPSLOCK": 58, "KEY_F1": 59, "KEY_F2": 60, "KEY_F3": 61,
    "KEY_F4": 62, "KEY_F5": 63, "KEY_F6": 64, "KEY_F7": 65, "KEY_F8": 66,
    "KEY_F9": 67, "KEY_F10": 68, "KEY_NUMLOCK": 69, "KEY_SCROLLLOCK": 70,
    "KEY_102ND": 86, "KEY_F11": 87, "KEY_F12": 88, "KEY_KPENTER": 96,
    "KEY_RIGHTCTRL": 97, "KEY_SYSRQ": 99, "KEY_RIGHTALT": 100,
    "KEY_HOME": 102, "KEY_UP": 103, "KEY_PAGEUP": 104, "KEY_LEFT": 105,
    "KEY_RIGHT": 106, "KEY_END": 107, "KEY_DOWN": 108, "KEY_PAGEDOWN": 109,
    "KEY_INSERT": 110, "KEY_DELETE": 111, "KEY_MUTE": 113,
    "KEY_VOLUMEDOWN": 114, "KEY_VOLUMEUP": 115, "KEY_POWER": 116,
    "KEY_PAUSE": 119, "KEY_SCALE": 120, "KEY_LEFTMETA": 125,
    "KEY_RIGHTMETA": 126, "KEY_COMPOSE": 127, "KEY_HELP": 138,
    "KEY_SETUP": 141, "KEY_SLEEP": 142, "KEY_WAKEUP": 143, "KEY_PROG1": 148,
    "KEY_PROG2": 149, "KEY_ROTATE_DISPLAY": 153, "KEY_MAIL": 155,
    "KEY_NEXTSONG": 163, "KEY_PLAYPAUSE": 164, "KEY_PREVIOUSSONG": 165,
    "KEY_STOPCD": 166, "KEY_HOMEPAGE": 172, "KEY_F13": 183, "KEY_F14": 184,
    "KEY_F15": 185, "KEY_F16": 186, "KEY_F17": 187, "KEY_F18": 188,
    "KEY_F19": 189, "KEY_F20": 190, "KEY_F21": 191, "KEY_F22": 192,
    "KEY_F23": 193, "KEY_F24": 194, "KEY_PRINT": 210, "KEY_CAMERA": 212,
    "KEY_SEARCH": 217, "KEY_BRIGHTNESSDOWN": 224, "KEY_BRIGHTNESSUP": 225,
    "KEY_MEDIA": 226, "KEY_SWITCHVIDEOMODE": 227, "KEY_KBDILLUMTOGGLE": 228,
    "KEY_KBDILLUMDOWN": 229, "KEY_KBDILLUMUP": 230, "KEY_BATTERY": 236,
    "KEY_BLUETOOTH": 237, "KEY_WLAN": 238, "KEY_UNKNOWN": 240,
    "KEY_VIDEO_NEXT": 241, "KEY_VIDEO_PREV": 242, "KEY_BRIGHTNESS_CYCLE": 243,
    "KEY_BRIGHTNESS_AUTO": 244, "KEY_DISPLAY_OFF": 245, "KEY_RFKILL": 247,
    "KEY_MICMUTE": 248, "KEY_INFO": 0x166, "KEY_FN": 0x1D0,
    "KEY_FN_ESC": 0x1D1, "KEY_PICKUP_PHONE": 0x1BD, "KEY_HANGUP_PHONE": 0x1BE,
    "KEY_TOUCHPAD_TOGGLE": 0x212, "KEY_TOUCHPAD_ON": 0x213,
    "KEY_TOUCHPAD_OFF": 0x214, "KEY_PRIVACY_SCREEN_TOGGLE": 0x279,
    "KEY_SELECTIVE_SCREENSHOT": 0x27A,
}


def _load_codes():
    name2code = dict(_BUILTIN_CODES)
    hdr = "/usr/include/linux/input-event-codes.h"
    if os.path.exists(hdr):
        rx = re.compile(r"#define\s+(KEY_\w+)\s+(0x[0-9a-fA-F]+|\d+)\b")
        with open(hdr) as f:
            for line in f:
                m = rx.match(line)
                if m:
                    name2code.setdefault(m.group(1), int(m.group(2), 0))
    code2name = {}
    for n, c in sorted(name2code.items(), key=lambda kv: len(kv[0])):
        if n in ("KEY_MAX", "KEY_CNT", "KEY_RESERVED"):
            continue
        code2name.setdefault(c, n)
    # prefer the canonical names for a few aliased codes
    for n in ("KEY_MUTE", "KEY_ROTATE_DISPLAY", "KEY_MICMUTE", "KEY_SCREENLOCK"):
        if n in name2code:
            code2name[name2code[n]] = n
    return name2code, code2name


NAME2CODE, CODE2NAME = _load_codes()


def key_name(code):
    if code >= SCAN_BASE:
        return "SCAN_%x" % (code - SCAN_BASE)
    return CODE2NAME.get(code, "CODE_%d" % code)


def key_code(name):
    if name in NAME2CODE:
        return NAME2CODE[name]
    m = re.fullmatch(r"CODE_(\d+)", name)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"SCAN_([0-9a-fA-F]+)", name)
    if m:
        return SCAN_BASE + int(m.group(1), 16)
    raise ValueError("unknown key name in template: %s" % name)


K_ESC = NAME2CODE["KEY_ESC"]
K_ENTER = NAME2CODE["KEY_ENTER"]
K_KPENTER = NAME2CODE["KEY_KPENTER"]
K_BACKSPACE = NAME2CODE["KEY_BACKSPACE"]
K_SPACE = NAME2CODE["KEY_SPACE"]
K_FN = NAME2CODE["KEY_FN"]
K_I = NAME2CODE["KEY_I"]
K_N = NAME2CODE["KEY_N"]
MODIFIERS = {NAME2CODE[n] for n in (
    "KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTALT", "KEY_RIGHTALT",
    "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT", "KEY_LEFTMETA", "KEY_RIGHTMETA")}


def _decode_bitmap(text):
    bits = set()
    for i, word in enumerate(reversed(text.split())):
        v = int(word, 16)
        b = 0
        while v:
            if v & 1:
                bits.add(i * 64 + b)   # /proc uses unsigned long (64 bit here)
            v >>= 1
            b += 1
    return bits


def scan_devices():
    """Parse /proc/bus/input/devices."""
    devs, cur = [], {}
    with open("/proc/bus/input/devices") as f:
        lines = f.read().splitlines() + [""]
    for line in lines:
        if not line.strip():
            if cur:
                devs.append(cur)
            cur = {}
            continue
        tag, _, val = line.partition(": ")
        if tag == "I":
            m = re.search(r"Bus=([0-9a-fA-F]+)", val)
            cur["bus"] = int(m.group(1), 16) if m else None
        elif tag == "N":
            cur["name"] = val.split("=", 1)[1].strip().strip('"')
        elif tag == "P":
            cur["phys"] = val.split("=", 1)[1]
        elif tag == "H":
            m = re.search(r"\bevent(\d+)\b", val)
            cur["path"] = "/dev/input/event" + m.group(1) if m else None
        elif tag == "B":
            k, _, bm = val.partition("=")
            cur["bits_" + k] = bm
    return devs


def is_keyboard_like(d, include_usb=False):
    if not d.get("path") or d.get("name") in EXCLUDED_DEVICES:
        return False
    keys = _decode_bitmap(d.get("bits_KEY", ""))
    if not keys:
        return False
    if any(0x110 <= k <= 0x14F for k in keys):     # mouse / touchpad buttons
        return False
    if not any(k < 0x100 or k >= 0x160 for k in keys):
        return False
    if d.get("bus") == BUS_USB and not include_usb:
        return False
    return True


class Device:
    def __init__(self, info):
        self.path = info["path"]
        self.name = info.get("name", "?")
        self.phys = info.get("phys", "")
        self.bus = info.get("bus")
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        self.grabbed = False
        self._last_raw = None
        self._pending_scan = None        # (time, scancode, raw) awaiting a key event
        self._scan_down = set()
        self._down = set()               # key codes this device reported as held
        self._keymap = {}                # scancode -> key code (kernel table cache)

    def grab(self):
        fcntl.ioctl(self.fd, EVIOCGRAB, 1)
        self.grabbed = True

    def ungrab(self):
        if self.grabbed:
            try:
                fcntl.ioctl(self.fd, EVIOCGRAB, 0)
            except OSError:
                pass
            self.grabbed = False

    def pressed_keys(self):
        buf = bytearray(KEY_BYTES)
        try:
            fcntl.ioctl(self.fd, EVIOCGKEY, buf, True)
        except OSError:
            return set()
        out = set()
        for i, byte in enumerate(buf):
            for b in range(8):
                if byte >> b & 1:
                    out.add(i * 8 + b)
        return out

    def keycode_for_scan(self, sc):
        if sc not in self._keymap:
            buf = bytearray(struct.pack("II", sc, 0))
            try:
                fcntl.ioctl(self.fd, EVIOCGKEYCODE, buf, True)
                self._keymap[sc] = struct.unpack("II", buf)[1]
            except OSError:
                self._keymap[sc] = 0
        return self._keymap[sc]

    def _flush_scan(self, out):
        """An MSC_SCAN not followed by a key event.

        Either a key without a key code (-> pseudo code SCAN_xx), or a mapped key
        whose EV_KEY the kernel suppressed because its own key state was out of
        sync (-> reported as that key, flagged as orphan)."""
        if self._pending_scan is None:
            return
        t, sc, raw = self._pending_scan
        self._pending_scan = None
        kc = self.keycode_for_scan(sc)
        if kc not in (0, NAME2CODE["KEY_UNKNOWN"]):
            value = 0 if kc in self._down else 1
            (self._down.add if value else self._down.discard)(kc)
            out.append((t, kc, value, sc, True))
            return
        if raw is not None:
            value = 0 if raw & 0x80 else 1
        else:                               # no raw byte: alternate press/release
            value = 0 if sc in self._scan_down else 1
        if value:
            self._scan_down.add(sc)
        else:
            self._scan_down.discard(sc)
        out.append((t, SCAN_BASE + sc, value, sc, True))

    def read(self):
        try:
            data = os.read(self.fd, EVENT_SIZE * 64)
        except (BlockingIOError, InterruptedError):
            return []
        out = []
        for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            sec, usec, typ, code, value = struct.unpack_from(EVENT_FMT, data, off)
            t = sec + usec / 1e6
            if typ == EV_KEY:
                scan = self._pending_scan[1] if self._pending_scan else None
                self._pending_scan = None
                if value == 1:
                    self._down.add(code)
                elif value == 0:
                    self._down.discard(code)
                out.append((t, code, value, scan, False))
            elif typ == EV_MSC and code == MSC_RAW:
                self._last_raw = value
            elif typ == EV_MSC and code == MSC_SCAN:
                self._flush_scan(out)
                self._pending_scan = (t, value, self._last_raw)
                self._last_raw = None
            elif typ == EV_SYN:
                self._flush_scan(out)
        return out

    def close(self):
        self.ungrab()
        try:
            os.close(self.fd)
        except OSError:
            pass

    def describe(self):
        return {"name": self.name, "path": self.path, "phys": self.phys,
                "bus": "0x%02x" % self.bus if self.bus is not None else None}


class Abort(Exception):
    pass


class Event:
    __slots__ = ("t", "dev", "code", "value", "scan")

    def __init__(self, t, dev, code, value, scan=None):
        self.t, self.dev, self.code, self.value, self.scan = t, dev, code, value, scan

    @property
    def name(self):
        return key_name(self.code)


class Input:
    """Multiplexes all keyboard-like devices; Esc pressed 3x within 1.5 s aborts."""

    def __init__(self, devices):
        self.devices = devices
        self.by_fd = {d.fd: d for d in devices}
        self.esc_presses = []
        self.abort_enabled = True
        self.t0 = time.monotonic()
        self.log = []                     # every key event: see _log()
        self.context = {"phase": "init", "key": None}

    def set_context(self, phase, key=None):
        self.context = {"phase": phase, "key": key}

    def _log(self, dev, t, code, value, scan, orphan=False, dropped=False):
        self.log.append({
            "t": round(time.monotonic() - self.t0, 3),
            "time": datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec="milliseconds"),
            "event": {0: "up", 1: "down", 2: "repeat"}.get(value, str(value)),
            "key": key_name(code), "code": code,
            "scan": ("0x%x" % scan) if scan is not None else None,
            "device": dev.name, "phase": self.context["phase"],
            "asked": self.context["key"], "orphan": orphan, "dropped": dropped})

    def any_pressed(self):
        return any(d.pressed_keys() for d in self.devices)

    def wait_release(self, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end and self.any_pressed():
            time.sleep(0.03)
        self.drain()

    def grab_all(self):
        # grabbing while a key is held would leave the OS with a "stuck" key
        self.wait_release()
        for d in self.devices:
            d.grab()

    def ungrab_all(self):
        self.wait_release(2.0)
        for d in self.devices:
            d.ungrab()

    def drain(self):
        for d in self.devices:
            while True:
                evs = d.read()
                if not evs:
                    break
                for t, code, value, scan, orphan in evs:
                    if value != 2:
                        self._log(d, t, code, value, scan, orphan, dropped=True)

    def events(self, timeout):
        """Key press (1) and release (0) events; autorepeat (2) is dropped."""
        try:
            r, _, _ = select.select(list(self.by_fd), [], [], max(0.0, timeout))
        except InterruptedError:
            return []
        out = []
        for fd in r:
            dev = self.by_fd[fd]
            for t, code, value, scan, orphan in dev.read():
                if value == 2:
                    continue
                self._log(dev, t, code, value, scan, orphan)
                ev = Event(t, dev, code, value, scan)
                out.append(ev)
                if value == 1 and code == K_ESC and self.abort_enabled:
                    now = time.monotonic()
                    self.esc_presses = [x for x in self.esc_presses if now - x < 1.5] + [now]
                    if len(self.esc_presses) >= 3:
                        raise Abort()
        return out

    def close(self):
        for d in self.devices:
            d.close()


def open_devices(include_usb=False, only=None):
    infos = [d for d in scan_devices() if is_keyboard_like(d, include_usb)]
    if only:
        infos = [d for d in infos if d["path"] in only or only_match(d, only)]
    devs, errors = [], []
    for info in infos:
        try:
            devs.append(Device(info))
        except PermissionError:
            errors.append(info["path"])
    if errors and not devs:
        sys.exit("No permission to read %s.\nRun with sudo, or add your user to the "
                 "'input' group." % ", ".join(errors))
    if not devs:
        sys.exit("No keyboard device found.")
    return devs


def only_match(info, only):
    return any(o.lower() in info.get("name", "").lower() for o in only)


# --------------------------------------------------------------------------
# Machine info and templates
# --------------------------------------------------------------------------

def read_dmi(field):
    try:
        with open("/sys/class/dmi/id/" + field) as f:
            return f.read().strip()
    except OSError:
        return ""


def model_name(m):
    if m["product"].lower().startswith(m["vendor"].lower()):
        return m["product"]
    return ("%s %s" % (m["vendor"], m["product"])).strip()


def machine_info():
    return {
        "vendor": read_dmi("sys_vendor"),
        "product": read_dmi("product_name"),
        "version": read_dmi("product_version"),
        "sku": read_dmi("product_sku"),
        "serial": read_dmi("product_serial"),
        "board_serial": read_dmi("board_serial"),
        "bios_version": read_dmi("bios_version"),
        "bios_date": read_dmi("bios_date"),
        "hostname": socket.gethostname(),
        "kernel": os.uname().release,
    }


def load_template(path):
    with open(path, encoding="utf-8") as f:
        t = json.load(f)
    keys = []
    for r, row in enumerate(t["rows"]):
        x = 0.0
        for i, k in enumerate(row):
            x = float(k.get("x", x))
            w = float(k.get("w", 1))
            names = k.get("codes", [])
            combo = k.get("combo", [])
            key = {
                "id": "r%dk%d" % (r, i),
                "label": k["label"],
                "name": k.get("name", k["label"]),
                "row": r, "x": x, "w": w,
                "code_names": names,
                "codes": [key_code(n) for n in names],
                "combo_names": combo,
                "combo": {key_code(n) for n in combo},
                "test": bool(k.get("test", bool(names or combo))),
                "accept_scan": bool(k.get("accept_scan", False)),
                "silent_in_action_mode": bool(k.get("silent_in_action_mode", False)),
                "mode_probe": bool(k.get("mode_probe", False)),
                "mirror_of": k.get("mirror_of"),
                "hint": k.get("hint", ""),
            }
            keys.append(key)
            x += w
    by_label = {k["label"]: k for k in keys if k["test"]}
    for k in keys:
        k["mirror_id"] = by_label[k["mirror_of"]]["id"] if k["mirror_of"] in by_label else None
    t["keys"] = keys
    t["path"] = path
    t.setdefault("timeout", 3)
    t.setdefault("fn_tests", [])
    all_codes = set()
    for k in keys:
        all_codes.update(k["codes"])
    t["all_codes"] = all_codes
    return t


def find_template(machine, layout=None):
    product = machine["product"].lower()
    found = []
    for p in sorted(glob.glob(os.path.join(HERE, "templates", "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                t = json.load(f)
        except (OSError, ValueError):
            continue
        if any(m.lower() in product for m in t.get("match", [])):
            if layout is None or t.get("layout") == layout:
                found.append(p)
    return found


# --------------------------------------------------------------------------
# Beeper: short tone when a key must be pressed
# --------------------------------------------------------------------------

TONES = {"go": (880, 0.07), "bad": (300, 0.22)}


class Beeper:
    """Methods: 'sound' (pw-play/paplay/aplay through the user's audio session),
    'pcspkr' (PC speaker input device), 'bell' (terminal bell), 'off'."""

    def __init__(self, mode="auto"):
        self.method = "off"
        self.procs = []
        self.files = {}
        self.pcspkr_fd = None
        if mode in ("auto", "sound") and self._setup_sound():
            self.method = "sound"
        elif mode in ("auto", "pcspkr") and self._setup_pcspkr():
            self.method = "pcspkr"
        elif mode in ("auto", "bell", "sound", "pcspkr"):
            self.method = "bell"

    def _setup_sound(self):
        player = next((shutil.which(p) for p in ("pw-play", "paplay", "aplay") if shutil.which(p)), None)
        if not player:
            return False
        d = tempfile.mkdtemp(prefix="kbdtest-")
        os.chmod(d, 0o755)
        for name, (freq, dur) in TONES.items():
            path = os.path.join(d, name + ".wav")
            rate, n = 44100, int(44100 * dur)
            with wave.open(path, "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(rate)
                f.writeframes(b"".join(
                    struct.pack("<h", int(14000 * math.sin(2 * math.pi * freq * i / rate)
                                          * min(1.0, i / 200, (n - i) / 200)))
                    for i in range(n)))
            os.chmod(path, 0o644)
            self.files[name] = path
        self.tmpdir = d
        self.cmd = [player]
        self.popen_kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                         "stderr": subprocess.DEVNULL}
        uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
        if os.geteuid() == 0 and uid:
            # root can't reach the desktop audio session: play as the real user
            run = "/run/user/%s" % uid
            env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": run,
                   "PULSE_SERVER": "unix:%s/pulse/native" % run}
            self.popen_kw.update(user=int(uid), group=int(gid or uid), extra_groups=[],
                                 env=env, cwd="/")
        return True

    def _setup_pcspkr(self):
        for d in scan_devices():
            if d.get("name") == "PC Speaker" and d.get("path"):
                try:
                    self.pcspkr_fd = os.open(d["path"], os.O_WRONLY)
                    return True
                except OSError:
                    return False
        return False

    def _pcspkr_tone(self, freq):
        try:
            os.write(self.pcspkr_fd, struct.pack(EVENT_FMT, 0, 0, 0x12, 2, freq))  # EV_SND, SND_TONE
        except OSError:
            pass

    def beep(self, kind="go"):
        freq, dur = TONES[kind]
        try:
            if self.method == "sound":
                self.procs = [p for p in self.procs if p.poll() is None]
                self.procs.append(subprocess.Popen(self.cmd + [self.files[kind]], **self.popen_kw))
            elif self.method == "pcspkr":
                self._pcspkr_tone(freq)
                threading.Timer(dur, self._pcspkr_tone, (0,)).start()
            elif self.method == "bell":
                curses.beep()
        except (OSError, curses.error, subprocess.SubprocessError):
            pass

    def close(self):
        for p in self.procs:
            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                p.kill()
        if self.files:
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self.pcspkr_fd is not None:
            self._pcspkr_tone(0)
            os.close(self.pcspkr_fd)


BEEPER = None


def beep(kind="go"):
    if BEEPER is not None:
        BEEPER.beep(kind)


# --------------------------------------------------------------------------
# Curses UI
# --------------------------------------------------------------------------

C_PENDING, C_CURRENT, C_PASS, C_FAIL, C_NA, C_TITLE, C_WARN, C_OK = range(1, 9)


class UI:
    def __init__(self, scr, template, title):
        self.scr = scr
        self.t = template
        self.title = title
        self.status = {k["id"]: ("pending" if k["test"] else "na") for k in template["keys"]}
        self.n_rows = max(k["row"] for k in template["keys"]) + 1
        self.units = max(k["x"] + k["w"] for k in template["keys"])
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        scr.nodelay(True)
        scr.keypad(True)
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            curses.init_pair(C_PENDING, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(C_CURRENT, curses.COLOR_BLACK, curses.COLOR_YELLOW)
            curses.init_pair(C_PASS, curses.COLOR_BLACK, curses.COLOR_GREEN)
            curses.init_pair(C_FAIL, curses.COLOR_WHITE, curses.COLOR_RED)
            curses.init_pair(C_NA, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(C_TITLE, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(C_WARN, curses.COLOR_RED, bg)
            curses.init_pair(C_OK, curses.COLOR_GREEN, bg)

    def attr(self, pair, extra=0):
        if curses.has_colors():
            return curses.color_pair(pair) | extra
        return extra | (curses.A_REVERSE if pair in (C_CURRENT, C_TITLE) else 0)

    def put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        text = text[: max(0, w - x - (1 if y == h - 1 else 0))]
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def center(self, y, text, attr=0):
        w = self.scr.getmaxyx()[1]
        self.put(y, max(0, (w - len(text)) // 2), text, attr)

    def draw_map(self, y0, current=None):
        w = self.scr.getmaxyx()[1]
        unit = max(3.0, min(7.0, (w - 2) / self.units))
        x_off = max(0, int((w - self.units * unit) // 2))
        colors = {"pending": C_PENDING, "current": C_CURRENT, "pass": C_PASS,
                  "fail": C_FAIL, "na": C_NA}
        for k in self.t["keys"]:
            kid = k["mirror_id"] or k["id"]
            st = "current" if kid == current else self.status[kid]
            sx = x_off + int(round(k["x"] * unit))
            ex = x_off + int(round((k["x"] + k["w"]) * unit)) - 1
            width = max(1, ex - sx)
            self.put(y0 + k["row"], sx, k["label"][:width].center(width),
                     self.attr(colors[st], curses.A_BOLD if st == "current" else 0))

    def render(self, phase, big=None, lines=(), bar=None, msg=None, msg_ok=False,
               current=None, show_map=True, footer=None):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self.put(0, 0, (" " + self.title).ljust(w), self.attr(C_TITLE, curses.A_BOLD))
        self.put(1, 1, phase, curses.A_BOLD)
        y = 3
        if big is not None:
            inner = " %s " % big
            box_w = max(len(inner) + 4, 15)
            self.center(y, "+" + "-" * (box_w - 2) + "+")
            self.center(y + 1, "|" + inner.center(box_w - 2) + "|", curses.A_BOLD)
            self.center(y + 2, "+" + "-" * (box_w - 2) + "+")
            y += 4
        if bar is not None:
            frac, label = bar
            bw = min(50, w - 12)
            filled = int(round(bw * max(0.0, min(1.0, frac))))
            self.center(y, "[" + "#" * filled + "." * (bw - filled) + "] " + label)
            y += 2
        for line in lines:
            self.put(y, 2, line)
            y += 1
        if msg:
            y += 1
            self.put(y, 2, msg, self.attr(C_OK if msg_ok else C_WARN, curses.A_BOLD))
        if show_map:
            map_y = max(y + 2, h - self.n_rows - 2)
            self.draw_map(map_y, current)
        self.put(h - 1, 1, footer or "Emergency exit: press Esc 3x quickly", curses.A_DIM)
        self.scr.refresh()
        # discard anything the terminal received (only possible when not grabbed)
        while self.scr.getch() != -1:
            pass


# --------------------------------------------------------------------------
# Test logic
# --------------------------------------------------------------------------

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def wait_choice(ui, inp, render_fn, choices, timeout=None):
    """Wait for one of the key codes in `choices` (dict code->value)."""
    end = None if timeout is None else time.monotonic() + timeout
    while True:
        remaining = None if end is None else end - time.monotonic()
        if remaining is not None and remaining <= 0:
            return None
        render_fn(remaining)
        for ev in inp.events(0.1 if remaining is None else min(0.1, remaining)):
            if ev.value == 1 and ev.code in choices:
                return choices[ev.code]


def key_matches(key, code, template):
    if code in key["codes"]:
        return True
    if key["accept_scan"] and code >= SCAN_BASE and code not in template["all_codes"]:
        return True
    return False


def prompt_for(key, action_mode):
    """Text shown for the key, and the timeout factor."""
    if key["silent_in_action_mode"]:
        if action_mode:
            return "Fn + " + key["name"], 1.5
        if action_mode is None:
            return key["name"] + "  (or Fn + %s)" % key["name"], 2.0
    return key["name"], 1.0


def wait_releases(inp, codes, timeout):
    """Wait until all `codes` are released. True if they were. Updates `codes`."""
    pending = codes
    end = time.monotonic() + timeout
    while pending and time.monotonic() < end:
        for ev in inp.events(0.05):
            if ev.value == 0:
                pending.discard(ev.code)
    return not pending


def test_one_key(ui, inp, key, template, timeout, phase, prompt, early=None):
    start = time.monotonic()
    deadline = start + timeout
    wrong, noise = [], []
    held = set()                 # keys currently down (pressed during this prompt)
    mods_seen = set()
    key_is_modifier = any(c in MODIFIERS for c in key["codes"])
    msg = None
    lines = ["Press the key shown above."]
    if key["hint"]:
        lines.append("(%s)" % key["hint"])

    def passed(got, dev):
        reaction = int((time.monotonic() - start) * 1000)
        released = wait_releases(inp, held, 1.5)
        return {"status": "PASS" if released else "STUCK", "got": got,
                "device": dev, "wrong": wrong, "extra": noise, "reaction_ms": reaction}

    if early is not None:
        held.add(early.code)
        res = passed(early.name, early.dev.name)
        res["early"] = True
        res["reaction_ms"] = 0
        return res
    beeped = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ui.render(phase, big=prompt, bar=(remaining / timeout, "%.1f s" % remaining),
                  lines=lines, msg=msg, current=key["id"])
        if not beeped:
            beep("go")          # right after the prompt is on screen
            beeped = True
        for ev in inp.events(min(0.05, remaining)):
            if ev.value == 0:
                held.discard(ev.code)
                continue
            held.add(ev.code)
            if key_matches(key, ev.code, template):
                return passed(ev.name, ev.dev.name)
            if ev.code == K_FN:
                continue
            if ev.code in MODIFIERS and not key_is_modifier:
                # macro keys send modifiers along with their code - not an error
                mods_seen.add(ev.code)
                noise.append(ev.name)
                if key["combo"] and key["combo"] <= mods_seen:
                    got = "+".join(key_name(c) for c in sorted(key["combo"]))
                    # a scancode may follow; prefer it as the precise identity
                    end2 = time.monotonic() + 0.3
                    while time.monotonic() < end2:
                        for e2 in inp.events(0.05):
                            if e2.value == 0:
                                held.discard(e2.code)
                                continue
                            held.add(e2.code)
                            if key_matches(key, e2.code, template):
                                got = e2.name
                    return passed(got, ev.dev.name)
                continue
            wrong.append(ev.name)
            msg = "Wrong key received: %s" % ev.name
    if noise and not wrong:
        wrong = noise
    return {"status": "WRONG" if wrong else "TIMEOUT", "got": None, "device": None,
            "wrong": wrong, "extra": [], "reaction_ms": None}


def gap(ui, inp, seconds, data, phase_name, next_key=None, template=None):
    """Short pause between keys; presses here are logged as unexpected.
    If the NEXT key is pressed already (tester was quick), that press is returned."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for ev in inp.events(max(0.0, end - time.monotonic())):
            if ev.value != 1:
                continue
            if next_key is not None and key_matches(next_key, ev.code, template):
                return ev
            data["unexpected"].append({"time": now_iso(), "phase": phase_name,
                                       "key": ev.name, "device": ev.dev.name})
    return None


def record_result(data, key, res, prompt):
    prev = data["results"].get(key["id"])
    res["events"] = [e["event"] + ":" + e["key"] for e in data["_inp"].log
                     if e["asked"] == key["label"]
                     and e["phase"] in ("main", "retry", "main-gap", "retry-gap")
                     and e["t"] >= data.get("_t_gap", 0)]
    res.update({"label": key["label"], "prompt": prompt, "row": key["row"],
                "expected": key["code_names"] + (["+".join(key["combo_names"])] if key["combo_names"] else []),
                "attempts": (prev["attempts"] + 1) if prev else 1,
                "history": (prev["history"] if prev else []) + [res["status"]]})
    data["results"][key["id"]] = res


def update_action_mode(key, res, data):
    if key["mode_probe"] and res["status"] == "PASS":
        data["action_keys_mode"] = res["got"] not in ("KEY_" + key["label"],)


def run_keys(ui, inp, template, data, keys, timeout, retry=False):
    early = None
    for i, k in enumerate(keys, 1):
        prompt, factor = prompt_for(k, data["action_keys_mode"])
        phase = "%s  key %d / %d" % ("RETRY" if retry else "Key test", i, len(keys))
        inp.set_context("retry" if retry else "main", k["label"])
        res = test_one_key(ui, inp, k, template, timeout * factor, phase, prompt, early)
        record_result(data, k, res, prompt)
        update_action_mode(k, res, data)
        ok = res["status"] == "PASS"
        if not ok:
            beep("bad")
        ui.status[k["id"]] = "pass" if ok else "fail"
        ui.render(phase, big=prompt, msg=("OK" if ok else res["status"]), msg_ok=ok)
        data["_t_gap"] = round(time.monotonic() - inp.t0, 3)
        nxt = keys[i] if i < len(keys) else None
        inp.set_context(("retry" if retry else "main") + "-gap", nxt["label"] if nxt else None)
        early = gap(ui, inp, 0.35 if ok else 0.8, data, "retry" if retry else "main",
                    nxt, template)


def run_retry_phase(ui, inp, template, data, timeout):
    while True:
        failed = [k for k in template["keys"]
                  if k["test"] and data["results"][k["id"]]["status"] != "PASS"]
        if not failed:
            return
        labels = ", ".join(k["label"] for k in failed)
        choice = wait_choice(
            ui, inp,
            lambda rem: ui.render(
                "Failed keys", lines=[
                    "%d key(s) failed: %s" % (len(failed), labels), "",
                    "ENTER     = retry the failed keys",
                    "SPACE     = continue",
                    "(continues automatically in %d s)" % int(rem or 0)]),
            {K_ENTER: "retry", K_KPENTER: "retry", K_SPACE: "continue"}, timeout=20)
        if choice != "retry":
            return
        gap(ui, inp, 0.4, data, "retry")
        run_keys(ui, inp, template, data, failed, timeout, retry=True)


def ask_failed_keys(ui, inp, template, data):
    """For every failed key ask the tester whether the right key was really pressed."""
    failed = [k for k in template["keys"]
              if k["test"] and data["results"][k["id"]]["status"] != "PASS"]
    choices = {K_ENTER: "yes", K_KPENTER: "yes", K_I: "yes",
               K_BACKSPACE: "no", K_N: "no", K_SPACE: "unsure"}
    for i, k in enumerate(failed, 1):
        r = data["results"][k["id"]]
        got = ", ".join(r.get("wrong") or []) or "nothing"
        inp.set_context("confirm-failed", k["label"])
        gap(ui, inp, 0.3, data, "confirm")
        ans = wait_choice(ui, inp, lambda rem: ui.render(
            "Failed key %d / %d - your feedback" % (i, len(failed)), big=k["label"],
            current=k["id"], lines=[
                "This key FAILED (%s). Received while asked: %s" % (r["status"], got),
                "",
                "Did you really press this key, at the position marked on the map?",
                "   ENTER (or I) = YES, I pressed the right key  -> keyboard fault",
                "   BACKSPACE (or N) = NO, I missed / pressed another key",
                "   SPACE = not sure",
                "", "Answer in %d s" % int(rem or 0)]),
            choices, timeout=60)
        r["user_pressed_right_key"] = ans
    inp.set_context("after-confirm")


def build_fn_steps(template, action_mode):
    steps = []
    for item in template["fn_tests"]:
        s = dict(item)
        if "fkey" in s and "keys" not in s:
            s["keys"] = s["fkey"] if action_mode else "Fn + " + s["fkey"]
        if "codes" not in s:
            s["codes"] = s.get("codes_action" if action_mode else "codes_plain", [])
        steps.append(s)
    return steps


def run_fn_phase(ui, inp, template, data):
    action_mode = data["action_keys_mode"]
    if action_mode is None:
        action_mode = True                  # HP default
    inp.ungrab_all()
    data["fn_phase_ungrabbed"] = True
    answers = {K_ENTER: "YES", K_KPENTER: "YES", K_BACKSPACE: "NO", K_SPACE: "SKIP"}
    mode_txt = ("ON  - the F-keys do their action WITHOUT Fn" if action_mode
                else "OFF - the F-keys do their action WITH Fn")
    choice = wait_choice(
        ui, inp,
        lambda rem: ui.render("Fn / action keys", show_map=False, lines=[
            "Key test finished. The keyboard is now RELEASED so the system",
            "reacts to the keys (brightness, volume, ...).",
            "",
            "Action-keys mode: " + mode_txt,
            "",
            "Each step shows what to press and what should happen.",
            "Press it ONCE, watch, then answer:",
            "   ENTER = YES, it happened    BACKSPACE = NO    SPACE = skip",
            "Steps marked 'signal check' pass by themselves when the key works.",
            "",
            "Press ENTER to begin, SPACE to skip these tests."]),
        {K_ENTER: "go", K_KPENTER: "go", K_SPACE: "skip"}, timeout=120)
    if choice != "go":
        data["fn_skipped"] = True
        return
    steps = build_fn_steps(template, action_mode)
    for i, s in enumerate(steps, 1):
        inp.wait_release(2.0)
        inp.set_context("fn", s["keys"])
        res = run_fn_step(ui, inp, s, i, len(steps), answers)
        data["fn_results"].append(res)


def run_fn_step(ui, inp, step, idx, total, answers):
    want = set(key_code(n) for n in step.get("codes", []))
    mode = step.get("mode", "confirm")
    timeout = 30.0
    end = time.monotonic() + timeout
    received = []
    result = None
    phase = "Fn / action keys  %d / %d" % (idx, total)
    if mode == "signal":
        how = ["Signal check - passes by itself when the signal arrives.",
               "BACKSPACE = not working    SPACE = skip"]
    else:
        how = ["Then answer:  ENTER = YES, it happened    BACKSPACE = NO    SPACE = skip"]
    first = True
    while result is None:
        rem = end - time.monotonic()
        if rem <= 0:
            result = "NO SIGNAL" if mode == "signal" else "NO ANSWER"
            break
        if first:
            first = False
            ui.render(phase, big=step["keys"], show_map=False)
            beep("go")
        ui.render(phase, big=step["keys"], show_map=False,
                  bar=(rem / timeout, "%d s" % rem),
                  lines=["Press it ONCE.", "",
                         "Expected:  " + step.get("see", ""), ""] + how +
                        ["", "Signals received: " + (", ".join(received) or "-")])
        for ev in inp.events(min(0.1, rem)):
            if ev.value != 1 or ev.code == K_FN:
                continue
            if ev.code in answers and ev.code not in want:
                ans = answers[ev.code]
                if mode == "signal" and ans == "YES":
                    continue            # signal steps can't be confirmed by hand
                result = ans
                break
            if ev.code in MODIFIERS and ev.code not in want:
                continue
            received.append(ev.name)
            if mode == "signal" and ev.code in want:
                result = "SIGNAL"
                ui.render(phase, big=step["keys"], show_map=False,
                          msg="Signal received: %s" % ev.name, msg_ok=True)
                time.sleep(0.7)
                break
    status = {"YES": "PASS", "SIGNAL": "PASS", "SKIP": "SKIPPED"}.get(result, "FAIL")
    return {"keys": step["keys"], "mode": mode, "see": step.get("see", ""),
            "expected_codes": step.get("codes", []),
            "answer": result, "status": status, "received": received}


def summary(template, data):
    tested = [k for k in template["keys"] if k["test"]]
    failed = [k["label"] for k in tested
              if data["results"].get(k["id"], {}).get("status") != "PASS"]
    retried_ok = [k["label"] for k in tested
                  if data["results"].get(k["id"], {}).get("status") == "PASS"
                  and data["results"][k["id"]]["attempts"] > 1]
    fn_failed = [r["keys"] for r in data["fn_results"] if r["status"] == "FAIL"]
    fn_skipped = [r["keys"] for r in data["fn_results"] if r["status"] == "SKIPPED"]
    if data.get("aborted"):
        overall = "INCOMPLETE"
    elif failed or fn_failed:
        overall = "FAIL"
    else:
        overall = "PASS"
    return {"overall": overall, "keys_total": len(tested),
            "keys_passed": len(tested) - len(failed), "keys_failed": failed,
            "keys_passed_on_retry": retried_ok,
            "fn_total": len(data["fn_results"]), "fn_failed": fn_failed,
            "fn_skipped": fn_skipped, "unexpected_presses": len(data["unexpected"])}


def interactive(scr, inp, template, data, args):
    title = "Keyboard test v%s  -  %s  -  S/N %s" % (
        VERSION, data["machine"]["product"] or "?", data["machine"]["serial"] or "?")
    ui = UI(scr, template, title)
    timeout = args.timeout or template["timeout"]
    keys = [k for k in template["keys"] if k["test"]]
    try:
        inp.grab_all()
        data["grabbed"] = True
        beep("go")
        beep_txt = {"sound": "speakers", "pcspkr": "PC speaker", "bell": "terminal bell",
                    "off": "OFF"}[BEEPER.method if BEEPER else "off"]
        wait_choice(ui, inp, lambda rem: ui.render("Ready", big="SPACE", lines=[
            "Template : %s" % template["name"],
            "Keys     : %d, %g s per key, then Fn / action keys" % (len(keys), timeout),
            "",
            "The keyboard is now GRABBED - the system does not receive key presses.",
            "Watch the keyboard: on each BEEP press the key shown here.",
            "A low tone means the key failed.",
            "Beep: %s - you should have heard one just now. If not: restart with" % beep_txt,
            "      --beep pcspkr  or  --beep bell  (or check the volume / mute).",
            "",
            "Press SPACE or ENTER to start."]),
            {K_SPACE: 1, K_ENTER: 1, K_KPENTER: 1})
        gap(ui, inp, 0.5, data, "start")
        inp.set_context("layout-check")
        ans = wait_choice(ui, inp, lambda rem: ui.render("Layout check", lines=[
            "Does the keyboard drawn below look like THIS laptop's keyboard?",
            "(same keys, same positions - colours don't matter)",
            "",
            "ENTER = YES, it matches",
            "BACKSPACE = NO, it is different (the test continues, the report notes it)",
            "", "Answer in %d s" % int(rem or 0)]),
            {K_ENTER: True, K_KPENTER: True, K_BACKSPACE: False, K_I: True, K_N: False},
            timeout=60)
        data["layout_confirmed"] = ans
        gap(ui, inp, 0.4, data, "start")
        data["started"] = now_iso()
        run_keys(ui, inp, template, data, keys, timeout)
        if not args.no_retry:
            run_retry_phase(ui, inp, template, data, timeout)
        ask_failed_keys(ui, inp, template, data)
        if template["fn_tests"] and not args.no_fn:
            run_fn_phase(ui, inp, template, data)
    except Abort:
        data["aborted"] = True
    data["finished"] = now_iso()
    inp.ungrab_all()
    s = summary(template, data)
    lines = ["Result      : %s" % s["overall"],
             "Keys passed : %d / %d" % (s["keys_passed"], s["keys_total"]),
             "Failed keys : %s" % (", ".join(s["keys_failed"]) or "-"),
             "Fn failed   : %s" % (", ".join(s["fn_failed"]) or "-"),
             "", "Writing report... press ENTER (or wait 10 s)."]
    try:
        inp.abort_enabled = False
        wait_choice(ui, inp, lambda rem: ui.render("Finished", lines=lines,
                                                   footer="Keyboard released."),
                    {K_ENTER: 1, K_KPENTER: 1, K_SPACE: 1, K_ESC: 1}, timeout=10)
    except Abort:
        pass


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

def slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "unknown"


def report_rows(template, data):
    rows = []
    for k in template["keys"]:
        if not k["test"]:
            continue
        r = data["results"].get(k["id"])
        if r is None:
            r = {"status": "NOT TESTED", "got": None, "wrong": [], "attempts": 0,
                 "reaction_ms": None, "history": []}
        rows.append((k, r))
    return rows


def _notes(r):
    notes = []
    if r.get("wrong"):
        notes.append("wrong: " + ",".join(r["wrong"]))
    if r.get("attempts", 0) > 1:
        notes.append("attempts: " + "/".join(r["history"]))
    if r.get("prompt") and r.get("prompt") != r.get("label"):
        notes.append("asked: " + r["prompt"])
    if r.get("early"):
        notes.append("pressed before the prompt appeared")
    if r.get("user_pressed_right_key"):
        notes.append("tester: pressed right key=" + r["user_pressed_right_key"])
    return notes


def _layout_txt(data):
    return {True: "yes (confirmed by tester)", False: "NO - tester says the on-screen layout differs",
            None: "not answered"}[data.get("layout_confirmed")]


def _mode_txt(data):
    return {True: "ON", False: "OFF", None: "-"}[data.get("action_keys_mode")]


def write_txt(path, template, data, s):
    m = data["machine"]
    out = []
    out.append("KEYBOARD TEST REPORT")
    out.append("=" * 70)
    out.append("Result        : %s" % s["overall"])
    out.append("Model         : %s" % model_name(m))
    out.append("Serial        : %s" % (m["serial"] or "-"))
    out.append("SKU           : %s" % (m["sku"] or "-"))
    out.append("BIOS          : %s (%s)" % (m["bios_version"], m["bios_date"]))
    out.append("Template      : %s" % template["name"])
    out.append("Started       : %s" % data.get("started", "-"))
    out.append("Finished      : %s" % data.get("finished", "-"))
    out.append("Aborted       : %s" % ("YES" if data.get("aborted") else "no"))
    out.append("Action keys   : %s" % _mode_txt(data))
    out.append("Layout OK     : %s" % _layout_txt(data))
    out.append("")
    out.append("Keys passed   : %d / %d" % (s["keys_passed"], s["keys_total"]))
    out.append("Failed keys   : %s" % (", ".join(s["keys_failed"]) or "-"))
    out.append("Passed on retry: %s" % (", ".join(s["keys_passed_on_retry"]) or "-"))
    out.append("Fn failed     : %s" % (", ".join(s["fn_failed"]) or "-"))
    out.append("Fn skipped    : %s" % (", ".join(s["fn_skipped"]) or "-"))
    out.append("")
    out.append("KEYS")
    out.append("-" * 70)
    out.append("%-10s %-10s %-26s %-6s %s" % ("Key", "Status", "Received", "ms", "Notes"))
    for k, r in report_rows(template, data):
        out.append("%-10s %-10s %-26s %-6s %s" % (
            k["label"], r["status"], r.get("got") or "-",
            r.get("reaction_ms") if r.get("reaction_ms") is not None else "-",
            "; ".join(_notes(r))))
    if data["fn_results"]:
        out.append("")
        out.append("FN / ACTION KEYS")
        out.append("-" * 70)
        for r in data["fn_results"]:
            out.append("%-14s %-8s %-10s %s" % (r["keys"], r["status"], r["answer"],
                                                ", ".join(r["received"]) or "-"))
    if data["unexpected"]:
        out.append("")
        out.append("UNEXPECTED KEY PRESSES (between prompts)")
        out.append("-" * 70)
        for u in data["unexpected"]:
            out.append("%s  %-8s %s" % (u["time"], u["phase"], u["key"]))
    out.append("")
    out.append("Full keystroke log: %d events, see the .json / .keylog.csv file" % len(data["keylog"]))
    out.append("Devices: " + "; ".join("%s (%s)" % (d["name"], d["path"]) for d in data["devices"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def write_html(path, template, data, s):
    m = data["machine"]
    e = html.escape
    U = 46
    colors = {"PASS": "#3fb950", "NOT TESTED": "#bbb", "na": "#8aa4c8"}
    keys_html = []
    for k in template["keys"]:
        kid = k["mirror_id"] or k["id"]
        if k["test"] or k["mirror_id"]:
            st = data["results"].get(kid, {}).get("status", "NOT TESTED")
        else:
            st = "na"
        bg = colors.get(st, "#e5534b")
        title = st if st != "na" else "not tested"
        keys_html.append(
            '<div class="k" title="%s" style="left:%dpx;top:%dpx;width:%dpx;background:%s">%s</div>'
            % (e(title), k["x"] * U, k["row"] * U, k["w"] * U - 4, bg, e(k["label"])))
    n_rows = max(k["row"] for k in template["keys"]) + 1
    units = max(k["x"] + k["w"] for k in template["keys"])
    rows = []
    for k, r in report_rows(template, data):
        cls = "ok" if r["status"] == "PASS" else "bad"
        rows.append("<tr><td>%s</td><td class=%s>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            e(k["label"]), cls, e(r["status"]), e(r.get("got") or "-"),
            r.get("reaction_ms") if r.get("reaction_ms") is not None else "-",
            e("; ".join(_notes(r)))))
    fn_rows = "".join(
        "<tr><td>%s</td><td class=%s>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            e(r["keys"]), "ok" if r["status"] == "PASS" else ("skip" if r["status"] == "SKIPPED" else "bad"),
            e(r["status"]), e(str(r["answer"])), e(", ".join(r["received"]) or "-"), e(r["see"]))
        for r in data["fn_results"])
    verdict_color = {"PASS": "#3fb950", "FAIL": "#e5534b"}.get(s["overall"], "#d29922")
    info = [("Model", model_name(m)), ("Serial", m["serial"] or "-"),
            ("SKU", m["sku"] or "-"), ("BIOS", "%s (%s)" % (m["bios_version"], m["bios_date"])),
            ("Template", template["name"]), ("Started", data.get("started", "-")),
            ("Finished", data.get("finished", "-")), ("Action keys mode", _mode_txt(data)), ("Layout matches", _layout_txt(data)),
            ("Keys passed", "%d / %d" % (s["keys_passed"], s["keys_total"])),
            ("Failed keys", ", ".join(s["keys_failed"]) or "-"),
            ("Passed on retry", ", ".join(s["keys_passed_on_retry"]) or "-"),
            ("Fn failed", ", ".join(s["fn_failed"]) or "-"),
            ("Fn skipped", ", ".join(s["fn_skipped"]) or "-")]
    doc = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Keyboard test %(serial)s</title>
<style>
body{font-family:system-ui,sans-serif;margin:24px;color:#222}
h1{margin:0 0 4px} .verdict{display:inline-block;padding:6px 18px;border-radius:6px;color:#fff;font-weight:bold;font-size:22px;background:%(vc)s}
table{border-collapse:collapse;margin:12px 0} td,th{border:1px solid #ccc;padding:3px 10px;text-align:left;font-size:14px}
th{background:#f0f0f0} .ok{color:#1a7f37;font-weight:bold} .bad{color:#c62828;font-weight:bold} .skip{color:#888}
.kb{position:relative;height:%(kbh)dpx;width:%(kbw)dpx;margin:16px 0;padding:6px;background:#333;border-radius:8px}
.k{position:absolute;height:%(kh)dpx;margin:6px;border-radius:4px;font-size:12px;display:flex;align-items:center;justify-content:center;color:#111}
.info td:first-child{font-weight:bold}
</style></head><body>
<h1>Keyboard test report</h1>
<p><span class="verdict">%(overall)s</span></p>
<table class="info">%(info)s</table>
<div class="kb">%(keys)s</div>
<h2>Keys</h2>
<table><tr><th>Key</th><th>Status</th><th>Received</th><th>ms</th><th>Notes</th></tr>%(rows)s</table>
<h2>Fn / action keys</h2>
<table><tr><th>Keys</th><th>Status</th><th>Answer</th><th>Signals</th><th>Expected</th></tr>%(fn)s</table>
<p style="color:#888;font-size:12px">keyboardtest v%(ver)s &middot; devices: %(devs)s</p>
</body></html>
""" % {"serial": e(m["serial"] or ""), "vc": verdict_color, "overall": e(s["overall"]),
       "kbh": n_rows * U + 4, "kbw": units * U + 4, "kh": U - 4,
       "info": "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(a), e(b)) for a, b in info),
       "keys": "".join(keys_html), "rows": "".join(rows),
       "fn": fn_rows or "<tr><td colspan=5>not run</td></tr>", "ver": VERSION,
       "devs": e("; ".join(d["name"] for d in data["devices"]))}
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def write_reports(template, data, outdir):
    os.makedirs(outdir, exist_ok=True)
    s = summary(template, data)
    data["summary"] = s
    m = data["machine"]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(outdir, "%s_%s_%s" % (slug(m["serial"] or "noserial"),
                                              slug(m["product"] or "unknown"), stamp))
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    out["results"] = [dict(r, key=k["label"]) for k, r in report_rows(template, data)]
    out["template"] = {"name": template["name"], "path": template["path"]}
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    write_txt(base + ".txt", template, data, s)
    write_html(base + ".html", template, data, s)
    with open(base + ".keylog.csv", "w", encoding="utf-8") as f:
        cols = ["t", "time", "event", "key", "code", "scan", "device", "phase", "asked", "orphan", "dropped"]
        f.write(",".join(cols) + "\n")
        for e in data["keylog"]:
            f.write(",".join('"%s"' % str(e[c]).replace('"', "'") if e[c] is not None else ""
                             for c in cols) + "\n")
    paths = [base + ext for ext in (".txt", ".json", ".html", ".keylog.csv")]
    # when run with sudo, hand the files back to the real user
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid and gid:
        for p in paths + [outdir]:
            try:
                os.chown(p, int(uid), int(gid))
            except OSError:
                pass
    return s, paths


# --------------------------------------------------------------------------
# Learn / monitor / list modes
# --------------------------------------------------------------------------

def learn(scr, inp, template, learned):
    ui = UI(scr, template, "Keyboard test - LEARN mode - %s" % template["name"])
    keys = [k for k in template["keys"] if k["test"]]
    inp.abort_enabled = False      # Esc must be learnable
    inp.grab_all()
    for i, k in enumerate(keys, 1):
        end = time.monotonic() + 10
        first = None
        while first is None and time.monotonic() < end:
            rem = end - time.monotonic()
            lines = ["Press this key ONCE on a KNOWN-GOOD keyboard.",
                     "If nothing registers, try it together with Fn."]
            if k["hint"]:
                lines.insert(0, "(%s)" % k["hint"])
            if rem > 9.95:
                beep("go")
            ui.render("LEARN  key %d / %d" % (i, len(keys)), big=k["label"],
                      bar=(rem / 10, "%.0f s (wait = skip)" % rem), lines=lines,
                      current=k["id"], footer="Learn mode: no emergency exit, just wait 10 s per key")
            for ev in inp.events(0.05):
                if ev.value == 1 and ev.code != K_FN:
                    first = ev
                    break
        codes = []
        if first:
            codes.append(first.code)
            end2 = time.monotonic() + 0.4      # collect the rest of a macro sequence
            while time.monotonic() < end2:
                for ev in inp.events(0.05):
                    if ev.value == 1 and ev.code != K_FN and ev.code not in codes:
                        codes.append(ev.code)
            inp.wait_release(2.0)
        learned[k["id"]] = codes
        ui.status[k["id"]] = "pass" if codes else "fail"
        gap(ui, inp, 0.3, {"unexpected": []}, "learn")
    inp.ungrab_all()


def save_learned(template, learned, machine):
    with open(template["path"], encoding="utf-8") as f:
        raw = json.load(f)
    for r, row in enumerate(raw["rows"]):
        for i, k in enumerate(row):
            kid = "r%dk%d" % (r, i)
            if kid not in learned:
                continue
            codes = learned[kid]
            if not codes:
                k["note"] = "not detected during learn - unchanged"
                continue
            label_is_mod = any(key_code(n) in MODIFIERS for n in k.get("codes", []))
            main = [c for c in codes if label_is_mod or c not in MODIFIERS]
            mods = [c for c in codes if c in MODIFIERS]
            if main:
                k["codes"] = sorted(set(k.get("codes", [])) | {key_name(main[0])})
            elif mods:
                k["combo"] = sorted(key_name(c) for c in mods)
            k["learned"] = [key_name(c) for c in codes]
    raw["name"] = raw["name"] + " (learned)"
    raw["learned_from"] = {"product": machine["product"], "serial": machine["serial"],
                           "date": now_iso()}
    raw["match"] = []          # use explicitly with --template until reviewed
    out = os.path.join(HERE, "templates", "learned_%s_%s.json" % (
        slug(machine["product"]), datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid and gid:
        try:
            os.chown(out, int(uid), int(gid))
        except OSError:
            pass
    return out


def monitor(inp):
    print("Monitoring (no grab). Ctrl+C to quit.")
    for d in inp.devices:
        print("  %-18s %s" % (d.path, d.name))
    inp.abort_enabled = False
    try:
        while True:
            for ev in inp.events(1.0):
                print("%-5s %-24s code=%-7s scan=%-6s %s" % (
                    "down" if ev.value else "up", ev.name, hex(ev.code),
                    hex(ev.scan) if ev.scan is not None else "-", ev.dev.name), flush=True)
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Laptop keyboard tester (Linux).")
    ap.add_argument("--template", help="template JSON (default: auto-detect from DMI model)")
    ap.add_argument("--layout", help="prefer template with this layout (e.g. hu)")
    ap.add_argument("--timeout", type=float, help="seconds per key (default from template)")
    ap.add_argument("--out", default=os.path.join(HERE, "reports"), help="report directory")
    ap.add_argument("--no-fn", action="store_true", help="skip Fn / action-key tests")
    ap.add_argument("--no-retry", action="store_true", help="don't offer retry of failed keys")
    ap.add_argument("--include-usb", action="store_true", help="also use USB keyboards")
    ap.add_argument("--device", action="append", help="only use this device (path or name part)")
    ap.add_argument("--beep", default="auto", choices=["auto", "sound", "pcspkr", "bell", "off"],
                    help="beep when a key must be pressed (default: auto)")
    ap.add_argument("--learn", action="store_true", help="record key codes into a new template")
    ap.add_argument("--monitor", action="store_true", help="print raw key events")
    ap.add_argument("--list", action="store_true", help="list keyboard devices and exit")
    args = ap.parse_args()

    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")

    if args.list:
        for d in scan_devices():
            if d.get("path"):
                print("%s %-18s %-6s %s" % ("*" if is_keyboard_like(d, args.include_usb) else " ",
                                            d["path"], "0x%02x" % (d.get("bus") or 0),
                                            d.get("name")))
        print("\n* = used by the test")
        return

    inp = Input(open_devices(args.include_usb, args.device))
    global BEEPER
    if not args.monitor:
        BEEPER = Beeper(args.beep)
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(Abort()))
    try:
        if args.monitor:
            monitor(inp)
            return

        machine = machine_info()
        if args.template:
            tpath = args.template
        else:
            found = find_template(machine, args.layout)
            if not found:
                sys.exit("No template matches model '%s'. Use --template FILE." % machine["product"])
            if len(found) > 1:
                print("Several templates match, using %s (others: %s)" % (found[0], ", ".join(found[1:])))
            tpath = found[0]
        template = load_template(tpath)

        if args.learn:
            learned = {}
            try:
                curses.wrapper(lambda scr: learn(scr, inp, template, learned))
            finally:
                inp.ungrab_all()
            out = save_learned(template, learned, machine)
            print("Learned template written to: %s" % out)
            for k in template["keys"]:
                if k["id"] in learned:
                    print("  %-8s %s" % (k["label"], " ".join(key_name(c) for c in learned[k["id"]]) or "-- nothing --"))
            return

        data = {"tool": "keyboardtest", "version": VERSION, "machine": machine,
                "devices": [d.describe() for d in inp.devices],
                "results": {}, "fn_results": [], "unexpected": [],
                "aborted": False, "action_keys_mode": None, "layout_confirmed": None,
                "keylog": inp.log, "_inp": inp, "_t_gap": 0,
                "beep": BEEPER.method if BEEPER else "off"}
        try:
            curses.wrapper(lambda scr: interactive(scr, inp, template, data, args))
        except Abort:
            data["aborted"] = True
            data.setdefault("finished", now_iso())
        finally:
            inp.ungrab_all()
        s, paths = write_reports(template, data, args.out)
        print("RESULT: %s   keys %d/%d   failed: %s   fn failed: %s" % (
            s["overall"], s["keys_passed"], s["keys_total"],
            ", ".join(s["keys_failed"]) or "-", ", ".join(s["fn_failed"]) or "-"))
        for p in paths:
            print("  " + p)
    finally:
        inp.close()
        if BEEPER is not None:
            BEEPER.close()


if __name__ == "__main__":
    main()
