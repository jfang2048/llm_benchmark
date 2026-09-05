# vLLM OpenAI server with GGUF support, pinned to vLLM 0.26.0.
#
# The vllm-gguf-plugin enables loading GGUF checkpoints in vLLM. The plugin
# version is pinned and the build asserts that installing it does not change
# the vLLM version (an assert guards against accidental upgrades).
FROM vllm/vllm-openai:v0.26.0

RUN python3 -m pip install --no-cache-dir "vllm-gguf-plugin==0.0.4" \
  && python3 - <<'PY'
import importlib.metadata as m
v = m.version('vllm')
p = m.version('vllm-gguf-plugin')
print('vllm=', v, 'plugin=', p)
assert v == '0.26.0', f'plugin install changed vLLM version to {v}'
PY
