"""Frozen-source annotations must survive rechunking without invented quotes."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_eval_cases as cases


class EvalCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.raw = self.project / 'data/raw/snapshot'
        self.source_file = 'parsed/archon-quests/demo.json'
        path = self.raw / self.source_file
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'对话': [
            {'说话者': '角色甲', '类型': 'character', '内容': '甲😀乙丙丁戊。'},
            {'说话者': '', '类型': 'character', '内容': '原文未说明身份。'}
        ]}, ensure_ascii=False), encoding='utf-8')
        self.material = {'id': 'M1', 'source_file': self.source_file,
                         'source_pointer': '/对话/0/内容', 'start': 1, 'end': 5}

    def tearDown(self):
        self.temp.cleanup()

    def anchor(self):
        result = cases.materialize(self.material, self.raw)
        result.pop('id')
        return result

    def question(self, identity='gq2-001'):
        return {'id': identity, 'group': 'core', 'category': 'fact', 'difficulty': 'easy',
                'question': f'{identity}：角色甲说了什么？', 'reference_answer': '甲说了测试内容。',
                'story_topic': identity, 'tags': ['测试'], 'uncertainty': 'none',
                'key_points': [{'id': 'p1', 'kind': 'fact', 'statement': '测试结论', 'evidence_ids': ['e1']}],
                'evidence': [{'id': 'e1', 'statement': '角色甲陈述测试内容', 'sources': [self.anchor()]}],
                'annotation_status': 'draft', 'user_review': 'not_reviewed',
                'corpus_anchor_coverage': {'status': 'not_assessed'}}

    def document(self):
        return {'schema_version': 2, 'benchmark_id': 'genshin-story-core',
                'version': '2.0.0-pilot', 'story_cutoff': '2026-06-05',
                'source_snapshot': 'data/raw/snapshot', 'questions': [self.question()]}

    def corpus(self, segments):
        raw_text = '甲😀乙丙丁戊。'
        return [{'id': f'c{i}', 'text': '角色甲：' + raw_text[a:b],
                 'source_file': self.source_file, 'source_kind': 'wiki_excerpt',
                 'source_pointer': ['/对话/0/内容'], 'source_spans': [{'start': a, 'end': b}]}
                for i, (a, b) in enumerate(segments)]

    def test_materials_extract_unicode_offsets_speaker_and_hash(self):
        anchor = self.anchor()
        self.assertEqual(anchor['quote'], '😀乙丙丁')
        self.assertEqual(anchor['speaker'], '角色甲')
        self.assertEqual(anchor['source_kind'], 'wiki_excerpt')
        self.assertEqual(anchor['source_sha256'], hashlib.sha256((self.raw / self.source_file).read_bytes()).hexdigest())
        m = {**self.material, 'source_pointer': '/对话/1/内容', 'start': 0, 'end': 3}
        self.assertEqual(cases.materialize(m, self.raw)['speaker'], '')

    def test_top_level_story_field_and_rfc_root_pointer(self):
        source = self.raw / 'parsed/weapons/demo.json'
        source.parent.mkdir(parents=True)
        source.write_text('{"故事":"甲施展力量保护众人。"}', encoding='utf-8')
        result = cases.materialize({'id': 'W1', 'source_file': 'parsed/weapons/demo.json',
                                    'source_pointer': '/故事'}, self.raw)
        self.assertEqual(result['quote'], '甲施展力量保护众人。')
        self.assertNotIn('speaker', result)
        self.assertEqual(cases.resolve_pointer({'a': 1}, ''), {'a': 1})

    def test_invalid_material_ranges_pointers_and_paths_are_rejected(self):
        for changes in ({'start': True}, {'end': 99}, {'start': -1}, {'end': 1},
                        {'source_file': '../outside.json'}, {'source_file': 'C:/outside.json'},
                        {'source_file': 'parsed'}, {'source_file': 'parsed/../demo.json'},
                        {'source_file': 'parsed\\archon-quests\\demo.json'},
                        {'source_pointer': '/对话/-1/内容'}, {'source_pointer': '/bad~2name'},
                        {'source_pointer': '/对话/0'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cases.materialize({**self.material, **changes}, self.raw)

    def test_invalid_coverage_status_and_unknown_source_family_fail(self):
        doc = self.document()
        doc['questions'][0]['corpus_anchor_coverage'] = {'status': 'all_good'}
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='draft')
        path = self.raw / 'parsed/unknown/demo.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"story":"故事。"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            cases.materialize({'source_file': 'parsed/unknown/demo.json', 'source_pointer': '/story'}, self.raw)

    def test_quotes_speaker_source_kind_and_changed_files_fail_validation(self):
        for key, value in [('quote', '伪造原文'), ('speaker', '角色乙'), ('source_kind', 'official'),
                           ('source_sha256', '0' * 64), ('start', False)]:
            doc = self.document()
            doc['questions'][0]['evidence'][0]['sources'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                cases.validate_document(doc, self.raw, mode='draft')
        doc = self.document()
        (self.raw / self.source_file).write_text('{"对话": []}', encoding='utf-8')
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='draft')

    def test_evidence_links_and_point_kinds_are_checked(self):
        for changes in ({'evidence_ids': ['missing']}, {'evidence_ids': []}, {'kind': 'guess'}):
            doc = self.document()
            doc['questions'][0]['key_points'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cases.validate_document(doc, self.raw, mode='draft')
        doc = self.document()
        doc['questions'].append(copy.deepcopy(doc['questions'][0]))
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='draft')

    def test_adjacent_overlapping_and_renamed_chunks_cover_same_anchor(self):
        source = self.anchor()
        for segments in ([(0, 7)], [(0, 3), (3, 7)], [(0, 4), (2, 7)]):
            rows = self.corpus(segments)
            result = cases.anchor_coverage([source], rows, self.raw)
            self.assertEqual(result['status'], 'complete')
            for row in rows:
                row['id'] = 'renamed-' + row['id']
            self.assertEqual(cases.anchor_coverage([source], rows, self.raw)['status'], 'complete')

    def test_gap_partial_absent_and_forged_corpus_text_are_not_coverage(self):
        source = self.anchor()
        self.assertEqual(cases.anchor_coverage([source], self.corpus([(0, 2), (3, 7)]), self.raw)['status'], 'partial')
        self.assertEqual(cases.anchor_coverage([source], [], self.raw)['status'], 'missing')
        rows = self.corpus([(0, 7)])
        rows[0]['text'] = '伪造的分块正文'
        with self.assertRaises(ValueError):
            cases.anchor_coverage([source], rows, self.raw)

    def test_unicode_whitespace_gaps_are_ignored_and_real_text_is_reported(self):
        path = self.raw / self.source_file
        text = '甲 \t\r\n\u00a0\u2003\u3000乙'
        path.write_text(json.dumps({'对话': [{'说话者': '角色甲', '类型': 'character', '内容': text}]}, ensure_ascii=False), encoding='utf-8')
        anchor = cases.materialize({**self.material, 'start': 0, 'end': len(text)}, self.raw)
        anchor.pop('id')
        rows = [{'id': f'c{i}', 'text': '角色甲：' + quote, 'source_file': self.source_file,
                 'source_kind': 'wiki_excerpt', 'source_pointer': ['/对话/0/内容'],
                 'source_spans': [{'start': a, 'end': b}]}
                for i, (a, b, quote) in enumerate([(0, 1, '甲'), (len(text)-1, len(text), '乙')])]
        result = cases.anchor_coverage([anchor], rows, self.raw)
        self.assertEqual(result, {'status': 'complete', 'covered_anchors': 1, 'total_anchors': 1})
        details = []
        cases.anchor_coverage([anchor], rows, self.raw, details=details)
        self.assertEqual(details, [])
        result = cases.anchor_coverage([anchor], rows[:1], self.raw, details=details)
        self.assertEqual(result, {'status': 'partial', 'covered_anchors': 0, 'total_anchors': 1})
        self.assertEqual(details[0]['fragments'], [{'start': len(text)-1, 'end': len(text), 'quote': '乙'}])

    def test_chunks_covering_only_whitespace_do_not_count_as_partial(self):
        path = self.raw / self.source_file
        path.write_text(json.dumps({'对话': [{'说话者': '角色甲', '类型': 'character', '内容': ' \t乙'}]}, ensure_ascii=False), encoding='utf-8')
        anchor = cases.materialize({**self.material, 'start': 0, 'end': 3}, self.raw)
        anchor.pop('id')
        rows = [{'id': 'blank', 'text': '角色甲：', 'source_file': self.source_file,
                 'source_kind': 'wiki_excerpt', 'source_pointer': ['/对话/0/内容'],
                 'source_spans': [{'start': 0, 'end': 2}]}]
        self.assertEqual(cases.anchor_coverage([anchor], rows, self.raw)['status'], 'missing')

    def test_coverage_report_keeps_real_missing_quotes_out_of_questions(self):
        doc = self.document()
        original = copy.deepcopy(doc)
        report = cases.make_coverage_report(doc, self.corpus([(0, 2), (3, 7)]), self.raw)
        self.assertEqual(doc, original)
        self.assertEqual(report['summary']['status_counts'], {'partial': 1})
        missing = report['missing_evidence'][0]
        self.assertEqual(missing['question_id'], 'gq2-001')
        self.assertEqual(missing['evidence_id'], 'e1')
        self.assertEqual(missing['fragments'], [{'start': 2, 'end': 3, 'quote': '乙'}])
        self.assertNotIn('missing_ranges', json.dumps(report))

    def test_coverage_summary_rejects_verbose_or_malformed_fields(self):
        doc = self.document()
        for value in ({'status': 'complete', 'covered_anchors': 1, 'total_anchors': 1, 'missing_ranges': []},
                      {'status': 'complete', 'covered_anchors': True, 'total_anchors': 1},
                      {'status': 'complete', 'covered_anchors': 0, 'total_anchors': 1}):
            doc['questions'][0]['corpus_anchor_coverage'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                cases.validate_document(doc, self.raw, mode='draft')

    def test_coverage_command_writes_fingerprinted_local_report_and_refuses_overwrite(self):
        corpus = self.corpus([(0, 2), (3, 7)])
        doc = self.document()
        doc['questions'][0]['corpus_anchor_coverage'] = cases.anchor_coverage([self.anchor()], corpus, self.raw)
        questions_path = self.project / 'questions.json'
        cases.write_json(questions_path, doc)
        corpus_path = self.project / 'corpus.jsonl'
        corpus_path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in corpus) + '\n', encoding='utf-8')
        out = self.project / 'rag/data/coverage'
        args = ['coverage', '--questions', str(questions_path), '--raw-root', str(self.raw),
                '--corpus', str(corpus_path), '--mode', 'draft', '--output-dir', str(out)]
        with patch.object(cases, 'PROJECT', self.project), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cases.main(args), 0)
            saved = (out / 'coverage_report.json').read_bytes()
            self.assertEqual(cases.main(args), 1)
        self.assertEqual((out / 'coverage_report.json').read_bytes(), saved)
        report = cases.load_json(out / 'coverage_report.json')
        self.assertEqual(report['questions_sha256'], hashlib.sha256(questions_path.read_bytes()).hexdigest())
        self.assertEqual(report['corpus_sha256'], hashlib.sha256(corpus_path.read_bytes()).hexdigest())
        self.assertEqual(report['missing_evidence'][0]['fragments'][0]['quote'], '乙')
        self.assertNotIn('missing_ranges', questions_path.read_text(encoding='utf-8'))

    def test_all_joint_source_anchors_are_required_for_complete_coverage(self):
        first = self.anchor()
        second = cases.materialize({**self.material, 'source_pointer': '/对话/1/内容', 'start': 0, 'end': 3}, self.raw)
        second.pop('id')
        result = cases.anchor_coverage([first, second], self.corpus([(0, 7)]), self.raw)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['covered_anchors'], 1)
        self.assertEqual(result['total_anchors'], 2)

    def test_pilot_matrix_and_full_matrix_are_not_interchangeable(self):
        doc = self.document()
        doc['questions'] = []
        index = 1
        for category in cases.CATEGORIES:
            for difficulty in cases.DIFFICULTIES:
                q = self.question(f'gq2-{index:03d}')
                q.update(category=category, difficulty=difficulty)
                doc['questions'].append(q)
                index += 1
        doc['questions'][0]['uncertainty'] = 'premise_correction'
        for index, difficulty in [(101, 'medium'), (102, 'hard')]:
            q = self.question(f'gq2-{index:03d}')
            q.update(group='cross_story', difficulty=difficulty)
            doc['questions'].append(q)
        self.assertEqual(cases.validate_document(doc, self.raw, mode='pilot')['questions'], 14)
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='full')
        doc['questions'][0]['difficulty'] = 'medium'
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='pilot')

    def test_pending_evidence_does_not_count_as_an_accepted_case(self):
        doc = self.document()
        doc['questions'][0].update(annotation_status='pending_evidence', reference_answer=None)
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='pilot')

    def test_full_quota_includes_ten_uncertainty_cases_and_two_cross_levels(self):
        doc = self.document()
        doc.update(version='2.0.0', questions=[])
        i = 1
        for category, values in cases.CORE_MATRIX.items():
            for difficulty, count in zip(cases.DIFFICULTIES, values):
                for _ in range(count):
                    q = self.question(f'gq2-{i:03d}')
                    q.update(category=category, difficulty=difficulty)
                    if i <= 10:
                        q['uncertainty'] = 'uncertainty_analysis'
                    doc['questions'].append(q)
                    i += 1
        for i in range(101, 111):
            q = self.question(f'gq2-{i:03d}')
            q.update(group='cross_story', difficulty='medium' if i < 106 else 'hard')
            doc['questions'].append(q)
        self.assertEqual(cases.validate_document(doc, self.raw, mode='full')['questions'], 110)
        doc['questions'][0]['uncertainty'] = 'none'
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='full')

    def test_build_extracts_sources_and_requires_complete_independent_reviews(self):
        q = self.question()
        q['evidence'][0]['sources'] = [{'material_id': 'M1'}]
        draft = {'materials': [self.material], 'questions': [q]}
        doc = cases.build_document([draft], self.raw)
        self.assertEqual(doc['questions'][0]['evidence'][0]['sources'][0]['quote'], '😀乙丙丁')
        self.assertEqual(doc['questions'][0]['annotation_status'], 'draft')
        passed = {'model': 'test-reviewer', 'reasoning_effort': 'medium',
                  'input_sha256': cases.review_input(draft, self.raw)['input_sha256'],
                  'results': [{'question_id': 'gq2-001', 'status': 'passed', 'issues': []}]}
        doc = cases.build_document([draft], self.raw, reviews=[passed])
        self.assertEqual(doc['questions'][0]['annotation_status'], 'source_reviewed')
        self.assertEqual(doc['questions'][0]['user_review'], 'not_reviewed')
        for changes in ({'results': []}, {'results': [{'question_id': 'gq2-001', 'status': 'needs_revision'}]},
                        {'results': [{'question_id': 'gq2-001', 'status': 'passed', 'issues': [{'severity': 'important'}]}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cases.build_document([draft], self.raw, reviews=[{**passed, **changes}])

    def test_review_hash_binds_answers_evidence_materials_and_raw_bytes(self):
        q = self.question()
        q['evidence'][0]['sources'] = [{'material_id': 'M1'}]
        draft = {'materials': [self.material], 'questions': [q], 'generation_notes': ['excluded self assessment']}
        packet = cases.review_input(draft, self.raw)
        self.assertNotIn('generation_notes', packet)
        report = {'model': 'test-reviewer', 'reasoning_effort': 'medium',
                  'input_sha256': packet['input_sha256'],
                  'results': [{'question_id': q['id'], 'status': 'passed', 'issues': []}]}
        revised = copy.deepcopy(draft)
        revised['questions'][0]['reference_answer'] = '改过的新答案'
        with self.assertRaises(ValueError):
            cases.build_document([revised], self.raw, reviews=[report])
        for severity in ('critical', 'important', 'unknown', 'IMPORTANT'):
            bad = copy.deepcopy(report)
            bad['results'][0]['issues'] = [{'severity': severity}]
            with self.subTest(severity=severity), self.assertRaises(ValueError):
                cases.build_document([draft], self.raw, reviews=[bad])
        source = self.raw / self.source_file
        source.write_bytes(source.read_bytes() + b'\n')
        self.assertNotEqual(packet['input_sha256'], cases.review_input(draft, self.raw)['input_sha256'])
        with self.assertRaises(ValueError):
            cases.build_document([draft], self.raw, reviews=[report])

    def test_stale_coverage_and_unreferenced_evidence_are_rejected(self):
        doc = self.document()
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, corpus=self.corpus([(0, 7)]), mode='draft')
        doc['questions'][0]['corpus_anchor_coverage'] = cases.anchor_coverage([self.anchor()], self.corpus([(0, 7)]), self.raw)
        self.assertEqual(cases.validate_document(doc, self.raw, corpus=self.corpus([(0, 7)]), mode='draft')['questions'], 1)
        extra = copy.deepcopy(doc['questions'][0]['evidence'][0])
        extra['id'] = 'unused'
        doc['questions'][0]['evidence'].append(extra)
        with self.assertRaises(ValueError):
            cases.validate_document(doc, self.raw, mode='draft')

    def test_material_export_refuses_existing_output_raw_and_eval(self):
        selection = {'materials': [self.material]}
        out = self.project / 'rag/data/new'
        cases.export_materials(selection, self.raw, out, self.project)
        self.assertTrue((out / 'materials.json').is_file())
        for target in (out, self.raw / 'oops', self.project / 'rag/eval/oops'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                cases.export_materials(selection, self.raw, target, self.project)

    def test_install_archives_exact_bytes_and_protects_existing_backup(self):
        target = self.project / 'rag/eval/questions.json'
        target.parent.mkdir(parents=True)
        original = b'{"old": true}\r\n'
        target.write_bytes(original)
        backup = self.project / 'rag/data/install_backup'
        cases.install_document(self.document(), self.raw, target, backup, self.project, mode='draft')
        self.assertEqual((backup / 'questions_before.json').read_bytes(), original)
        self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['schema_version'], 2)
        with self.assertRaises(ValueError):
            cases.install_document(self.document(), self.raw, target, backup, self.project, mode='draft')
        with self.assertRaises(ValueError):
            cases.install_document(self.document(), self.raw, self.raw / 'unsafe.json',
                                   self.project / 'rag/data/other', self.project, mode='draft')

    def test_install_rejects_canonical_path_resolving_into_snapshot(self):
        target = self.project / 'rag/eval/questions.json'
        protected = self.raw / self.source_file
        original = protected.read_bytes()
        document = self.document()
        real_resolve = Path.resolve

        def redirected_resolve(path, *args, **kwargs):
            # Models an eval path or parent symlink/junction into the raw snapshot.
            return protected if path == target else real_resolve(path, *args, **kwargs)

        with patch.object(Path, 'resolve', redirected_resolve):
            with self.assertRaises(ValueError):
                cases.install_document(document, self.raw, target, self.project / 'rag/data/backup',
                                       self.project, mode='draft')
        self.assertEqual(protected.read_bytes(), original)

    def test_duplicate_json_keys_fail_instead_of_silently_overwriting(self):
        p = self.project / 'bad.json'
        p.write_text('{"id":"a","id":"b"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            cases.load_json(p)


if __name__ == '__main__':
    unittest.main()
