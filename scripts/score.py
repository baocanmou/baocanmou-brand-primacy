#!/usr/bin/env python3
"""Score a Brand Primacy (CUMS) diagnosis. Checks structure, evidence rules and arithmetic, not the judgment itself."""
import argparse
import json
import sys
from pathlib import Path

DIMENSIONS = [
    ('C', '核心价值与文化'),
    ('U', '用户连接'),
    ('M', '市场敏感度'),
    ('S', '社会角色与价值'),
]
CODES = [code for code, _ in DIMENSIONS]
ITEM_IDS = [f'{code}{n}' for code in CODES for n in range(1, 5)]
# Self-reported and inferred evidence cannot reach the top of the evidence ladder.
EVIDENCE_CAPS = {'资料可见': 5, '用户陈述': 4, '推断': 3}
PENDING = '待核实'
TESTS = ('真', '要', '异', '久')
MIN_ITEMS_PER_DIMENSION = 3
MIN_COVERAGE_FOR_TIER = 13
WEAK_DIMENSION = 3
SOURCE_EVIDENCE_MIN_SCORE = 3
ABSOLUTE_WORDS = ('最好', '最强', '最大', '第一', '唯一', '独家', '顶级', '保证', '100%', '永不', '根治')
ROUTES = {
    '强': '放大并坚持',
    '中': '先补短板，再设计表达',
    '弱': '回去找根、补证据，不做放大',
}


def tier(g, scores):
    if g < 5 or min(scores) <= WEAK_DIMENSION:
        return '弱'
    return '强' if g >= 8 else '中'


def dimension_scores(items):
    out = {}
    for code in CODES:
        scored = [items[f'{code}{n}']['score'] for n in range(1, 5)
                  if items[f'{code}{n}']['score'] is not None]
        value = None
        if len(scored) >= MIN_ITEMS_PER_DIMENSION:
            value = round(sum(scored) / (len(scored) * 5) * 10, 1)
        out[code] = (value, len(scored))
    return out


def validate_items(items):
    errors = []
    if not isinstance(items, dict):
        return ['缺少 items 对象']
    missing = [i for i in ITEM_IDS if i not in items]
    if missing:
        errors.append(f'缺少检查项：{", ".join(missing)}')
    extra = [i for i in items if i not in ITEM_IDS]
    if extra:
        errors.append(f'未知检查项：{", ".join(extra)}')
    for item_id in ITEM_IDS:
        item = items.get(item_id)
        if item is None:
            continue
        if not isinstance(item, dict):
            errors.append(f'{item_id} 必须是对象')
            continue
        etype, score = item.get('evidence_type'), item.get('score')
        if not isinstance(item.get('evidence'), str) or not item['evidence'].strip():
            errors.append(f'{item_id}: evidence 不能为空')
        if etype == PENDING:
            if score is not None:
                errors.append(f'{item_id}: 待核实项的 score 必须是 null')
        elif etype not in EVIDENCE_CAPS:
            errors.append(f'{item_id}: evidence_type 必须是 {"、".join([*EVIDENCE_CAPS, PENDING])} 之一')
        elif isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 5:
            errors.append(f'{item_id}: score 必须是 0–5 的整数')
        elif score > EVIDENCE_CAPS[etype]:
            errors.append(f'{item_id}: 证据类型为「{etype}」时不能高于 {EVIDENCE_CAPS[etype]} 分')
    return errors


def validate(data):
    if not isinstance(data, dict):
        return ['诊断必须是 JSON 对象']
    errors = []
    if data.get('schema_version') != '1.0':
        errors.append('schema_version 必须是 "1.0"')
    brand = data.get('brand')
    if not isinstance(brand, dict) or not isinstance(brand.get('name'), str) or not brand['name'].strip():
        errors.append('brand.name 不能为空')
    item_errors = validate_items(data.get('items'))
    errors += item_errors
    if item_errors:
        return errors
    items = data['items']
    dims = dimension_scores(items)

    source = data.get('source')
    if source is not None:
        if not isinstance(source, dict):
            return errors + ['source 必须是对象或 null']
        if dims['C'][0] is None:
            errors.append('C 证据不足时不写源力句，source 应为 null：先补 C 的证据')
        elif dims['C'][0] <= WEAK_DIMENSION:
            errors.append(f'C 不高于 {WEAK_DIMENSION} 分时不写源力句，source 应为 null：先回去找根')
        for key in ('statement', 'direction'):
            if not isinstance(source.get(key), str) or not source[key].strip():
                errors.append(f'source.{key} 不能为空')
        ids = source.get('evidence_ids')
        if not isinstance(ids, list) or len(ids) < 2:
            errors.append('source.evidence_ids 至少引用 2 个检查项')
        else:
            if not any(isinstance(i, str) and i.startswith('C') for i in ids):
                errors.append('source.evidence_ids 至少引用 1 个 C 检查项：源力要长在根上')
            for i in ids:
                score = items.get(i, {}).get('score') if isinstance(i, str) else None
                if i not in ITEM_IDS:
                    errors.append(f'source.evidence_ids: 未知检查项 {i}')
                elif score is None or score < SOURCE_EVIDENCE_MIN_SCORE:
                    errors.append(f'source.evidence_ids: {i} 低于 {SOURCE_EVIDENCE_MIN_SCORE} 分，撑不起源力句')
        tests = source.get('tests')
        if not isinstance(tests, dict) or set(tests) != set(TESTS):
            errors.append(f'source.tests 需要 {"、".join(TESTS)} 四关')
        else:
            for name in TESTS:
                t = tests[name]
                if (not isinstance(t, dict) or not isinstance(t.get('pass'), bool)
                        or not isinstance(t.get('why'), str) or not t['why'].strip()):
                    errors.append(f'source.tests.{name} 需要 pass（true/false）和非空的 why')

    actions = data.get('actions')
    if not isinstance(actions, list) or not 1 <= len(actions) <= 3:
        errors.append('actions 需要 1–3 件事')
    else:
        for n, action in enumerate(actions, 1):
            if not isinstance(action, dict):
                errors.append(f'actions[{n}] 必须是对象')
                continue
            for key in ('what', 'who', 'done_when'):
                if not isinstance(action.get(key), str) or not action[key].strip():
                    errors.append(f'actions[{n}].{key} 不能为空')
            if action.get('item') not in ITEM_IDS:
                errors.append(f'actions[{n}].item 必须是 16 个检查项之一')
    not_doing = data.get('not_doing')
    if (not isinstance(not_doing, list) or not 1 <= len(not_doing) <= 3
            or not all(isinstance(x, str) and x.strip() for x in not_doing)):
        errors.append('not_doing 需要 1–3 条非空文字')
    if errors:
        return errors

    scores = [dims[c][0] for c in CODES]
    if None not in scores:
        shortest = min(CODES, key=lambda c: (dims[c][0], CODES.index(c)))
        g = geometric_mean(scores)
        if tier(g, scores) != '强' and not any(a['item'].startswith(shortest) for a in actions):
            errors.append(f'最短的一项是 {shortest}，actions 里至少要有一件事针对它')
    return errors


def geometric_mean(scores):
    product = 1.0
    for s in scores:
        product *= s
    return round(product ** 0.25, 1)


def compute(data):
    items = data['items']
    dims = dimension_scores(items)
    names = dict(DIMENSIONS)
    dimensions = [{'code': c, 'name': names[c], 'score': dims[c][0], 'scored_items': dims[c][1]}
                  for c in CODES]
    scored_total = sum(d['scored_items'] for d in dimensions)
    scores = [d['score'] for d in dimensions]
    complete = None not in scores
    g = geometric_mean(scores) if complete else None
    final = complete and scored_total >= MIN_COVERAGE_FOR_TIER
    level = tier(g, scores) if complete else None
    ranked = sorted((d for d in dimensions if d['score'] is not None),
                    key=lambda d: (d['score'], CODES.index(d['code'])))

    source = data.get('source')
    if source is None:
        source_status = '未成立'
    elif level != '弱' and all(source['tests'][t]['pass'] for t in TESTS):
        source_status = '成立'
    else:
        source_status = '待验证'

    warnings = []
    if source:
        hit = [w for w in ABSOLUTE_WORDS if w in source['statement']]
        if hit:
            warnings.append(f'源力句含绝对化用语「{"、".join(hit)}」，换成能证明的说法')
    for d in dimensions:
        if d['score'] is not None and d['score'] <= WEAK_DIMENSION:
            warnings.append(f'{d["code"]} 为 {d["score"]:g} 分，不高于 {WEAK_DIMENSION} 分：按“弱”处理，先补这一项')

    return {
        'dimensions': dimensions,
        'g': g,
        'coverage': f'{scored_total}/16',
        'status': 'final' if final else 'estimate',
        'tier': level,
        'route': ROUTES[level] if level else None,
        'shortest': ranked[0]['code'] if complete else None,
        'order': [d['code'] for d in ranked] if complete else [],
        'insufficient': [d['code'] for d in dimensions if d['score'] is None],
        'pending': [i for i in ITEM_IDS if items[i]['score'] is None],
        'source_status': source_status,
        'warnings': warnings,
    }


def render(name, r):
    lines = [f'## {name}', f'覆盖：{r["coverage"]}']
    if r['g'] is None:
        lines.append(f'源力指数：证据不足（{"、".join(r["insufficient"])}），不出总分和档位，先补证据')
    elif r['status'] == 'final':
        lines.append(f'源力指数 G：{r["g"]:g}/10　档位：{r["tier"]}　{r["route"]}')
    else:
        lines.append(f'源力指数 G：暂估 {r["g"]:g}/10（覆盖不足 {MIN_COVERAGE_FOR_TIER} 项）　'
                     f'暂按「{r["tier"]}」：{r["route"]}')
    for d in r['dimensions']:
        shown = '证据不足' if d['score'] is None else f'{d["score"]:g}/10'
        lines.append(f'  {d["code"]} {d["name"]}  {shown}  （打分 {d["scored_items"]}/4）')
    if r['order']:
        lines.append('补短板顺序：' + ' → '.join(r['order']))
    lines.append(f'源力句：{r["source_status"]}')
    if r['pending']:
        lines.append('待核实：' + '、'.join(r['pending']))
    lines += [f'提醒：{w}' for w in r['warnings']]
    return '\n'.join(lines)


def render_compare(old, new):
    lines = ['## 复测对比（前 → 后）']
    for a, b in zip(old['dimensions'], new['dimensions']):
        if a['score'] is None or b['score'] is None:
            lines.append(f'  {a["code"]} {a["name"]}  证据不足，无法对比')
            continue
        delta = round(b['score'] - a['score'], 1)
        lines.append(f'  {a["code"]} {a["name"]}  {a["score"]:g} → {b["score"]:g}  （{delta:+g}）')
    if old['g'] is not None and new['g'] is not None:
        lines.append(f'  源力指数 G  {old["g"]:g} → {new["g"]:g}  （{round(new["g"] - old["g"], 1):+g}）')
        lines.append(f'  档位  {old["tier"]} → {new["tier"]}')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path, help='一个或多个诊断 JSON')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    parser.add_argument('--compare', action='store_true', help='按“前、后”两份诊断输出复测对比')
    args = parser.parse_args(argv)
    if args.compare and len(args.files) != 2:
        parser.error('--compare 需要正好两份诊断：先旧后新')
    outputs, failed = [], False
    for path in args.files:
        data = json.loads(path.read_text(encoding='utf-8'))
        errors = validate(data)
        brand = data.get('brand') if isinstance(data, dict) else None
        label = (brand.get('name') if isinstance(brand, dict) else None) or path.stem
        if errors:
            failed = True
            outputs.append({'file': str(path), 'name': label, 'passed': False, 'errors': errors})
        else:
            outputs.append({'file': str(path), 'name': label, 'passed': True, **compute(data)})
    if args.json:
        print(json.dumps(outputs if len(outputs) > 1 else outputs[0], ensure_ascii=False, indent=2))
        return 1 if failed else 0
    for out in outputs:
        if out['passed']:
            print(render(out['name'], out))
        else:
            print(f'## {out["name"]}：检查未通过')
            print('\n'.join(f'  - {e}' for e in out['errors']))
        print()
    if args.compare and not failed:
        print(render_compare(*outputs))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
