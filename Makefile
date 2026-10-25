.DEFAULT_GOAL := help

PYTHON := venv/bin/python

.PHONY: help check guardian voice-analyst family verifier scam-intel

help:
	@echo "Run an agent with its project virtual environment:"
	@echo "  make guardian"
	@echo "  make voice-analyst"
	@echo "  make family"
	@echo "  make verifier"
	@echo "  make scam-intel"
	@echo "  make check"

check:
	@test -x $(PYTHON) || (echo "Missing venv. Create it with: python3 -m venv venv && venv/bin/python -m pip install -r requirements.txt"; exit 1)
	@$(PYTHON) -m compileall -q agents services shared
	@$(PYTHON) -c 'import dotenv, uagents; print("Environment and imports are ready.")'

guardian: check
	@$(PYTHON) -m agents.guardian.agent

voice-analyst: check
	@$(PYTHON) -m agents.voice_analyst.agent

family: check
	@$(PYTHON) -m agents.family.agent

verifier: check
	@$(PYTHON) -m agents.verifier.agent

scam-intel: check
	@$(PYTHON) -m agents.scam_intel.agent
