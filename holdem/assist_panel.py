"""Decision-first text and Markdown views of public-information analysis."""
import re
from .display import cards
from .assist import NAMES
from .terminal import wrap


UNCERTAIN = '暂无法可靠判断'
ASSUMPTION = '当前轮规则模型估计，未校准；最多一次对手反加，之后假设无额外下注。'


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
                    for step in changes)+'（摊牌参照的主要估计变化）。'


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


def threat_entries(a, detail=False):
    entries = []
    for opponent in a['ranges']:
        parts = []
        for threat in opponent['threats']:
            probability = percent(threat['prob']) if threat['prob'] >= .001 else '<0.1%'
            text = threat['label']+' '+probability
            if detail or threat['label'] in ('顺子', '同花顺'):
                text += '（'+' / '.join(threat['families'][:None if detail else 2])+'）'
            parts.append(text)
        if parts:
            entries.append((short(opponent['name']), '；'.join(parts)))
    return entries


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
    if a.get('prediction'):
        entries = []
        for c in a['prediction']['actions']:
            entries.append((c['label'], f'被反加 {percent(c["reraise"])}；'
                            f'反加后平均额外投入 {c["extra_paid"]:.1f}；退款均值 {c["refund"]:.1f}。'))
        sections.append(('反加与追加投入', entries))
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
    prediction = a.get('prediction')
    confidence = ' ｜ 信心：'+prediction['confidence']+'（模型内）' if prediction else ''
    paragraph('建议：'+a['advice']+confidence, bold=True)
    lines.append('')
    paragraph(a['advice_reason'])
    if prediction and prediction['backup']:
        backup = prediction['backup']
        paragraph('备选：'+backup['label']+f'（预计净收益 {backup["ev"]:+.1f}）。')
    heading('最终获胜机会')
    reliable = (prediction['ess'] if prediction else a['ess']) >= 100-1e-9
    final = prediction['best'] if prediction else a['headline']
    if prediction:
        if final['action'] == 'fold':
            paragraph('弃牌后放弃争夺，不再追加投入。')
        elif final['split']:
            paragraph('采用首选动作，按可争夺底池分别看：')
            lines.append('')
            for pot in final['pot_results']:
                bullet(pot['label'], f'可争夺概率 {percent(pot["presence"])}；该池可争夺时，获胜 {percent(pot["win"])}，'
                       f'平局 {percent(pot["tie"])}')
            if final['excluded_pots']:
                paragraph('部分情景无资格争夺：'+'、'.join(p['label'] for p in final['excluded_pots']))
        else:
            paragraph(f'总获胜 {percent(final["win"])} ｜ 平局 {percent(final["tie"])} ｜ '
                      f'落败 {percent(max(0.,1-final["win"]-final["tie"]))}', bold=True)
            lines.append('')
            paragraph(f'直接拿池 {percent(final["direct"])} ＋ 摊牌独赢 {percent(final["showdown"])}。')
        lines.append('')
        paragraph('以上按首选动作及模型内反加应对计算。')
    else:
        if len(final['pot_results']) > 1 or final['excluded_pots']:
            for pot in final['pot_results']:
                paragraph(pot['label']+f' {pot["amount"]}：'+odds(pot, reliable, headline=True), bold=True)
            if final['excluded_pots']:
                paragraph('无资格争夺：'+'、'.join(p['label'] for p in final['excluded_pots']))
        else:
            paragraph(odds(final, reliable, headline=True), bold=True)
        lines.append('')
        paragraph('尚无可执行动作；以上为本轮跟平、之后无额外下注的摊牌参照。')
    heading('选择对比')
    if prediction:
        rows = []
        for n,c in enumerate(prediction['actions']):
            chance = '分池见下' if c['split'] else percent(c['win'])
            risk = '不再投入' if c['action'] == 'fold' else '亏损 '+percent(c['loss_risk'])
            rows.append((('首选 ' if n == 0 else '')+c['label']+f'（投入 {c["paid"]}）',
                         chance, f'{c["ev"]:+.1f}', risk))
        if md:
            lines += ['| 选择与本次投入 | 总获胜概率 | 预计净收益 | 主要风险 |', '|---|---:|---:|---|']
            lines.extend('| '+' | '.join(markdown(cell) for cell in row)+' |' for row in rows)
        else:
            for action, chance, ev, risk in rows:
                paragraph(action)
                paragraph(f'获胜 {chance} · 预计净收益 {ev} · {risk}')
                lines.append('')
        split_choices = [c for c in prediction['actions'] if c['split'] and c is not final]
        if split_choices:
            lines.append('')
            paragraph('其他分池选择（概率以该池可争夺为条件）：')
            if md:
                lines.append('')
            for c in split_choices:
                bullet(c['label'], '；'.join(p['label']+f'：可争夺 {percent(p["presence"])} / 获胜 {percent(p["win"])}'
                                           for p in c['pot_results']))
    else:
        paragraph('尚未轮到你或你已全押，暂无可执行选择。')
    lines.append('')
    paragraph(ASSUMPTION)
    if prediction:
        paragraph('以净收益为主排序；收益接近时优先减少投入。')
        paragraph('净收益和亏损风险从当前决策点起算，既往投入不重复扣除；退款不算获胜。')
    threats = threat_entries(a, a['detail'])
    if threats:
        heading('对手关键威胁')
        paragraph('占比为各席候选范围中领先你的部分，并非已知持牌。')
        lines.append('')
        for label,value in threats:
            bullet(label,value)
    heading('为什么')
    for label, value in reasons(a):
        bullet(label, value)
    if a['detail']:
        for title, entries in detail_sections(a):
            heading(title)
            for label, value in entries:
                bullet(label, value)
    return '\n'.join(lines)
