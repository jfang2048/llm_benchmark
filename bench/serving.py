"""Shared Docker entry point for local llama.cpp serving."""
import subprocess


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
