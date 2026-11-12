"""Монитор: читает новые блоки, разбирает события Vault, обновляет состояние и применяет правила.

Монитор использует только данные блокчейна; разметку сценария он не видит.
"""
from dataclasses import dataclass

from eth_utils.abi import event_abi_to_log_topic

from .rules import RULES


@dataclass(frozen=True)
class Event:
    name: str
    args: dict


@dataclass(frozen=True)
class Tx:
    hash: str
    block: int
    sender: str
    status: int
    events: tuple


@dataclass(frozen=True)
class Alert:
    rule: str
    tx: Tx
    message: str


class Context:
    """Состояние, доступное правилам (описание полей - в rules.py)."""

    def __init__(self, vault, owner, allowlist, vault_eth):
        self._vault = vault
        self.owner = owner
        self.allowlist = frozenset(allowlist)
        self.balances = {}
        self.vault_eth = vault_eth
        self.total_balances = 0
        self.deficit = 0
        self.prev_deficit = 0
        self.block = 0

    def balance_before(self, account):
        return self._vault.functions.balanceOf(account).call(block_identifier=self.block - 1)


class Monitor:
    def __init__(self, w3, vault, owner, allowlist, start_block):
        self.w3 = w3
        self.vault = vault
        self.ctx = Context(vault, owner, allowlist, w3.eth.get_balance(vault.address, start_block - 1))
        self.next_block = start_block
        self.txs = []
        self.alerts = []
        self.eth_outflow = {}  # хэш -> уменьшение ETH в Vault за транзакцию, wei
        self._topics = {event_abi_to_log_topic(a): a['name'] for a in vault.abi if a['type'] == 'event'}

    def poll(self):
        """Обрабатывает все новые блоки и возвращает новые тревоги."""
        new = []
        latest = self.w3.eth.block_number
        while self.next_block <= latest:
            block = self.w3.eth.get_block(self.next_block)
            for tx_hash in block.transactions:
                new.extend(self._process(self.w3.eth.get_transaction_receipt(tx_hash)))
            self.next_block += 1
        return new

    def _process(self, receipt):
        events = (self._decode(log) for log in receipt.logs if log.address == self.vault.address)
        tx = Tx(self.w3.to_hex(receipt.transactionHash), receipt.blockNumber, receipt['from'],
                receipt.status, tuple(e for e in events if e))
        self.txs.append(tx)
        self._update_state(tx)
        alerts = []
        for rule_id, _, rule in RULES:
            message = rule(tx, self.ctx)
            if message:
                alerts.append(Alert(rule_id, tx, message))
        self.alerts.extend(alerts)
        return alerts

    def _decode(self, log):
        name = self._topics.get(bytes(log.topics[0]))
        if name is None:
            return None
        return Event(name, dict(getattr(self.vault.events, name)().process_log(log).args))

    def _update_state(self, tx):
        ctx = self.ctx
        ctx.block = tx.block
        touched = {e.args['account'] for e in tx.events if e.name in ('Deposit', 'Withdrawal')}
        for account in touched:
            ctx.balances[account] = self.vault.functions.balanceOf(account).call(block_identifier=tx.block)
        before = ctx.vault_eth
        ctx.vault_eth = self.w3.eth.get_balance(self.vault.address, tx.block)
        self.eth_outflow[tx.hash] = before - ctx.vault_eth
        ctx.total_balances = sum(ctx.balances.values())
        ctx.prev_deficit = ctx.deficit
        ctx.deficit = ctx.total_balances - ctx.vault_eth
