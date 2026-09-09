# Local LLM Inference Benchmark
#
# Registry-driven cohorts (see configs/models.json):
#   mainstream_8_9b   Qwen3-8B, DeepSeek-R1-Distill-Llama-8B, GLM-4-9B-0414,
#                     Yi-1.5-9B-Chat  (IQ4_XS, upstream llama.cpp)
#   spark_reference   Spark-X2.5-4B    (IQ4_XS, XHToken llama.cpp fork)
#
# Primary targets:
#   make setup        Download models and build serving images
#   make smoke        Fast admission sanity check (serve + smoke)
#   make benchmark    Mainstream 8-9B capacity sweep
#   make spark        Spark reference capacity sweep
#   make reliability  Transport-reliability gate (both cohorts)
#   make shape        Token-controlled ISL/OSL workload sweep (both cohorts)
#   make open-loop    Poisson load + SLO/goodput sweep (both cohorts)
#   make startup      Cold-start latency (both cohorts)
#   make soak         Sustained load + thermal degradation (both cohorts)
#   make sessions     Multi-turn latency (both cohorts)
#   make llama-bench  Microbenchmark with the pinned llama.cpp binary
#   make report       Rebuild the current dashboard
#   make reproduce    End-to-end reproduction (both cohorts + dashboard)
#   make clean        Tear down benchmark containers
#
# Historical: make benchmark-v1 (old Spark-vs-Qwen3-4B shell comparison)

SHELL := /bin/bash
ROOT  := $(shell pwd)

# AIPerf CLI; override with `make AIPERF=aiperf` if it is already on your PATH.
AIPERF ?= $(HOME)/venvs/aiperf/bin/aiperf
RUNNER  = AIPERF="$(AIPERF)" python3 -m bench.runner
COHORTS = mainstream_8_9b spark_reference

# Capability-evaluation python (.venv-eval/, created by eval-setup).
EVALPY ?= .venv-eval/bin/python

.PHONY: help setup smoke benchmark spark reliability shape open-loop startup \
	soak sessions llama-bench report reproduce clean benchmark-v1 \
	eval-setup eval-admit eval-code eval-livecodebench eval-swe eval-deepswe \
	eval-multilingual eval-terminal eval-live eval-frontier eval-report \
	eval-standard eval-all

help:
	@printf '%s\n' \
	  "Local LLM Inference Benchmark" \
	  "" \
	  "Primary cohorts: mainstream_8_9b (8-9B) + spark_reference (Spark-X2.5-4B)" \
	  "" \
	  "  make setup        Download models and build serving images" \
	  "  make smoke        Fast admission sanity check" \
	  "  make benchmark    Mainstream 8-9B capacity sweep" \
	  "  make spark        Spark reference capacity sweep" \
	  "  make reliability  Transport-reliability gate (both cohorts)" \
	  "  make shape        ISL/OSL workload sweep (both cohorts)" \
	  "  make open-loop    Poisson load + goodput sweep (both cohorts)" \
	  "  make startup      Cold-start latency (both cohorts)" \
	  "  make soak         Sustained load + thermal degradation (both cohorts)" \
	  "  make sessions     Multi-turn latency (both cohorts)" \
	  "  make llama-bench  llama.cpp microbenchmark" \
	  "  make report       Rebuild the current dashboard" \
	  "  make reproduce    End-to-end reproduction" \
	  "  make clean        Tear down benchmark containers" \
	  "" \
	  "Coding / SWE capability (separate layer):" \
	  "  make eval-setup        Build .venv-eval + pin external benchmarks" \
	  "  make eval-admit        Context + agent-harness admission (all models)" \
	  "  make eval-code         EvalPlus (HumanEval+/MBPP+) all models" \
	  "  make eval-livecodebench LiveCodeBench (LOCAL PROTOCOL, n=1)" \
	  "  make eval-swe          SWE-bench Verified Local-20" \
	  "  make eval-deepswe      DeepSWE Local-10" \
	  "  make eval-multilingual SWE-bench Multilingual Local-18" \
	  "  make eval-terminal     Terminal-Bench Local-10" \
	  "  make eval-live         SWE-bench-Live Local-10" \
	  "  make eval-report       Regenerate capability dashboard data" \
	  "  make eval-standard     The feasible local standard suite" \
	  "" \
	  "Historical: make benchmark-v1"

setup:
	./scripts/build.sh
	./scripts/download_models.sh

smoke:
	./scripts/admit.sh

benchmark:
	$(RUNNER) --cohort mainstream_8_9b --suite capacity

spark:
	$(RUNNER) --cohort spark_reference --suite capacity

reliability:
	@for c in $(COHORTS); do $(RUNNER) --cohort $$c --suite reliability || exit 1; done

shape:
	@for c in $(COHORTS); do $(RUNNER) --cohort $$c --suite shape || exit 1; done

open-loop:
	@for c in $(COHORTS); do $(RUNNER) --cohort $$c --suite open-loop || exit 1; done

startup:
	@for c in $(COHORTS); do $(RUNNER) --cohort $$c --suite startup || exit 1; done

soak:
	@for c in $(COHORTS); do $(RUNNER) --cohort $$c --suite soak || exit 1; done

sessions:
	@for c in $(COHORTS); do $(RUNNER) --cohort $$c --suite sessions || exit 1; done

llama-bench:
	python3 -m bench.llama_bench

report:
	python3 scripts/generate_current_report.py

# --- Coding / SWE capability evaluation (separate from serving) ---
# Canonical model arms (short form; see configs/models.json).
EVAL_ARMS = qwen3_8b deepseek_r1_8b glm4_9b yi_15_9b spark_llama

eval-setup:
	./scripts/eval_setup.sh

eval-admit:
	@for a in $(EVAL_ARMS); do \
		$(EVALPY) evals/admit.py context $$a || true; \
		$(EVALPY) evals/admit.py agent $$a || true; done

eval-code:
	EVALPY="$(EVALPY)" ./scripts/eval_code.sh

eval-livecodebench:
	@for a in $(EVAL_ARMS); do $(EVALPY) evals/livecodebench.py run $$a || true; done

eval-swe:
	@for a in $(EVAL_ARMS); do $(EVALPY) evals/swe.py run $$a || true; done

eval-deepswe:
	@for a in $(EVAL_ARMS); do $(EVALPY) evals/deepswe.py run $$a || true; done

eval-multilingual:
	@for a in $(EVAL_ARMS); do $(EVALPY) evals/multilingual.py run $$a || true; done

eval-terminal:
	@for a in $(EVAL_ARMS); do $(EVALPY) evals/terminal.py run $$a || true; done

eval-live:
	@for a in $(EVAL_ARMS); do $(EVALPY) evals/live.py run $$a || true; done

eval-frontier:
	@echo "SWE-bench Pro: DEFERRED (task-quality review). SWE-EVO: deferred."

eval-report:
	python3 scripts/eval_report.py
	python3 scripts/generate_current_report.py

# Local standard suite (feasible on this laptop; frontier pilots NOT included).
eval-standard: eval-code eval-livecodebench eval-swe eval-deepswe eval-multilingual eval-terminal eval-report

eval-all: eval-setup eval-standard

reproduce:
	./scripts/reproduce.sh

clean:
	./scripts/cleanup.sh

benchmark-v1:
	MODE=final ./scripts/benchmark.sh
