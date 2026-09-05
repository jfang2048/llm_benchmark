# Model Weights

Model weight files are **not** stored in this repository. They are downloaded
(or provided) into this directory by `scripts/download_models.sh`, which verifies
each file against a pinned SHA256.

| Model | File | Source | SHA256 | Size (approx) |
|---|---|---|---|---|
| Qwen3-4B | `Qwen3-4B-Q4_K_M.gguf` | [Qwen/Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF) | `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5` | ~2.4 GiB |
| Spark-X2.5-4B | `Spark-X2.5-4B-Q4_K_M.gguf` | see below | `7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c` | ~2.6 GiB |

## Qwen3-4B

Auto-downloaded from the official [Qwen GGUF repository](https://huggingface.co/Qwen/Qwen3-4B-GGUF):

```bash
make setup          # or: ./scripts/download_models.sh
```

## Spark-X2.5-4B

The Spark-X2.5-4B weights are released by XHToken (iFLYTEK's Ciyuan Xinghuo
subsidiary): [XHToken/Spark-X2.5-4B](https://huggingface.co/XHToken/Spark-X2.5-4B).

There is **no single canonical public GGUF URL** for the exact Q4_K_M artifact
used in this benchmark, so it is not auto-downloaded. Obtain the file by either:

1. **Copy an existing file** (e.g. from another machine) and let the script
   verify it:
   ```bash
   cp /path/to/Spark-X2.5-4B-Q4_K_M.gguf models/
   ./scripts/download_models.sh   # verifies SHA256
   ```

2. **Convert from the official weights** using the llama.cpp fork that this
   repo builds in `docker/llama-cpp/Dockerfile` (the XHToken fork includes the
   Spark-X2.5 architecture, which upstream llama.cpp does not yet support):
   ```bash
   huggingface-cli download XHToken/Spark-X2.5-4B --local-dir /tmp/spark-src
   # run the convert + quantize scripts from the built spark-x25-llama:cuda13 image
   ```

The expected filename and SHA256 above are the ground truth; anything that
verifies against that hash is the correct artifact.

## License

Model weights are governed by their own upstream licenses. This repository does
not claim any rights over them and does not redistribute them. See the upstream
model cards for terms:

- Qwen3: https://huggingface.co/Qwen/Qwen3-4B-GGUF
- Spark-X2.5: https://huggingface.co/XHToken/Spark-X2.5-4B

`models/` and its contents are git-ignored (`*.gguf`).
