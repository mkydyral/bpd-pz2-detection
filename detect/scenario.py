"""Сценарий: развёртывание контрактов, легитимный трафик и атаки с разметкой (ground truth).

Разметку использует только evaluate.py; монитор её не видит.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ETH = 10**18
CENT = ETH // 100
OUT = Path(__file__).resolve().parent.parent / 'out'

N_BENIGN = 250
PAYROLL_AT = (30, 55, 80, 105, 130, 155, 185, 215)  # номера легитимных транзакций с пакетной выплатой
DUPLICATE_AT = 130  # в этой выплате один получатель дважды (зарплата и премия)
ROTATION_AT = 200  # плановая смена оператора владельцем на адрес из списка разрешённых
EXPLOITS = {90: 'A1', 170: 'A2'}  # атака повторного входа после легитимной транзакции с этим номером
TAKEOVER_AT = 230  # захват роли оператора
SWEEPS_AT = (236, 238, 240)  # вывод средств захваченной ролью
REENTRIES = 3  # повторных входов в одной атаке: ущерб 3 ETH при депозите 1 ETH
SWEEP = 4 * ETH
GAS = 1_000_000  # явный лимит газа: транзакция включается в блок, даже если откатится (например, на паузе)


@dataclass(frozen=True)
class World:
    vault: object
    payroll: object
    attacker_contract: object
    owner: str
    guardian: str
    attacker: str
    ops: str
    users: list


@dataclass(frozen=True)
class Step:
    kind: str
    send: Callable[[], bytes] | None = None
    incident: str | None = None  # 'A1', 'A2', 'B' - атака; None - легитимная транзакция
    phase: str | None = None  # 'exploit', 'takeover', 'sweep'


def artifact(name):
    path = OUT / f'{name}.sol' / f'{name}.json'
    if not path.exists():
        raise SystemExit(f'Нет out/{name}.sol/{name}.json: выполните make build')
    data = json.loads(path.read_text(encoding='utf-8'))
    return data['abi'], data['bytecode']['object']


def mined(w3, tx_hash):
    """Receipt транзакции; anvil включает её в блок за миллисекунды, частый опрос ускоряет сценарий в 4 раза."""
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30, poll_latency=0.005)


def deploy(w3, name, sender, *args):
    abi, bytecode = artifact(name)
    tx_hash = w3.eth.contract(abi=abi, bytecode=bytecode).constructor(*args).transact({'from': sender})
    return w3.eth.contract(address=mined(w3, tx_hash).contractAddress, abi=abi)


def setup(w3):
    a = w3.eth.accounts
    owner, guardian, attacker, ops, users = a[0], a[1], a[2], a[3], a[4:12]
    vault = deploy(w3, 'Vault', owner, guardian)
    payroll = deploy(w3, 'Payroll', owner, vault.address)
    attacker_contract = deploy(w3, 'Attacker', attacker, vault.address)
    return World(vault, payroll, attacker_contract, owner, guardian, attacker, ops, users)


def sender(fn, account, value=0):
    params = {'from': account, 'gas': GAS}
    if value:
        params['value'] = value
    return lambda: fn.transact(params)


def build_plan(w, seed):
    """Список шагов: N_BENIGN легитимных транзакций и вставленные между ними атаки."""
    rng = random.Random(seed)
    v = w.vault
    balance = dict.fromkeys(w.users, 0)  # теневые балансы: суммы выводов всегда корректны

    def benign(i):
        if i < len(w.users):  # начальные депозиты всех участников
            u, amount = w.users[i], rng.randint(500, 2000) * CENT
            balance[u] += amount
            return Step('deposit', sender(v.functions.deposit(), u, amount))
        if i == len(w.users):
            return Step('payroll.fund', sender(w.payroll.functions.fund(), w.owner, 60 * ETH))
        if i in PAYROLL_AT:
            recipients = rng.sample(w.users, 3)
            kind = 'payroll'
            if i == DUPLICATE_AT:
                recipients.append(recipients[0])
                kind = 'payroll, один получатель дважды'
            amounts = [rng.randint(50, 150) * CENT for _ in recipients]
            return Step(kind, sender(w.payroll.functions.pay(recipients, amounts), w.owner))
        if i == ROTATION_AT:
            return Step('setOperator владельцем', sender(v.functions.setOperator(w.ops), w.owner))
        u = rng.choice(w.users)
        action = rng.choices(['deposit', 'withdraw', 'withdrawTo', 'withdrawAll'], weights=[40, 30, 20, 10])[0]
        if balance[u] < CENT:
            action = 'deposit'
        if action == 'deposit':
            amount = rng.randint(10, 500) * CENT
            balance[u] += amount
            return Step(action, sender(v.functions.deposit(), u, amount))
        if action == 'withdrawAll':
            balance[u] = 0
            return Step(action, sender(v.functions.withdrawAll(), u))
        amount = rng.randint(1, balance[u] // CENT) * CENT
        balance[u] -= amount
        if action == 'withdraw':
            return Step(action, sender(v.functions.withdraw(amount), u))
        to = rng.choice([x for x in w.users if x != u])
        return Step(action, sender(v.functions.withdrawTo(to, amount), u))

    steps = []
    for i in range(N_BENIGN):
        steps.append(benign(i))
        if i in EXPLOITS:
            attack = w.attacker_contract.functions.attack(REENTRIES)
            steps.append(Step('Attacker.attack', sender(attack, w.attacker, ETH), EXPLOITS[i], 'exploit'))
        if i == TAKEOVER_AT:
            steps.append(Step('setOperator атакующим', sender(v.functions.setOperator(w.attacker), w.attacker),
                              'B', 'takeover'))
        if i in SWEEPS_AT:
            steps.append(Step('sweep', sender(v.functions.sweep(w.attacker, SWEEP), w.attacker), 'B', 'sweep'))
    return steps
