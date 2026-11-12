"""Запуск: python -m detect run [--respond R3] [--seed N] [--quiet]

Поднимает локальный блокчейн anvil, разворачивает контракты, проигрывает сценарий
(легитимный трафик и атаки), после каждой транзакции опрашивает монитор и печатает метрики правил.
"""
import argparse
import shutil
import socket
import subprocess
import sys
import time

from web3 import HTTPProvider, Web3

from . import evaluate, scenario
from .monitor import Monitor
from .rules import RULES


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_anvil():
    if not shutil.which('anvil'):
        sys.exit('anvil не найден: установите Foundry (README, раздел "Подготовка среды")')
    port = free_port()
    proc = subprocess.Popen(['anvil', '--port', str(port), '--accounts', '12', '--silent'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w3 = Web3(HTTPProvider(f'http://127.0.0.1:{port}', request_kwargs={'timeout': 30}))
    for _ in range(150):
        if w3.is_connected():
            return proc, w3
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    proc.kill()
    sys.exit('anvil не запустился за 15 с')


def run(w3, seed, respond, quiet):
    world = scenario.setup(w3)
    steps = scenario.build_plan(world, seed)
    monitor = Monitor(w3, world.vault, world.owner, {world.owner, world.ops}, w3.eth.block_number + 1)
    labels, pause = {}, None
    for step in steps:
        receipt = scenario.mined(w3, step.send())
        labels[w3.to_hex(receipt.transactionHash)] = step
        for alert in monitor.poll():
            if alert.rule in respond and pause is None:
                fn = world.vault.functions.pause()
                receipt = scenario.mined(w3, fn.transact({'from': world.guardian, 'gas': scenario.GAS}))
                labels[w3.to_hex(receipt.transactionHash)] = scenario.Step('Vault.pause guardian')
                pause = (receipt.blockNumber, alert)
    monitor.poll()
    print(evaluate.report(monitor, labels, RULES, pause, quiet))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m detect')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('run', help='сценарий, монитор и метрики правил')
    p.add_argument('--respond', metavar='ПРАВИЛА',
                   help='guardian ставит Vault на паузу по первой тревоге этих правил, например R3 или R1,R3')
    p.add_argument('--seed', type=int, default=2026, help='seed легитимного трафика')
    p.add_argument('--quiet', action='store_true', help='без журнала тревог')
    args = parser.parse_args(argv)

    respond = set(args.respond.split(',')) if args.respond else set()
    unknown = respond - {rule_id for rule_id, _, _ in RULES}
    if unknown:
        parser.error(f'неизвестные правила: {", ".join(sorted(unknown))}')

    proc, w3 = start_anvil()
    try:
        run(w3, args.seed, respond, args.quiet)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == '__main__':
    main()
