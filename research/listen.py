"""Listen for input reports on every readable HID collection of the keyboard."""
import sys, threading, time, hid

VID, PID = 0x0C45, 0x8006
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 40
stop = time.time() + secs


def worker(d):
    dev = hid.device()
    try:
        dev.open_path(d["path"])
    except Exception as e:
        print(f"skip if{d['interface_number']} {d['usage_page']:#x}/{d['usage']:#x}: {e}", flush=True)
        return
    dev.set_nonblocking(True)
    tag = f"if{d['interface_number']} {d['usage_page']:#06x}/{d['usage']:#04x}"
    print("listening", tag, flush=True)
    while time.time() < stop:
        r = dev.read(64)
        if r:
            print(time.strftime("%H:%M:%S"), tag, bytes(r).hex(" "), flush=True)
        time.sleep(0.003)


ts = [threading.Thread(target=worker, args=(d,), daemon=True) for d in hid.enumerate(VID, PID)]
for t in ts: t.start()
for t in ts: t.join()
print("done", flush=True)
