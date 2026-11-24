"""Generic standalone job launcher for Colab sessions (avoids IPython's running asyncio loop)."""
import json, os, subprocess, sys, tarfile
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
with log_file.open("w", encoding="utf-8") as lf:
    p = subprocess.Popen(cmd, cwd="/content/repo", env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        lf.write(line)
        lf.flush()
        print(line, end="", flush=True)
    rc = p.wait()

if rc != 0:
    raise RuntimeError(f"job {spec['module']} failed with exit code {rc}")
print(f"[run_job] completed successfully (rc=0)", flush=True)
