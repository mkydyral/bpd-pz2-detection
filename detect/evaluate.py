"""Оценка правил по разметке сценария.

Для каждого правила: число тревог, TP и FP (по транзакциям), precision, доля ложных тревог
среди легитимных транзакций (FPR), обнаруженные инциденты, задержка обнаружения и запас
времени до первого ущерба (в блоках). Для сценария: потери по инцидентам.
"""
ETH = 10**18
INCIDENT_TYPES = {'A': 'повторный вход', 'B': 'захват роли оператора'}
MAX_LOG = 40


def incidents_of(monitor, labels):
    """{инцидент: {'start': блок начала, 'first_loss': блок первого ущерба, 'loss': wei}}"""
    result = {}
    for tx in monitor.txs:
        name = labels[tx.hash].incident
        if not name:
            continue
        inc = result.setdefault(name, {'start': tx.block, 'first_loss': None, 'loss': 0})
        loss = monitor.eth_outflow[tx.hash]
        if tx.status == 1 and loss > 0:
            inc['loss'] += loss
            if inc['first_loss'] is None:
                inc['first_loss'] = tx.block
    return result


def rule_row(rule_id, title, monitor, labels, incidents, n_benign):
    first_alert = {}  # хэш -> первая тревога правила по транзакции
    for alert in monitor.alerts:
        if alert.rule == rule_id:
            first_alert.setdefault(alert.tx.hash, alert)
    tp = sum(1 for h in first_alert if labels[h].incident)
    fp = len(first_alert) - tp
    precision = f'{tp / len(first_alert):.0%}' if first_alert else '-'
    detected, cells = 0, []
    for name, inc in incidents.items():
        blocks = [a.tx.block for h, a in first_alert.items() if labels[h].incident == name]
        if not blocks:
            cells.append(f'{name} -')
            continue
        detected += 1
        first = min(blocks)
        lead = '-' if inc['first_loss'] is None else inc['first_loss'] - first
        cells.append(f'{name} {first - inc["start"]}/{lead}')
    return (f'{rule_id:<3} {title:<35} {len(first_alert):>6} {tp:>4} {fp:>4} {precision:>9} '
            f'{fp / n_benign:>7.1%}  {detected}/{len(incidents)}: {", ".join(cells)}')


def alert_log(monitor, labels):
    lines = ['', 'Журнал тревог (блок, правило, разметка, сообщение):']
    for alert in monitor.alerts[:MAX_LOG]:
        step = labels[alert.tx.hash]
        mark = f'АТАКА {step.incident} ({step.phase})' if step.incident else f'ЛОЖНАЯ ({step.kind})'
        lines.append(f'  блок {alert.tx.block:>4}  {alert.rule:<3}  {mark:<40} {alert.message}')
    if len(monitor.alerts) > MAX_LOG:
        lines.append(f'  ... ещё {len(monitor.alerts) - MAX_LOG}')
    return lines


def report(monitor, labels, rules, pause=None, quiet=False):
    txs = monitor.txs
    n_attack = sum(1 for tx in txs if labels[tx.hash].incident)
    n_benign = len(txs) - n_attack
    incidents = incidents_of(monitor, labels)
    lines = [f'Транзакций: {len(txs)} (легитимных {n_benign}, атакующих {n_attack}), '
             f'блоки {txs[0].block}-{txs[-1].block}']
    lines.append('Инциденты: ' + '; '.join(
        f'{name} - {INCIDENT_TYPES[name[0]]}, блок {inc["start"]}' for name, inc in incidents.items()))
    if not quiet:
        lines += alert_log(monitor, labels)
    lines += ['', f'{"Правило":<39} {"Тревог":>6} {"TP":>4} {"FP":>4} {"Precision":>9} {"FPR":>7}  '
                  f'Инциденты: задержка/запас, блоков']
    lines += [rule_row(rule_id, title, monitor, labels, incidents, n_benign) for rule_id, title, _ in rules]
    lines.append('Задержка - от начала инцидента до первой тревоги; запас - от первой тревоги до первого '
                 'ущерба (1 блок Ethereum = 12 с).')
    total = sum(inc['loss'] for inc in incidents.values())
    lines.append('Потери: ' + ', '.join(f'{name} {inc["loss"] / ETH:.2f} ETH' for name, inc in incidents.items())
                 + f'; итого {total / ETH:.2f} ETH')
    rejected = sum(1 for tx in txs if tx.status == 0 and not labels[tx.hash].incident)
    if pause:
        block, alert = pause
        step = labels[alert.tx.hash]
        cause = f'атака {step.incident}' if step.incident else f'ЛОЖНАЯ тревога, {step.kind}'
        lines.append(f'Пауза: блок {block}, guardian по тревоге {alert.rule} ({cause}). '
                     f'Отклонено легитимных транзакций: {rejected}.')
    elif rejected:
        lines.append(f'Откатилось легитимных транзакций: {rejected}.')
    return '\n'.join(lines)
