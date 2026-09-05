# Reproducible Local LLM Inference Benchmark
#
# Targets:
#   make preflight        Validate the machine (GPU, Docker, ports, models)
#   make setup            Download models and build serving images
#   make deploy           Create the benchmark serving containers
#   make healthcheck      Verify every serving endpoint is API-ready
#   make benchmark        Run the full validated benchmark matrix (mode=final)
#   make benchmark-smoke  Run a fast smoke benchmark (mode=smoke)
#   make report           Rebuild the interactive report + static charts from data
#   make reproduce        One-command end-to-end reproduction (preflight->report)
#   make security         Run the pre-push security/privacy checker
#   make clean            Tear down benchmark containers (does not delete models)

SHELL := /bin/bash
SCRIPTS := scripts

.PHONY: help preflight setup deploy healthcheck benchmark benchmark-smoke benchmark-reliability benchmark-capacity benchmark-shape benchmark-openloop benchmark-startup benchmark-soak benchmark-sessions benchmark-backend report report-v2 reproduce security clean

help:
	@printf '%s\n' \
	  "Reproducible Local LLM Inference Benchmark" \
	  "" \
	  "  make preflight        Validate the machine (GPU, Docker, ports, models)" \
	  "  make setup            Download models and build serving images" \
	  "  make deploy           Create the benchmark serving containers" \
	  "  make healthcheck      Verify every serving endpoint is API-ready" \
	  "  make benchmark        Run the full validated benchmark matrix (final)" \
	  "  make benchmark-smoke  Run a fast smoke benchmark" \
	  "  make benchmark-reliability  Run the P0 transport-reliability gate" \
	  "  make benchmark-capacity     Run the P2 capacity discovery sweep" \
	  "  make benchmark-shape        Run the P3 ISL/OSL token-shape benchmark" \
	  "  make benchmark-openloop     Run the P4 open-loop + goodput benchmark" \
	  "  make benchmark-startup      Run the P5 process cold-start measurement" \
	  "  make benchmark-soak         Run the P5 sustained-load soak benchmark" \
	  "  make benchmark-sessions     Run the P7 multi-turn sessions benchmark" \
	  "  make benchmark-backend      Run the P8 llama.cpp vs vLLM+GGUF comparison" \
	  "  make report           Rebuild the interactive report from committed data" \
	  "  make report-v2        Rebuild the Benchmark v2 dashboard from v2 run data" \
	  "  make reproduce        One-command end-to-end reproduction" \
	  "  make security         Run the pre-push security/privacy checker" \
	  "  make clean            Tear down benchmark containers"

preflight:
	./$(SCRIPTS)/preflight.sh

setup:
	./$(SCRIPTS)/download_models.sh
	./$(SCRIPTS)/build.sh

deploy:
	./$(SCRIPTS)/deploy.sh

healthcheck:
	./$(SCRIPTS)/healthcheck.sh

benchmark:
	MODE=final ./$(SCRIPTS)/benchmark.sh

benchmark-smoke:
	MODE=smoke ./$(SCRIPTS)/benchmark.sh

benchmark-reliability:
	MODE=reliability ./$(SCRIPTS)/benchmark.sh

benchmark-capacity:
	MODE=capacity ./$(SCRIPTS)/benchmark.sh

benchmark-shape:
	MODE=shape ./$(SCRIPTS)/benchmark.sh

benchmark-openloop:
	MODE=open-loop ./$(SCRIPTS)/benchmark.sh

benchmark-startup:
	MODE=startup ./$(SCRIPTS)/benchmark.sh

benchmark-soak:
	MODE=soak ./$(SCRIPTS)/benchmark.sh

benchmark-sessions:
	MODE=sessions ./$(SCRIPTS)/benchmark.sh

benchmark-backend:
	MODE=backend ./$(SCRIPTS)/benchmark.sh

report:
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/generate_report.py; \
	else python3 $(SCRIPTS)/generate_report.py; fi
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/generate_v2_report.py; \
	else python3 $(SCRIPTS)/generate_v2_report.py; fi

report-v2:
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/generate_v2_report.py; \
	else python3 $(SCRIPTS)/generate_v2_report.py; fi

reproduce:
	./$(SCRIPTS)/reproduce.sh

security:
	./$(SCRIPTS)/security_check.sh

clean:
	./$(SCRIPTS)/cleanup.sh
