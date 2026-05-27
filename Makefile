API_DIR := apps/api
PYTHON := $(API_DIR)/.venv/bin/python
UV := uv

.PHONY: report
report:
	@test -n "$(DATE)" || (echo "Usage: make report DATE=YYYY-MM-DD [KIND=close|midday]" && exit 2)
	cd $(API_DIR) && PYTHONPATH=. $(if $(wildcard $(PYTHON)),.venv/bin/python,$(UV) run python) -m app.cli.generate_report --date $(DATE) --kind $(or $(KIND),close)
