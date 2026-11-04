import sys, time, curses
sys.path.insert(0, '/srv/keyboardtest'); sys.dont_write_bytecode = True
import keyboardtest as kt
N = kt.NAME2CODE
class D: name = "fake"
# real 840 G6 behaviour, action-keys mode ON
ACTION = {"F1":["KEY_SWITCHVIDEOMODE"],"F2":["KEY_F2"],"F3":["KEY_BRIGHTNESSDOWN"],"F4":["KEY_BRIGHTNESSUP"],
          "F5":["KEY_MUTE"],"F6":["KEY_VOLUMEDOWN"],"F7":["KEY_VOLUMEUP"],"F8":["KEY_MICMUTE"],"F9":[],
          "F10":["KEY_NUMLOCK"],"F11":[],"F12":["KEY_LEFTCTRL","KEY_LEFTALT","SCAN_d5"],
          "Call":["KEY_LEFTALT","KEY_PICKUP_PHONE","KEY_LEFTMETA"],
          "Hangup":["KEY_LEFTCTRL","KEY_LEFTALT","KEY_HANGUP_PHONE"],"W":["KEY_E"],"Screen":["KEY_LEFTCTRL","KEY_LEFTALT"],"Q":["KEY_LEFTSHIFT"]}
def press(names):
    evs=[kt.Event(0,D,kt.key_code(n),1) for n in names]+[kt.Event(0,D,kt.key_code(n),0) for n in reversed(names)]
    return evs
class FakeInput(kt.Input):
    def __init__(s): kt.Input.__init__(s, []); s.q=[]
    def grab_all(s): pass
    def ungrab_all(s): pass
    def wait_release(s,t=0): pass
    def drain(s): s.q=[]
    def events(s, timeout):
        time.sleep(min(timeout,0.01))
        if not s.q: return []
        e=s.q.pop(0); s._log(D, time.time(), e.code, e.value, None); return [e]
inp=FakeInput(); asked=[]
orig=kt.UI.render
def render(self, phase, big=None, **kw):
    orig(self, phase, big=big, **kw)
    if inp.q: return
    if phase=="Ready": inp.q=press(["KEY_SPACE"])
    elif phase=="Layout check":
        if not hasattr(self,"d2"):
            self.d2=1; h,w=self.scr.getmaxyx()
            open("screen_layout.txt","w").write("\n".join(self.scr.instr(y,0,w).decode("utf-8","replace").rstrip() for y in range(h)))
        inp.q=press(["KEY_ENTER"])
    elif phase.startswith("Failed key"):
        if not hasattr(self,"d3"):
            self.d3=1; h,w=self.scr.getmaxyx()
            open("screen_failed.txt","w").write("\n".join(self.scr.instr(y,0,w).decode("utf-8","replace").rstrip() for y in range(h)))
        inp.q=press(["KEY_ENTER" if big=="Q" else "KEY_BACKSPACE"])
    elif phase=="Failed keys": inp.q=press(["KEY_SPACE"])
    elif phase.startswith("Fn / action keys") and not kw.get("bar"):
        if "Finished" not in phase and big is None: inp.q=press(["KEY_ENTER"])
    elif phase.startswith("Key test") and kw.get("bar"):
        if big=="Q" and not hasattr(self,"dumped"):
            self.dumped=1; h,w=self.scr.getmaxyx()
            open("screen.txt","w").write("\n".join(self.scr.instr(y,0,w).decode("utf-8","replace").rstrip() for y in range(h)))
        asked.append(big)
        if big.startswith("Fn + "):
            inp.q=press(["KEY_"+big[5:]]); return
        k=next(k for k in self.t["keys"] if k["test"] and (k["label"]==big or k["name"]==big)); big=k["label"]
        names = ACTION[big] if big in ACTION else k["code_names"]
        inp.q=press(names) if names else []
        if not names: inp.q=[]   # silent key: nothing happens -> timeout
    elif phase.startswith("Fn / action keys") and kw.get("bar"):
        if big=="Fn + F1": inp.q=press(["KEY_F1"])
        elif big=="Fn + Right Shift": inp.q=press(["KEY_SYSRQ"])
        elif big=="F11": inp.q=press(["KEY_ENTER"])              # firmware key, user confirms
        else: inp.q=press(ACTION[big])+press(["KEY_ENTER"])
    elif phase=="Finished": inp.q=press(["KEY_ENTER"])
kt.UI.render=render
kt.BEEPER=kt.Beeper("off")
m=kt.machine_info(); t=kt.load_template(kt.find_template(m)[0])
class A: timeout=0.4; no_retry=False; no_fn=False
data={"layout_confirmed":None,"keylog":inp.log,"_inp":inp,"_t_prompt":0,"tool":"x","version":kt.VERSION,"machine":m,"devices":[],"results":{},"fn_results":[],"unexpected":[],"aborted":False,"action_keys_mode":None}
curses.wrapper(lambda scr: kt.interactive(scr, inp, t, data, A))
s,paths=kt.write_reports(t,data,sys.argv[1])
print("ASKED top row:", [a for a in asked][:18])
print(s); print(paths[0])
