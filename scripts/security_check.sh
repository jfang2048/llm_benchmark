#!/usr/bin/env bash
# Pre-push security / privacy / repo-hygiene gate.
# Exits non-zero if any tracked file contains forbidden material.
#
# Checks: model binaries, oversized files, .env, private keys, token patterns,
# private home paths, raw cache dirs, backup files, CJK (non-English) text.
# Run before every push and in CI.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; FAIL=1; }
ok(){ printf '[PASS] %s\n' "$*"; }

# Tracked file list (the publication allowlist). Fall back to scanning the
# working tree if nothing is staged/committed yet.
TRACKED="$(git ls-files 2>/dev/null)"
if [[ -z "$TRACKED" ]]; then
  echo "[INFO] nothing tracked yet; scanning staged files + working tree (respecting .gitignore)"
  FILES="$(git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)"
else
  FILES="$TRACKED"
fi

echo "== Forbidden file types =="
bad="$(printf '%s\n' "$FILES" | grep -E '\.(gguf|safetensors|bin|pt|pth|ckpt|ggml)(\.|$)' || true)"
[[ -z "$bad" ]] && ok "no model binaries tracked" || { fail "model binaries: $bad"; }

echo "== Oversized files (> 5 MiB) =="
big=""
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  sz=$(stat -c %s "$f" 2>/dev/null || echo 0)
  if (( sz > 5242880 )); then big="$big $f ($((sz/1024/1024)) MiB)"; fi
done <<< "$FILES"
[[ -z "$big" ]] && ok "no file exceeds 5 MiB" || { fail "oversized: $big"; }

echo "== Secrets and private material =="
secrets="$(printf '%s\n' "$FILES" | grep -E '(^|/)\.env$|\.env\.(local|prod|dev)$' || true)"
[[ -z "$secrets" ]] && ok "no .env files tracked" || { fail ".env tracked: $secrets"; }

privkeys="$(printf '%s\n' "$FILES" | grep -E '\.(pem|key|p12|pfx)$' || true)"
[[ -z "$privkeys" ]] && ok "no key files tracked" || { fail "key files: $privkeys"; }

echo "== Secret token / password patterns in tracked content =="
# KEY= patterns require a non-empty value so that empty placeholders in
# .env.example / config.env.example do not false-positive.
pat='(Authorization:[[:space:]]*Bearer|HF_TOKEN=[^[:space:]]|HUGGING_FACE_HUB_TOKEN=[^[:space:]]|GITHUB_TOKEN=[^[:space:]]|OPENAI_API_KEY=[^[:space:]]|API_KEY=[^[:space:]]|PASSWORD=[^[:space:]]|SECRET=[^[:space:]]|BEGIN (OPENSSH|RSA|EC|DSA) PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})'
hits=""
SELF="scripts/security_check.sh"
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  [[ "$f" == "$SELF" ]] && continue   # the checker contains its own pattern text
  if grep -rniE "$pat" "$f" >/dev/null 2>&1; then hits="$hits $f"; fi
done <<< "$FILES"
[[ -z "$hits" ]] && ok "no token/password patterns" || { fail "token/password pattern in: $hits"; }

echo "== Private home paths / machine identifiers =="
hits2=""
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  if grep -rniE '/home/[a-z_][a-z0-9_]*|/Users/[a-zA-Z0-9_]+' "$f" >/dev/null 2>&1; then hits2="$hits2 $f"; fi
done <<< "$FILES"
[[ -z "$hits2" ]] && ok "no private home paths" || { fail "private home path in: $hits2"; }

echo "== Backup / temp files =="
bak="$(printf '%s\n' "$FILES" | grep -E '\.(bak|orig|tmp|swp)$|\.before-' || true)"
[[ -z "$bak" ]] && ok "no backup files tracked" || { fail "backup files: $bak"; }

echo "== Raw cache directories =="
cache="$(printf '%s\n' "$FILES" | grep -E '(^|/)(hf-cache|vllm-cache|torch_compile_cache|__pycache__)/' || true)"
[[ -z "$cache" ]] && ok "no cache dirs tracked" || { fail "cache dirs: $cache"; }

echo "== Non-English (CJK) text =="
cjk=""
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  if LC_ALL=C grep -nP '[\x{4E00}-\x{9FFF}\x{3040}-\x{30FF}\x{AC00}-\x{D7AF}]' "$f" >/dev/null 2>&1; then cjk="$cjk $f"; fi
done <<< "$FILES"
[[ -z "$cjk" ]] && ok "no CJK text in tracked files" || { fail "CJK text in: $cjk"; }

echo
if (( FAIL )); then
  echo "Security check FAILED. Fix the items above before committing/pushing."
  exit 1
fi
echo "Security check PASSED (allowlist size: $(printf '%s\n' "$FILES" | grep -c .) files)."
exit 0
