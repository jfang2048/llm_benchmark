# Local LLM Inference Benchmark
#
# Primary targets:
#   make setup            Download models and build serving images
#   make smoke            Fast sanity benchmark
#   make benchmark        Run the current primary benchmark (capacity sweep)
#   make report           Rebuild the current dashboard
#   make reproduce        One-command end-to-end reproduction
#   make clean            Tear down benchmark containers
#
# Suites:
#   make capacity         Closed-loop throughput/error sweep vs concurrency
#   make shape            Token-controlled ISL/OSL workload sweep
#   make open-loop        Poisson load + SLO/goodput sweep
#   make startup          Process cold-start latency
#   make soak             Sustained load + thermal degradation
#   make sessions         Multi-turn latency by turn
#   make backend          Engine A/B (llama.cpp vs vLLM+GGUF)
#   make reliability      Transport-reliability gate
#
# Historical:
#   make benchmark-v1     Run the historical v1 model comparison (diagnostic)

SHELL := /bin/bash
SCRIPTS := scripts

.PHONY: help setup smoke benchmark benchmark-8b9b reliability-8b9b shape-8b9b \
	llama-bench benchmark-v1 capacity shape open-loop startup \
	soak sessions backend reliability report report-v1 reproduce security clean \
	preflight deploy healthcheck

help:
	@printf '%s\n' \
	  "Local LLM Inference Benchmark" \
	  "" \
	  "  make setup        Download models and build serving images" \
	  "  make smoke        Fast sanity benchmark" \
	  "  make benchmark    Current primary benchmark (capacity sweep)" \
	  "  make report       Rebuild the current dashboard" \
	  "  make reproduce    One-command end-to-end reproduction" \
	  "  make clean        Tear down benchmark containers" \
	  "" \
	  "Suites:" \
	  "  make capacity / shape / open-loop / startup / soak / sessions / backend" \
	  "  make reliability  Transport-reliability gate" \
	  "" \
	  "Historical: make benchmark-v1"

preflight:
	./$(SCRIPTS)/preflight.sh

setup:
	./$(SCRIPTS)/download_models.sh
	./$(SCRIPTS)/build.sh

deploy:
	./$(SCRIPTS)/deploy.sh

healthcheck:
	./$(SCRIPTS)/healthcheck.sh

smoke:
	MODE=smoke ./$(SCRIPTS)/benchmark.sh

benchmark:
	MODE=capacity ./$(SCRIPTS)/benchmark.sh

# Mainstream 8-9B cohort (current primary): registry-driven runner.
benchmark-8b9b:
	python3 -m bench.runner

reliability-8b9b:
	python3 -m bench.runner --suite reliability

shape-8b9b:
	python3 -m bench.runner --suite shape

llama-bench:
	python3 -m bench.llama_bench

benchmark-v1:
	MODE=final ./$(SCRIPTS)/benchmark.sh

capacity:
	MODE=capacity ./$(SCRIPTS)/benchmark.sh

shape:
	MODE=shape ./$(SCRIPTS)/benchmark.sh

open-loop:
	MODE=open-loop ./$(SCRIPTS)/benchmark.sh

startup:
	MODE=startup ./$(SCRIPTS)/benchmark.sh

soak:
	MODE=soak ./$(SCRIPTS)/benchmark.sh

sessions:
	MODE=sessions ./$(SCRIPTS)/benchmark.sh

backend:
	MODE=backend ./$(SCRIPTS)/benchmark.sh

reliability:
	MODE=reliability ./$(SCRIPTS)/benchmark.sh

report:
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/generate_v2_report.py; \
	else python3 $(SCRIPTS)/generate_v2_report.py; fi

report-v1:
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/generate_report.py; \
	else python3 $(SCRIPTS)/generate_report.py; fi

reproduce:
	./$(SCRIPTS)/reproduce.sh

curate-v2:
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/curate_v2_final.py; \
	else python3 $(SCRIPTS)/curate_v2_final.py; fi

security:
	./$(SCRIPTS)/security_check.sh

clean:
	./$(SCRIPTS)/cleanup.sh
