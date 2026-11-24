"""Generic standalone job launcher for Colab sessions (avoids IPython's running asyncio loop + keeps WS alive)."""
import json, os, selectors, subprocess, sys, tarfile, time
from pathlib import Path

if Path("/content/oca_repo.tar.gz").is_file():
    os.makedirs("/content/repo", exist_ok=True)
    with tarfile.open("/content/oca_repo.tar.gz", "r:gz") as tf:
        tf.extractall("/content/repo", filter="data")

spec = json.loads(Path("/content/job_spec.json").read_text(encoding="utf-8"))
cmd = [sys.executable, "-u", "-m", spec["module"], *spec.get("args", [])]
log_file = Path(spec.get("log_file", "/content/runs/last_job.log"))
log_file.parent.mkdir(parents=True, exist_ok=True)

env = {**os.environ, "PYTHONPATH": "/content/repo", **spec.get("env", {})}
print(f"[run_job] starting: {' '.join(cmd)}", flush=True)
t0 = time.time()
last_out = t0
with log_file.open("w", encoding="utf-8") as lf:
    p = subprocess.Popen(cmd, cwd="/content/repo", env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ)
    while True:
        events = sel.select(timeout=20.0)
        if events:
            line = p.stdout.readline()
            if not line:
                break
            lf.write(line)
            lf.flush()
            print(line, end="", flush=True)
            last_out = time.time()
        else:
            if p.poll() is not None:
                rem = p.stdout.read()
                if rem:
                    lf.write(rem)
                    lf.flush()
                    print(rem, end="", flush=True)
                break
            if time.time() - last_out >= 20.0:
                print(f"[run_job heartbeat] elapsed={int(time.time()-t0)}s pid={p.pid}", flush=True)
                last_out = time.time()
    rc = p.wait()

if rc != 0:
    raise RuntimeError(f"job {spec['module']} failed with exit code {rc}")
print(f"[run_job] completed successfully in {int(time.time()-t0)}s (rc=0)", flush=True)
