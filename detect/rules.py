"""Правила обнаружения. В задании изменяется только этот файл.

Правило получает транзакцию tx и контекст ctx и возвращает строку - описание тревоги,
или None, если тревоги нет. Правило вызывается для каждой транзакции после её включения в блок.

tx.hash, tx.block      хэш транзакции и номер блока
tx.sender              кто отправил транзакцию
tx.status              1 - выполнена, 0 - откатилась
tx.events              события Vault в порядке появления. У события e:
                         e.name - 'Deposit', 'Withdrawal', 'OperatorChanged', 'Swept', 'Paused'
                         e.args - аргументы события (см. src/Vault.sol), например
                                  e.args['account'], e.args['to'], e.args['amount']

ctx.owner              владелец Vault
ctx.allowlist          адреса, которые владелец может назначить оператором
ctx.vault_eth          ETH на балансе Vault после транзакции, wei
ctx.total_balances     сумма balanceOf всех известных участников после транзакции, wei
ctx.deficit            нехватка средств после транзакции: total_balances - vault_eth
ctx.prev_deficit       нехватка средств до транзакции
ctx.balance_before(a)  balanceOf(a) до транзакции
"""

ETH = 10**18


def r1_repeated_withdrawals(tx, ctx):
    """R1. Повторный вход (reentrancy): несколько выводов в одной транзакции.

    TODO (Б2): правило срабатывает и на легитимные пакетные выплаты Payroll.
    Сравните события Withdrawal в атаке и в выплате, уточните условие,
    запустите make run и сравните FP и precision до и после.
    """
    withdrawals = [e for e in tx.events if e.name == 'Withdrawal']
    if len(withdrawals) >= 2:
        return f'{len(withdrawals)} событий Withdrawal в одной транзакции'
    return None


def r2_solvency(tx, ctx):
    """R2 (готовое правило). Платёжеспособность: ETH в Vault меньше суммы балансов участников.
    Тревога - только когда нехватка растёт, чтобы не повторять её в каждом блоке."""
    if ctx.deficit > 0 and ctx.deficit > ctx.prev_deficit:
        return f'нехватка {ctx.deficit / ETH:.2f} ETH (до транзакции {ctx.prev_deficit / ETH:.2f})'
    return None


def r3_operator_takeover(tx, ctx):
    """R3. Захват роли оператора.

    TODO (Б3): тревога, если в транзакции есть событие OperatorChanged и
    оператора сменил не владелец (e.args['by'] != ctx.owner)
    или новый оператор (e.args['newOperator']) не входит в ctx.allowlist.
    """
    return None


# Идентификатор, название в отчёте, функция.
RULES = [
    ('R1', 'Повторные выводы в одной транзакции', r1_repeated_withdrawals),
    ('R2', 'Платёжеспособность хранилища', r2_solvency),
    ('R3', 'Захват роли оператора', r3_operator_takeover),
]
