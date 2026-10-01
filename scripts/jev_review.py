#!/usr/bin/env python3
"""Optional second opinion on a Brand Primacy diagnosis, using TypeSafe Jev.

score.py owns the arithmetic and stays authoritative. This script asks Jev to re-read each piece of
evidence against the evidence ladder and to check the source statement and actions, then lists where
its reading differs from the diagnosis. It never changes scores. Reads TYPESAFE_API_KEY from the
environment. Only the diagnosis JSON is sent to api.typesafe.ai.
"""
import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = 'https://api.typesafe.ai/v1/systemone'
MODEL = 'jev-latest'
GAP = 1.5  # ladder levels; smaller differences are treated as agreement
LOW_CONFIDENCE = 0.4

CHECKPOINTS = {
    'C1': '初心：为什么做这门生意',
    'C2': '底线：不肯妥协的事',
    'C3': '承诺：对顾客说到做到',
    'C4': '内部一致：团队照着做',
    'U1': '需求：顾客买它是为了解决什么',
    'U2': '落差：顾客在哪个环节不满',
    'U3': '回头：复购与推荐',
    'U4': '复述：顾客怎么向别人介绍它',
    'M1': '趋势：行业正在发生什么变化',
    'M2': '对手：谁在抢同一批顾客',
    'M3': '差异：对手做不到或不愿做的事',
    'M4': '调整：最近一次因变化做的改动',
    'S1': '存在价值：品牌不在了，谁会少了什么',
    'S2': '上下游：谁因它过得更好',
    'S3': '经得起看：经营方式能否长期并公开',
    'S4': '站位：和谁站在一起',
}
LADDER = [
    '没有：答不上来；或者说的和做的相反；或者证据表明这件事没做到、做得差',
    '只有说法：口号式回答，或没有核实过的个人看法，没有任何具体例子',
    '零散做到：有具体例子，但只靠个别人或个别时候，没有固定下来；或知道问题但没有处理；或数据表明只做到一小部分',
    '成了规矩：稳定在做，写出了具体做法、流程、标准；或只达到行业底线要求',
    '经过考验：为它放弃过钱、订单或速度；或在压力下照样做到；或做过调整并看到结果',
    '被人印证：这件事做得好，并且有顾客、员工、伙伴的原话，或数据、公开记录，能独立证明做得好',
]


def load_score():
    spec = importlib.util.spec_from_file_location('score', HERE / 'score.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_request(data):
    items = {i: {'checkpoint': CHECKPOINTS[i], 'evidence': v['evidence'], 'evidence_type': v['evidence_type']}
             for i, v in data['items'].items() if v['score'] is not None}
    state = {'brand': data['brand'], 'items': items}
    questions = {}
    for i in items:
        questions[f'level_{i}'] = {
            'type': 'score',
            'instructions': {
                'context': '这是一次品牌评估。只根据证据文字本身判断。阶梯衡量的是这件事做到了什么程度，不是证据有多确凿：证据表明做得不好时，即使有数据或原话，也选低档。',
                'question': f'`items.{i}.evidence` 这段证据，在检查项 `items.{i}.checkpoint` 上达到了证据阶梯的哪一级？',
            },
            'criteria': LADDER,
        }
    source = data.get('source')
    if source:
        state['source'] = {
            'statement': source['statement'],
            'cited_evidence': [items[i]['evidence'] for i in source['evidence_ids'] if i in items],
        }
        questions['source_generic'] = {
            'type': 'noul',
            'instructions': '把 `source.statement` 里的品牌换成同行业任意一个竞争对手，这句话是否多半仍然成立？',
            'criteria': {'true': '同行大多可以原样说这句话，没有只属于这个品牌的具体做法',
                         'false': '句子里有具体做法，多数同行说不出口或做不到'},
        }
        questions['source_supported'] = {
            'type': 'noul',
            'instructions': '`source.statement` 里的每一个事实性说法，是否都能在 `source.cited_evidence` 里找到依据？',
            'criteria': {'true': '每个说法都有对应证据', 'false': '至少有一个说法在证据里找不到依据'},
        }
        questions['source_slogan'] = {
            'type': 'noul',
            'instructions': '`source.statement` 读起来是否像广告口号，而不像老板或顾客平时会说的话？',
            'criteria': {'true': '形容词堆砌、抽象大词、喊口号', 'false': '平实，说的是具体的事'},
        }
    state['actions'] = [{'what': a['what'], 'who': a['who'], 'done_when': a['done_when']}
                        for a in data['actions']]
    for n in range(len(data['actions'])):
        questions[f'action_{n}'] = {
            'type': 'noul',
            'instructions': f'`actions[{n}]` 是否具体到负责的人下周一不用再问“这是什么意思”就能开始做，并且能判断做没做完？',
            'criteria': {'true': '动作、负责人和完成标准都具体可见',
                         'false': '是“提升”“加强”“优化”这类方向性说法，或看不出怎样算完成'},
        }
    return {'model': MODEL, 'state': state, 'questions': questions}


def ask(key, body):
    req = urllib.request.Request(
        API, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def review(data, answers):
    rows, flags = [], []
    for i, item in data['items'].items():
        if item['score'] is None:
            continue
        a = answers[f'level_{i}']
        jev, conf = round(a['score'], 1), round(a['confidence'], 2)
        diff = round(item['score'] - jev, 1)
        note = ''
        if abs(diff) >= GAP:
            note = '可能偏高' if diff > 0 else '可能偏低'
            if conf < LOW_CONFIDENCE:
                note += '（Jev 也不确定）'
            flags.append(f'{i} {CHECKPOINTS[i].split("：")[0]}：诊断 {item["score"]} 分，Jev 读作 {jev:g}，{note}。'
                         f'要么证据没写全，要么分打得不准。')
        rows.append({'id': i, 'score': item['score'], 'jev': jev, 'confidence': conf, 'note': note})
    source_checks = {}
    if data.get('source'):
        generic = round(answers['source_generic']['noul'], 2)
        supported = round(answers['source_supported']['noul'], 2)
        slogan = round(answers['source_slogan']['noul'], 2)
        source_checks = {'generic': generic, 'supported': supported, 'slogan': slogan}
        if generic >= 0.5 and data['source']['tests']['异']['pass']:
            flags.append(f'源力句：“异”这一关判了通过，但 Jev 认为同行多半也能说这句话（{generic:.0%}）。')
        if supported < 0.5:
            flags.append(f'源力句：有说法在引用的证据里找不到依据（有依据的概率 {supported:.0%}）。')
        if slogan >= 0.5:
            flags.append(f'源力句：读起来像口号（{slogan:.0%}），改成平时说话的样子。')
    actions = []
    for n, action in enumerate(data['actions']):
        p = round(answers[f'action_{n}']['noul'], 2)
        actions.append(p)
        if p < 0.5:
            flags.append(f'第 {n + 1} 件事不够具体（具体的概率 {p:.0%}）：{action["what"]}')
    return {'items': rows, 'source': source_checks, 'actions': actions, 'flags': flags}


def render(name, result, usage):
    lines = [f'## {name} · Jev 复核', 'ID   诊断  Jev   把握  备注']
    for r in result['items']:
        lines.append(f'{r["id"]}   {r["score"]}     {r["jev"]:<4g}  {r["confidence"]:.2f}  {r["note"]}')
    if result['source']:
        s = result['source']
        lines.append(f'源力句：同行也能说 {s["generic"]:.0%}　有证据支持 {s["supported"]:.0%}　像口号 {s["slogan"]:.0%}')
    lines.append('三件事的具体程度：' + '　'.join(f'{p:.0%}' for p in result['actions']))
    lines.append('')
    if result['flags']:
        lines.append('需要回看：')
        lines += [f'  - {f}' for f in result['flags']]
    else:
        lines.append('没有需要回看的分歧。')
    lines.append(f'读法：打分相差 {GAP} 级以上才列入回看；把握低于 {LOW_CONFIDENCE} 表示 Jev 自己也拿不准。'
                 '源力句“同行也能说”“像口号”到 50% 以上、“有证据支持”和三件事的具体程度低于 50% 才需要改。')
    lines.append(f'（{usage}；Jev 的读法只作第二意见，分数以 score.py 为准）')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='用 Jev 对诊断做第二意见复核（可选）')
    parser.add_argument('file', type=Path, help='诊断 JSON')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    args = parser.parse_args(argv)
    key = os.environ.get('TYPESAFE_API_KEY')
    if not key:
        print('未设置 TYPESAFE_API_KEY，跳过 Jev 复核。报告里注明“未做 Jev 复核”即可。', file=sys.stderr)
        return 2
    data = json.loads(args.file.read_text(encoding='utf-8'))
    errors = load_score().validate(data)
    if errors:
        print('诊断未通过 score.py 检查，先修正：\n' + '\n'.join(f'  - {e}' for e in errors), file=sys.stderr)
        return 1
    try:
        resp = ask(key, build_request(data))
    except (urllib.error.URLError, TimeoutError) as e:
        print(f'Jev 请求失败（{e}），跳过复核。', file=sys.stderr)
        return 2
    result = review(data, resp['answers'])
    usage = f'模型 {resp["model"]}，{resp["usage"]["input_tokens"] + resp["usage"]["output_tokens"]} tokens'
    if args.json:
        print(json.dumps({'model': resp['model'], 'usage': resp['usage'], **result}, ensure_ascii=False, indent=2))
    else:
        print(render(data['brand']['name'], result, usage))
    return 0


if __name__ == '__main__':
    sys.exit(main())
