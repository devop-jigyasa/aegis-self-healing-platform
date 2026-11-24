.PHONY: all setup test lint chaos-oom chaos-crash chaos-reset clean help

help:
	@echo "AEGIS Platform Commands:"
	@echo "  make setup        - Bootstrap local Kind cluster, build images & deploy manifests"
	@echo "  make test         - Run automated unit and integration tests"
	@echo "  make lint         - Run flake8 code quality scans"
	@echo "  make chaos-oom    - Trigger OOMKill memory spike scenario"
	@echo "  make chaos-crash  - Trigger CrashLoopBackOff scenario"
	@echo "  make chaos-reset  - Reset all chaos flags to nominal health"
	@echo "  make clean        - Tear down local Kind cluster and remove local images"

setup:
	@bash scripts/setup-cluster.sh

test:
	python -m pytest tests/ -v

lint:
	python -m flake8 app/ controller/ tests/ --count --max-line-length=135 --statistics

chaos-oom:
	@bash scripts/inject-chaos.sh oom

chaos-crash:
	@bash scripts/inject-chaos.sh crash

chaos-reset:
	@bash scripts/inject-chaos.sh reset

clean:
	@bash scripts/cleanup.sh
