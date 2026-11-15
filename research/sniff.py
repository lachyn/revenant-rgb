"""Attach to CZC.Gaming Revenant.exe and log every HID packet it sends/receives.
Output: console + hidlog.txt next to this script."""
import sys, time, pathlib, frida

PROC = "CZC.Gaming Revenant.exe"
LOG = pathlib.Path(__file__).with_name("hidlog.txt")

JS = r"""
const hidHandles = {};
function hex(p, n) {
  if (p.isNull() || n <= 0) return "";
  const b = new Uint8Array(p.readByteArray(Math.min(n, 1100)));
  return Array.from(b, x => x.toString(16).padStart(2, "0")).join(" ");
}
function hook(modName) {
  const m = Process.findModuleByName(modName);
  if (!m) return false;
  if (modName === "hid.dll") {
    for (const fn of ["HidD_SetFeature", "HidD_SetOutputReport"]) {
      const a = m.findExportByName(fn);
      if (a) Interceptor.attach(a, { onEnter(args) {
        send({t: fn, h: args[0].toString(), d: hex(args[1], args[2].toInt32())});
      }});
    }
    for (const fn of ["HidD_GetFeature", "HidD_GetInputReport"]) {
      const a = m.findExportByName(fn);
      if (a) Interceptor.attach(a, {
        onEnter(args) { this.b = args[1]; this.n = args[2].toInt32(); this.h = args[0]; },
        onLeave(r) { send({t: fn, h: this.h.toString(), ok: r.toInt32(), d: hex(this.b, this.n)}); }
      });
    }
  }
  if (modName === "kernel32.dll" || modName === "KERNELBASE.dll") {
    const cf = m.findExportByName("CreateFileW");
    if (cf) Interceptor.attach(cf, {
      onEnter(args) { this.p = args[0].isNull() ? "" : args[0].readUtf16String(); },
      onLeave(r) { if (/vid_0c45/i.test(this.p)) { hidHandles[r.toString()] = this.p; send({t: "open", h: r.toString(), p: this.p}); } }
    });
    const wf = m.findExportByName("WriteFile");
    if (wf) Interceptor.attach(wf, { onEnter(args) {
      const h = args[0].toString();
      if (hidHandles[h]) send({t: "WriteFile", h, d: hex(args[1], args[2].toInt32())});
    }});
    const rf = m.findExportByName("ReadFile");
    if (rf) Interceptor.attach(rf, {
      onEnter(args) { this.h = args[0].toString(); this.b = args[1]; this.n = args[2].toInt32(); },
      onLeave(r) { if (hidHandles[this.h]) send({t: "ReadFile", h: this.h, d: hex(this.b, this.n)}); }
    });
  }
  return true;
}
hook("KERNELBASE.dll");
const pending = ["hid.dll"];
const timer = setInterval(() => {
  for (let i = pending.length - 1; i >= 0; i--) if (hook(pending[i])) { send({t: "hooked", m: pending[i]}); pending.splice(i, 1); }
  if (!pending.length) clearInterval(timer);
}, 200);
"""

def main():
    dev = frida.get_local_device()
    procs = [p for p in dev.enumerate_processes() if "revenant" in p.name.lower()]
    if not procs:
        sys.exit("The CZC.Gaming Revenant program is not running - start it first.")
    print("Attaching to", procs[0].name, procs[0].pid, flush=True)
    session = dev.attach(procs[0].pid)
    f = LOG.open("a", encoding="utf-8")
    def on_msg(msg, _):
        if msg["type"] != "send":
            print(msg); return
        p = msg["payload"]
        line = f"{time.strftime('%H:%M:%S')} {p.get('t'):<20} {p.get('h','')} {p.get('p') or p.get('m') or ''} {p.get('d','')}"
        print(line, flush=True); f.write(line + "\n"); f.flush()
    script = session.create_script(JS)
    script.on("message", on_msg)
    script.load()
    print("Capturing... (Ctrl+C to stop)", flush=True)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
