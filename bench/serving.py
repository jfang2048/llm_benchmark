"""Docker launch, GPU sampling, and temperature checks for the serving suites."""
import subprocess
import time


def start_server(container, image, port, gguf, alias, model_dir, flags):
    args = [
        "docker", "run", "-d", "--name", container,
        "--gpus", "all", "--ipc", "host",
        "-p", f"127.0.0.1:{port}:8000",
        "-v", f"{model_dir}:/models:ro",
        "--entrypoint", "/src/build/bin/llama-server",
        image,
        "--model", f"/models/{gguf}", "--alias", alias,
        "--host", "0.0.0.0", "--port", "8000",
        *flags,
    ]
    return subprocess.run(args, capture_output=True, text=True)

def gpu_metric(metric):
    try:
        query = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={metric}", "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL,
        )
        return int(query.splitlines()[0].strip())
    except (OSError, subprocess.CalledProcessError, IndexError, ValueError):
        return None


def gpu_vram():
    return gpu_metric("memory.used")


def wait_for_temperature(max_temp_c, timeout_s=120):
    start = time.monotonic()
    while True:
        temperature = gpu_metric("temperature.gpu")
        if temperature is None or temperature <= max_temp_c:
            return True
        if time.monotonic() - start >= timeout_s:
            return False
        time.sleep(3)


def oom_check(container):
    result = subprocess.run(["docker", "logs", container], capture_output=True, text=True)
    log = (result.stdout + result.stderr).lower()
    return any(pattern in log for pattern in ("out of memory", "cuda error", "failed to allocate"))


class Telemetry:
    def __init__(self, path):
        self.path = path
        self.proc = None

    def start(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            self.proc = subprocess.Popen(
                ["nvidia-smi",
                 "--query-gpu=timestamp,name,temperature.gpu,utilization.gpu,"
                 "utilization.memory,memory.used,power.draw,clocks.sm,clocks.mem",
                 "--format=csv", "-lms", "500"],
                stdout=stream, stderr=subprocess.DEVNULL,
            )

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None
