.PHONY: setup check build run run-respond need-uv

setup: need-uv       ## Python 3.12 и web3 в .venv по uv.lock
	uv sync --locked

check: need-uv       ## проверка среды; результат - check-result-pz2.txt
	uv run --locked python scripts/check_env.py

build:
	forge build

run: need-uv build   ## сценарий: anvil, трафик, атаки, монитор, метрики правил
	uv run --locked python -m detect run

run-respond: need-uv build  ## то же, guardian ставит хранилище на паузу по срабатыванию R3
	uv run --locked python -m detect run --respond R3

need-uv:
	@command -v uv >/dev/null 2>&1 || { echo "uv не установлен - см. README, раздел 'Подготовка среды'"; exit 1; }
