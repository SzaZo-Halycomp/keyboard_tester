import sys, os, struct, time, curses
sys.path.insert(0, '/srv/keyboardtest'); sys.dont_write_bytecode = True
import keyboardtest as kt
N = kt.NAME2CODE
# --- orphan scan: Enter down normally, release arrives as MSC_SCAN only (as in the real log)
r, w = os.pipe(); os.set_blocking(r, False)
class D(kt.Device):
    def __init__(s):
        s.fd=r; s._last_raw=None; s._pending_scan=None; s._scan_down=set(); s._down=set(); s.name="fake"
        s._keymap={0x1c: N["KEY_ENTER"], 0x6d: 0, 0xf8: N["KEY_UNKNOWN"]}
def ev(t,c,v): return struct.pack(kt.EVENT_FMT,1,0,t,c,v)
os.write(w, b"".join([ev(4,4,0x1c),ev(1,28,1),ev(0,0,0),  ev(4,4,0x1c),ev(0,0,0),      # Enter down, orphan release
                      ev(4,4,0x6d),ev(0,0,0), ev(4,4,0x6d),ev(0,0,0),                     # unmapped key down/up
                      ev(4,4,0xf8),ev(0,0,0)]))
print("decoded:", [(kt.key_name(c), v, hex(sc), o) for t,c,v,sc,o in D().read()])
# --- early press: next key pressed during the gap counts
class F:
    name="fake"
class FakeInput(kt.Input):
    def __init__(s): kt.Input.__init__(s, []); s.q=[]
    def events(s, timeout):
        time.sleep(min(timeout,0.01))
        if not s.q: return []
        e=s.q.pop(0); s._log(F, time.time(), e.code, e.value, None); return [e]
inp=FakeInput()
t=kt.load_template('/srv/keyboardtest/templates/hp_elitebook_840_g5_g6_hu.json')
keys=[k for k in t["keys"] if k["label"] in ("R","T")]
data={"results":{}, "unexpected":[], "action_keys_mode":False, "_inp":inp, "_t_gap":0}
orig=kt.UI.render
def render(self, phase, big=None, **kw):
    orig(self, phase, big=big, **kw)
    if big=="R" and kw.get("bar") and not inp.q:
        inp.q=[kt.Event(0,F,N["KEY_R"],1),kt.Event(0,F,N["KEY_R"],0),
               kt.Event(0,F,N["KEY_T"],1),kt.Event(0,F,N["KEY_T"],0)]   # T typed right after R
kt.UI.render=render
curses.wrapper(lambda scr: kt.run_keys(kt.UI(scr,t,"x"), inp, t, data, keys, 2))
for k in keys:
    r=data["results"][k["id"]]; print(k["label"], r["status"], r.get("early"), r["events"], kt._notes(r))
