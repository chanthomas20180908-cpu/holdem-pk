"""Decision-first text and Markdown views of public-information analysis."""
import re
from .display import cards
from .assist import NAMES
from .terminal import wrap


UNCERTAIN = '暂无法可靠判断'
ASSUMPTION = '条件比较未预测对手后续反应，假设此后无额外下注；各情景沿用当前对手范围。'


def percent(value):
    return f'{value:.1%}'


def clean(value):
    return ' '.join(str(value).split())


def markdown(value):
    # Nicknames and other dynamic text cannot create links, HTML or table cells.
    return re.sub(r'([\\`*_{}\[\]()<>#|~])', r'\\\1', clean(value))


def short(value, limit=18):
    value = clean(value)
    return value if len(value) <= limit else value[:limit-1]+'…'


def odds(result, reliable, *, headline=False):
    if result.get('direct'):
        return '直接拿池（发生率未预测）'
    if not reliable or result.get('win') is None:
        return UNCERTAIN
    if headline:
        return (f'独赢 {percent(result["win"])}　｜　平局 {percent(result["tie"])}'
                f'　｜　落败 {percent(result["loss"])}')
    return f'{percent(result["win"])} / {percent(result["tie"])}'


def scenario_label(s):
    if s['label'] == '当前跟注':
        return '当前对手留场'
    return s['label'].replace('其余未回应者', '待回应者').replace('可回应者全部', '可回应者')


def change_summary(a):
    if len(a['headline']['pot_results']) > 1 or a['headline']['excluded_pots']:
        return '存在分池资格差异，暂不将整桌胜率变化归因到各池。'
    timeline = a['timeline']
    if len(timeline) < 2 or any(step['ess'] < 100 for step in timeline):
        return '尚无可靠的前后对比。'
    changes = sorted(timeline[1:], key=lambda step: -abs(step['win_delta']))[:2]
    changes = [step for step in changes if abs(step['win_delta']) >= .0005]
    if not changes:
        return '独赢机会较上次没有明显变化。'
    return '；'.join(short(step['label'], 24)+f'：独赢机会 {step["win_delta"]*100:+.1f} 个百分点'
                    for step in changes)+'（主要估计变化）。'


def path_summary(a):
    if not a['board']:
        return '尚未发出翻牌，先看起手牌结构与留场人数。'
    if len(a['board']) == 5:
        return '已到河牌，没有后续补牌。'
    groups = a['paths']['groups']
    improving = [x for g in groups if g['label'] in ('有效改善', '改善但有风险') for x in g['items']]
    improving.sort(key=lambda x: -NAMES.index(x['category']))
    danger = next((g for label in ('危险来牌', '改善但有风险') for g in groups if g['label'] == label), None)
    parts = []
    if improving:
        items = [x for x in improving if x['category'] == improving[0]['category']][:2]
        parts.append('改善例 '+cards([x['card'] for x in items])+' → '+items[0]['category']+'（不保证获胜）')
    if danger:
        parts.append('警惕 '+cards([x['card'] for x in danger['items'][:2]])+'，可能增加牌面威胁')
    return '；'.join(parts)+'。' if parts else '没有提高成牌等级的下一张牌，留意对手继续下注。'


def reasons(a):
    current = a['current']
    threats = []
    for opponent in a['ranges']:
        for candidate in opponent['leading']:
            category = candidate['description'].split(' · ')[0]
            if category not in threats:
                threats.append(category)
    if threats:
        current += '；可能落后于 '+ '、'.join(threats[:2])+' 等候选成牌'
    pressure = [p for p in a['ranges'] if any('下注' in e or '跟注' in e for e in p['evidence'])]
    if pressure:
        strongest = max(pressure, key=lambda p: sum('下注' in e for e in p['evidence']))
        evidence = next(e for e in reversed(strongest['evidence']) if '下注' in e or '跟注' in e)
        pressure_text = short(strongest['name'])+'：'+evidence+'，其候选范围随公开行动调整。'
    else:
        pressure_text = '尚无可用于收窄范围的下注／跟注证据。'
    if not a['history_complete']:
        pressure_text = '历史不完整，未猜测缺失动作，按随机范围参照。'
    return [('当前牌力', current+'。'),
            ('对手压力', pressure_text),
            ('关键来牌', path_summary(a)),
            ('相比上次', change_summary(a)),
            ('选择依据', a['advice_reason'])]


def comparison_rows(a):
    reliable = a['ess'] >= 100
    rows, sidepots = [], []
    for choice in a['comparisons']:
        action = choice['label']+f'（投入 {choice["paid"]}）'
        if choice['action'] == 'fold':
            rows.append((action, '放弃争夺', '—', '0（不再投入）'))
            continue
        for s in choice['scenarios']:
            label = scenario_label(s)
            # A pickup and a refund are deterministic within a forced scenario.
            ev = f'{s["ev"]:+.1f}' if reliable or s['direct'] else UNCERTAIN
            chance = '分池见下' if len(s['pot_results']) > 1 and not s['direct'] else odds(s, reliable)
            rows.append((action, label, chance, ev))
            if len(s['pot_results']) > 1 or s['excluded_pots']:
                bits = []
                for p in s['pot_results']:
                    chance = odds(p, reliable)
                    if not p['direct'] and reliable:
                        chance = f'独赢 {percent(p["win"])} / 平局 {percent(p["tie"])}'
                    bits.append(p['label']+f' {p["amount"]}：'+chance)
                if s['excluded_pots']:
                    bits.append('无资格争夺 '+ '、'.join(p['label']+f' {p["amount"]}' for p in s['excluded_pots']))
                if s['refund']:
                    bits.append(f'未被跟注退回 {s["refund"]}（不算获胜）')
                sidepots.append((choice['label']+' / '+label, '；'.join(bits)))
    return rows, sidepots


def detail_sections(a):
    sections = []
    opponents = []
    for p in a['ranges']:
        evidence = ' → '.join(p['evidence']) or '没有可用动作证据'
        groups = '、'.join(g['label'] for g in p['groups'][:2])
        opponents.append((p['name'], evidence+'；候选类型包括 '+groups+'，不代表实际持牌。'))
    if opponents:
        sections.append(('对手公开证据', opponents))
    paths = []
    for group in a['paths']['groups']:
        routes = {}
        for item in group['items']:
            routes.setdefault(item['route'], []).append(item)
        ordered = sorted(routes.items(), key=lambda route: -NAMES.index(route[1][0]['category']))
        for route, items in ordered[:2]:
            examples = cards([item['card'] for item in items[:3]])
            paths.append((group['label'], examples+' 等 → '+route+'；'+items[0]['reason']))
    if paths:
        sections.append(('关键来牌展开', paths))
    if len(a['timeline']) > 1 and len(a['headline']['pot_results']) == 1 and not a['headline']['excluded_pots']:
        changes = []
        for previous, step in zip(a['timeline'], a['timeline'][1:]):
            reliable = step['ess'] >= 100 and previous['ess'] >= 100
            changes.append((step['label'], f'独赢机会 {step["win_delta"]*100:+.1f} 个百分点' if reliable else UNCERTAIN))
        sections.append(('公开事件与胜率变化', changes))
    if a['comparisons']:
        sections.append(('各选择的取舍', [(c['label'], c['risk']+'。') for c in a['comparisons']]))
    return sections


def render(a, *, format='text', width=64):
    if format not in ('text', 'markdown'):
        raise ValueError('辅助输出格式必须为 text 或 markdown')
    width = max(40, width)
    md = format == 'markdown'
    lines = []

    def heading(title):
        if lines:
            lines.append('')
        lines.extend([('### '+title) if md else '【'+title+'】', ''])

    def paragraph(value, *, bold=False):
        if md:
            value = markdown(value)
            lines.append('**'+value+'**' if bold else value)
        else:
            lines.extend(wrap(clean(value), width))

    def bullet(label, value):
        if md:
            lines.append('- **'+markdown(label)+'**：'+markdown(value))
        else:
            lines.extend(wrap('• '+clean(label)+'：'+clean(value), width))

    heading('辅助决策')
    if a['inactive']:
        paragraph(a['reason'])
        return '\n'.join(lines)
    paragraph('建议：'+a['advice'], bold=True)
    lines.append('')
    paragraph(a['advice_reason'])
    heading('最终获胜机会')
    reliable = a['ess'] >= 100
    final = a['headline']
    if len(final['pot_results']) > 1 or final['excluded_pots']:
        for pot in final['pot_results']:
            paragraph(pot['label']+f' {pot["amount"]}：'+odds(pot, reliable, headline=True), bold=True)
        if final['excluded_pots']:
            paragraph('无资格争夺：'+'、'.join(p['label'] for p in final['excluded_pots']))
    else:
        paragraph(odds(final, reliable, headline=True), bold=True)
    lines.append('')
    paragraph(f'第 {a["hand_number"]} 手 · {short(a["player_names"][a["seat"]])}视角 · '
              f'{a["live_count"]} 人在局；假设本轮全部跟平，随后无额外下注至摊牌，基于公开信息估计。')
    heading('选择对比')
    if not md and a['comparisons']:
        paragraph('概率顺序：独赢 / 平局')
        lines.append('')
    rows, sidepots = comparison_rows(a)
    if not rows:
        paragraph('尚未轮到你或你已全押，暂无可执行选择。')
    elif md:
        lines += ['| 选择与本次投入 | 对手情景 | 独赢 / 平局 | 条件净收益 |',
                  '|---|---|---|---:|']
        lines.extend('| '+' | '.join(markdown(cell) for cell in row)+' |' for row in rows)
    else:
        previous_action = None
        for action, label, chances, ev in rows:
            if action != previous_action:
                if lines[-1]:
                    lines.append('')
                paragraph(action)
            paragraph(f'{label}：{chances}；条件净收益 {ev}')
            previous_action = action
    lines.append('')
    paragraph(ASSUMPTION)
    if rows:
        paragraph('净收益从当前决策点计算，既往投入不重复扣除；退款不算获胜。')
    if sidepots:
        lines.append('')
        paragraph('分池：以下概率按各个本人有资格争夺的底池分别展示。')
        if md:
            lines.append('')
        for label, value in sidepots:
            bullet(label, value)
    heading('为什么')
    for label, value in reasons(a):
        bullet(label, value)
    if a['detail']:
        for title, entries in detail_sections(a):
            heading(title)
            for label, value in entries:
                bullet(label, value)
    return '\n'.join(lines)
