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

.PHONY: help preflight setup deploy healthcheck benchmark benchmark-smoke report reproduce security clean

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
	  "  make report           Rebuild the interactive report from committed data" \
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

report:
	@if [ -x .venv/bin/python ]; then .venv/bin/python $(SCRIPTS)/generate_report.py; \
	else python3 $(SCRIPTS)/generate_report.py; fi

reproduce:
	./$(SCRIPTS)/reproduce.sh

security:
	./$(SCRIPTS)/security_check.sh

clean:
	./$(SCRIPTS)/cleanup.sh
