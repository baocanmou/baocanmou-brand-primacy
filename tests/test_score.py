import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score = load('score')
jev_review = load('jev_review')


def example(name):
    return json.loads((ROOT / f'examples/{name}.json').read_text(encoding='utf-8'))


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.data = example('suihe-bakery')

    def result(self):
        self.assertEqual(score.validate(self.data), [])
        return score.compute(self.data)

    def set_dimension(self, code, value):
        for n in range(1, 5):
            self.data['items'][f'{code}{n}'].update(score=value, evidence_type='资料可见')

    def set_all(self, value):
        for code in score.CODES:
            self.set_dimension(code, value)

    def test_example_scores(self):
        r = self.result()
        self.assertEqual([d['score'] for d in r['dimensions']], [7.0, 8.5, 3.5, 6.7])
        self.assertEqual((r['g'], r['tier'], r['coverage'], r['status']), (6.1, '中', '15/16', 'final'))
        self.assertEqual(r['shortest'], 'M')
        self.assertEqual(r['source_status'], '待验证')

    def test_weak_example_has_no_source(self):
        self.data = example('qingqi-salad')
        r = self.result()
        self.assertEqual((r['tier'], r['shortest'], r['source_status']), ('弱', 'C', '未成立'))

    def test_geometric_mean_keeps_short_board(self):
        self.set_all(5)
        self.set_dimension('S', 1)
        self.data['actions'][0]['item'] = 'S1'
        r = self.result()
        self.assertEqual([d['score'] for d in r['dimensions']], [10, 10, 10, 2])
        self.assertEqual(r['g'], 6.7)
        self.assertEqual(r['tier'], '弱')

    def test_zero_dimension_gives_zero(self):
        self.set_all(4)
        self.set_dimension('U', 0)
        self.data['actions'][0]['item'] = 'U1'
        self.data['source']['evidence_ids'] = ['C1', 'C2']
        self.assertEqual(self.result()['g'], 0)

    def test_tiers(self):
        for value, expected in ((5, '强'), (4, '强'), (3, '中'), (2, '弱')):
            self.set_all(value)
            self.data['source']['evidence_ids'] = ['C1', 'C2']
            if value < 3:
                self.data['source'] = None
            self.assertEqual(self.result()['tier'], expected, value)

    def test_source_established_needs_all_tests_and_not_weak(self):
        self.set_all(4)
        for t in self.data['source']['tests'].values():
            t['pass'] = True
        self.assertEqual(self.result()['source_status'], '成立')
        self.set_dimension('M', 1)
        self.assertEqual(self.result()['source_status'], '待验证')

    def test_evidence_caps(self):
        self.data['items']['C1'].update(score=5, evidence_type='用户陈述')
        self.data['items']['S1'].update(score=4, evidence_type='推断')
        errors = score.validate(self.data)
        self.assertTrue(any('C1' in e and '4' in e for e in errors))
        self.assertTrue(any('S1' in e and '3' in e for e in errors))

    def test_pending_item_must_not_be_scored(self):
        self.data['items']['S4']['score'] = 3
        self.assertTrue(any('S4' in e for e in score.validate(self.data)))

    def test_no_source_when_core_is_weak(self):
        self.set_dimension('C', 1)
        self.data['actions'][0]['item'] = 'C2'
        self.assertTrue(any('先回去找根' in e for e in score.validate(self.data)))

    def test_source_must_rest_on_scored_core_evidence(self):
        self.data['source']['evidence_ids'] = ['U1', 'U4']
        self.assertTrue(any('C 检查项' in e for e in score.validate(self.data)))
        self.data['source']['evidence_ids'] = ['C1', 'M3']
        self.assertTrue(any('M3' in e for e in score.validate(self.data)))

    def test_actions_must_address_shortest_dimension(self):
        for action in self.data['actions']:
            action['item'] = 'U2'
        self.assertTrue(any('最短的一项是 M' in e for e in score.validate(self.data)))

    def test_no_source_when_core_is_insufficient(self):
        for item_id in ('C1', 'C4'):
            self.data['items'][item_id].update(score=None, evidence_type='待核实')
        self.assertTrue(any('C 证据不足' in e for e in score.validate(self.data)))

    def test_dimension_needs_three_scored_items(self):
        for item_id in ('S1', 'S2'):
            self.data['items'][item_id].update(score=None, evidence_type='待核实')
        r = self.result()
        self.assertIsNone(r['g'])
        self.assertEqual(r['insufficient'], ['S'])
        self.assertEqual((r['order'], r['shortest']), ([], None))

    def test_low_coverage_is_estimate(self):
        for item_id in ('C4', 'U2', 'M4'):
            self.data['items'][item_id].update(score=None, evidence_type='待核实')
        r = self.result()
        self.assertEqual((r['coverage'], r['status']), ('12/16', 'estimate'))

    def test_absolute_words_are_flagged(self):
        self.data['source']['statement'] = '全城第一的现烤面包'
        self.assertTrue(any('第一' in w for w in self.result()['warnings']))
        self.data['source']['statement'] = '当天现做'
        self.data['actions'][0]['what'] = '挑卖得最好的三款加烤一炉'
        self.assertEqual(self.result()['warnings'], [])

    def test_cli_compare(self):
        newer = copy.deepcopy(self.data)
        for n in range(1, 5):
            newer['items'][f'M{n}'].update(score=4, evidence_type='资料可见')
        newer['actions'][0]['item'] = 'S1'
        with tempfile.TemporaryDirectory() as tmp:
            old_path, new_path = Path(tmp) / 'old.json', Path(tmp) / 'new.json'
            old_path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
            new_path.write_text(json.dumps(newer, ensure_ascii=False), encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = score.main([str(old_path), str(new_path), '--compare'])
        self.assertEqual(code, 0)
        self.assertIn('M 市场敏感度  3.5 → 8  （+4.5）', out.getvalue())


class JevReviewTests(unittest.TestCase):
    def test_checkpoints_and_ladder_match_rubric(self):
        rubric = (ROOT / 'references/rubric.md').read_text(encoding='utf-8')
        for item_id, title in jev_review.CHECKPOINTS.items():
            self.assertIn(f'| {item_id} | {title} |', rubric)
        for level in jev_review.LADDER:
            self.assertIn(f'| {level.split("：")[0]} |', rubric)

    def test_request_only_asks_about_scored_items(self):
        body = jev_review.build_request(example('suihe-bakery'))
        self.assertNotIn('level_S4', body['questions'])
        self.assertEqual(len([q for q in body['questions'] if q.startswith('level_')]), 15)
        self.assertEqual(len(body['questions']), 15 + 3 + 3)

    def test_review_flags_gaps(self):
        data = example('suihe-bakery')
        answers = {f'level_{i}': {'score': float(v['score']), 'confidence': 0.9}
                   for i, v in data['items'].items() if v['score'] is not None}
        answers['level_C2'] = {'score': 1.0, 'confidence': 0.9}
        answers.update(source_generic={'noul': 0.1}, source_supported={'noul': 0.2},
                       source_slogan={'noul': 0.1}, action_0={'noul': 0.9},
                       action_1={'noul': 0.3}, action_2={'noul': 0.9})
        flags = jev_review.review(data, answers)['flags']
        self.assertEqual(len(flags), 3)
        self.assertTrue(flags[0].startswith('C2') and '可能偏高' in flags[0])


if __name__ == '__main__':
    unittest.main()
