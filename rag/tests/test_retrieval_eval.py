"""Source-location proxies, reproducible runs, and immutable baseline boundaries."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rag.scripts import evaluate_retrieval as evaluate
from rag.scripts import evaluate_rag_mvp as retriever


def row(identity, file='parsed/a.json', pointers=None):
    return {'id': identity, 'title': '契约', 'text': '契约与公平',
            'source_file': file, 'source_pointer': pointers or ['/a']}


def source(pointer='/a', file='parsed/a.json'):
    return {'file': file, 'pointer': pointer}


class MetricTests(unittest.TestCase):
    def test_exact_locations_deduplicate_both_annotations_and_retrieved_chunks(self):
        sources = [source(), source(), source('/b'), source('/missing')]
        corpus = [row('a', pointers=['/a', '/b']), row('duplicate'),
                  row('wrong-file', file='parsed/other.json', pointers=['/missing'])]
        result = evaluate.score_locations(sources, corpus[:2], evaluate.corpus_locations(corpus))
        self.assertEqual(result['annotated_locations'], 3)
        self.assertEqual(result['matched_locations'], 2)
        self.assertEqual(result['hit_at_k'], 1)
        self.assertAlmostEqual(result['coverage_at_k'], 2 / 3)
        self.assertEqual(result['unmapped_locations'], 1)
        self.assertEqual(result['sources'][-1]['in_corpus'], False)

    def test_same_file_or_same_pointer_alone_is_not_a_hit_and_negative_control_drops_metric(self):
        corpus = [row('good'), row('pointer-only', file='parsed/other.json'),
                  row('file-only', pointers=['/b'])]
        locations = evaluate.corpus_locations(corpus)
        good = evaluate.score_locations([source()], corpus[:1], locations)
        bad = evaluate.score_locations([source()], corpus[1:], locations)
        self.assertEqual((good['hit_at_k'], good['coverage_at_k']), (1, 1))
        self.assertEqual((bad['hit_at_k'], bad['coverage_at_k']), (0, 0))
        empty = evaluate.score_locations([], [], locations)
        self.assertIsNone(empty['hit_at_k'])
        self.assertIsNone(empty['coverage_at_k'])

    def test_summary_has_explicit_macro_micro_denominators_and_unscored_count(self):
        corpus = [row('a')]
        results = []
        for number, sources in enumerate(([source()], [source(), source('/b'), source('/c')], [])):
            results.append({'question_id': str(number), 'retrieval_seconds': .25,
                            'source_location': evaluate.score_locations(sources, corpus,
                                                                        evaluate.corpus_locations(corpus))})
        summary = evaluate.summarize(results, 3, 'completed', .5)
        self.assertEqual(summary['scored_questions'], 2)
        self.assertEqual(summary['unscored_questions'], 1)
        self.assertEqual(summary['source_location_hit_at_k'], 1)
        self.assertAlmostEqual(summary['source_location_macro_coverage_at_k'], 2 / 3)
        self.assertEqual(summary['source_location_micro_coverage_at_k'], .5)
        self.assertEqual((summary['matched_locations'], summary['annotated_locations']), (2, 4))
        self.assertEqual(summary['semantic_coverage'], 'not_evaluated')
        self.assertEqual(summary['answer_correctness'], 'not_evaluated')
        self.assertTrue(summary['complete'])


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / 'rag/scripts'
        scripts.mkdir(parents=True)
        for module in (evaluate, retriever, evaluate.artifact_catalog):
            target = scripts / Path(module.__file__).name
            target.write_bytes(Path(module.__file__).read_bytes())
        (self.root / 'rag/eval').mkdir(parents=True)
        (self.root / 'rag/data/corpus').mkdir(parents=True)
        self.questions = self.root / 'rag/eval/questions.json'
        self.corpus = self.root / 'rag/data/corpus/corpus.jsonl'
        self.document = {'version': '0.5', 'dataset': 'test-dev', 'source_snapshot': 'data/raw/test',
                         'questions': [{'id': 'q1', 'type': 'fact', 'difficulty': 'easy',
                                        'question': '契约', 'answer': 'GOLD_NOT_A_QUERY',
                                        'keywords': ['GOLD_NOT_A_QUERY'], 'sources': [source()]}]}
        self.write_questions(self.document)
        self.corpus.write_text(json.dumps(row('a'), ensure_ascii=False) + '\n', encoding='utf-8')
        self.catalog = self.root / 'rag/catalog.json'
        self.catalog.write_text(json.dumps({'schema_version': 2, 'baseline_id': 'current-003',
            'raw_root': 'data/raw/test', 'source_snapshot': 'test',
            'datasets': {'full_corpus': {'path': 'rag/data/corpus/corpus.jsonl', 'rows': 1},
                         'story_dev': {'path': 'rag/eval/questions.json', 'version': '0.5', 'questions': 1}},
            'files': {p.relative_to(self.root).as_posix(): {'bytes': p.stat().st_size,
                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in (self.questions, self.corpus)}}), encoding='utf-8')
        self.before = {p: p.read_bytes() for p in (self.catalog, self.questions, self.corpus)}

    def write_questions(self, value):
        self.questions.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def run_main(self, args=()):
        with patch.object(evaluate, 'PROJECT', self.root), \
             patch.object(evaluate, '__file__', str(self.root / 'rag/scripts/evaluate_retrieval.py')), \
             patch.object(retriever, '__file__', str(self.root / 'rag/scripts/evaluate_rag_mvp.py')), \
             patch.object(evaluate.artifact_catalog, '__file__', str(self.root / 'rag/scripts/artifact_catalog.py')), \
             patch.object(retriever, 'api_request', side_effect=AssertionError('no API allowed')), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return evaluate.main(list(args))

    def load_run(self, number=1):
        output = self.root / f'rag/data/outputs/retrieval/r{number:03d}'
        return output, json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))

    def test_records_actual_inputs_parameters_source_copies_and_artifact_hashes(self):
        self.assertEqual(self.run_main(['--top-k', '2']), 0)
        output, manifest = self.load_run()
        self.assertEqual(manifest['execution_status'], 'completed')
        self.assertEqual(manifest['review_status'], 'not_reviewed')
        self.assertEqual(manifest['parameters']['top_k'], 2)
        self.assertEqual(manifest['parameters']['protocol_id'], 'retrieval-source-location-v0')
        identity = manifest['parameters']['identity']
        self.assertEqual(identity['questions']['version'], '0.5')
        self.assertEqual(identity['corpus']['sha256'], hashlib.sha256(self.corpus.read_bytes()).hexdigest())
        self.assertIn('python', manifest['parameters']['runtime'])
        self.assertIn('source_commit', manifest)
        self.assertEqual(manifest['metadata']['processed_questions'], 1)
        self.assertEqual(set(manifest['metadata']['artifacts']), {'results.jsonl', 'summary.json', 'report.md'})
        for name in ('results.jsonl', 'summary.json', 'report.md'):
            self.assertEqual(manifest['metadata']['artifacts'][name]['sha256'],
                             hashlib.sha256((output / name).read_bytes()).hexdigest())
        copied = {p.name for p in (output / 'executed_source').glob('*.py')}
        self.assertEqual(copied, {'evaluate_retrieval.py', 'evaluate_rag_mvp.py', 'artifact_catalog.py'})
        result = json.loads((output / 'results.jsonl').read_text(encoding='utf-8'))
        self.assertEqual(result['question'], '契约')
        self.assertNotIn('GOLD_NOT_A_QUERY', json.dumps(result))
        self.assertEqual(result['retrieved'][0]['id'], 'a')
        self.assertEqual({p: p.read_bytes() for p in self.before}, self.before)

    def test_repeated_runs_keep_rankings_and_metrics_and_never_overwrite(self):
        self.assertEqual(self.run_main(), 0)
        first, _ = self.load_run()
        saved = {p.name: p.read_bytes() for p in first.iterdir() if p.is_file()}
        self.assertEqual(self.run_main(['--output-dir', str(first)]), 1)
        self.assertEqual(self.run_main(), 0)
        second, _ = self.load_run(2)
        a, b = [json.loads((p / 'results.jsonl').read_text(encoding='utf-8')) for p in (first, second)]
        self.assertEqual(a['retrieved'], b['retrieved'])
        self.assertEqual(a['source_location'], b['source_location'])
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir() if p.is_file()}, saved)

    def test_uses_one_real_index_and_only_question_text_for_every_query(self):
        custom = self.root / 'two.json'
        document = copy.deepcopy(self.document)
        document['questions'].append({**document['questions'][0], 'id': 'q2', 'question': '公平'})
        custom.write_text(json.dumps(document), encoding='utf-8')
        original = evaluate.LexicalIndex
        index = original([row('a')])
        with patch.object(evaluate, 'LexicalIndex', return_value=index) as construction, \
             patch.object(index, 'search', wraps=index.search) as search:
            self.assertEqual(self.run_main(['--questions', str(custom), '--top-k', '3']), 0)
        construction.assert_called_once()
        self.assertEqual(search.call_args_list, [unittest.mock.call('契约', 3), unittest.mock.call('公平', 3)])

    def test_seal_failure_still_finishes_failed_run_and_keeps_number(self):
        with patch.object(evaluate.artifact_catalog, 'seal_inputs', side_effect=OSError('unavailable')):
            self.assertEqual(self.run_main(), 1)
        output, manifest = self.load_run()
        self.assertEqual(manifest['execution_status'], 'failed')
        self.assertEqual(manifest['metadata']['processed_questions'], 0)
        summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
        self.assertFalse(summary['complete'])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.load_run(2)[1]['execution_status'], 'completed')

    def test_changed_default_inputs_are_rejected_before_allocating_output(self):
        for target in (self.questions, self.corpus):
            with self.subTest(target=target):
                saved = target.read_bytes()
                target.write_bytes(saved + b' ')
                self.assertEqual(self.run_main(), 1)
                self.assertFalse((self.root / 'rag/data/outputs').exists())
                target.write_bytes(saved)

    def test_explicit_inputs_record_custom_identity_without_baseline_snapshot_claim(self):
        custom = self.root / 'custom.jsonl'
        custom.write_bytes(self.corpus.read_bytes())
        self.assertEqual(self.run_main(['--corpus', str(custom)]), 0)
        _, manifest = self.load_run()
        identity = manifest['parameters']['identity']['corpus']
        self.assertFalse(identity['baseline_verified'])
        self.assertIsNone(identity['source_snapshot'])

    def test_input_changing_while_loaded_cannot_complete_with_a_misleading_hash(self):
        custom = self.root / 'changing.jsonl'
        custom.write_bytes(self.corpus.read_bytes())
        loader = retriever.load_jsonl
        def change_after_read(path):
            rows = loader(path)
            custom.write_bytes(custom.read_bytes() + b'\n')
            return rows
        with patch.object(retriever, 'load_jsonl', side_effect=change_after_read):
            self.assertEqual(self.run_main(['--corpus', str(custom)]), 1)

    def test_rejects_raw_baseline_and_nested_output_targets(self):
        for target in ('data/raw/out', 'rag/data/corpus/new', 'rag/data/outputs/retrieval/run/nested'):
            with self.subTest(target=target):
                self.assertEqual(self.run_main(['--output-dir', str(self.root / target)]), 1)
        self.assertEqual({p: p.read_bytes() for p in self.before}, self.before)

    def test_invalid_inputs_fail_without_changing_baseline(self):
        invalid = []
        for key, value in [('questions', []), ('version', ''), ('questions', [self.document['questions'][0]] * 2)]:
            changed = copy.deepcopy(self.document)
            changed[key] = value
            invalid.append(changed)
        for sources in (None, [source('no-slash')], [source('/bad~2')], [source(file='../escape')]):
            changed = copy.deepcopy(self.document)
            changed['questions'][0]['sources'] = sources
            invalid.append(changed)
        custom = self.root / 'bad.json'
        for value in invalid:
            custom.write_text(json.dumps(value), encoding='utf-8')
            self.assertEqual(self.run_main(['--questions', str(custom)]), 1)
        for text in ('', '{}\n', json.dumps(row('a')) + '\n' + json.dumps(row('a'))):
            custom.write_text(text, encoding='utf-8')
            self.assertEqual(self.run_main(['--corpus', str(custom)]), 1)
        self.assertEqual(self.run_main(['--top-k', '0']), 1)
        self.assertEqual({p: p.read_bytes() for p in self.before}, self.before)

    def test_failures_and_interruptions_keep_flushed_results_and_terminal_status(self):
        self.document['questions'].append({**self.document['questions'][0], 'id': 'q2'})
        custom = self.root / 'two.json'
        custom.write_text(json.dumps(self.document), encoding='utf-8')
        for number, (failure, status, code) in enumerate(((RuntimeError('broken'), 'failed', 1),
                                                         (KeyboardInterrupt(), 'interrupted', 130)), 1):
            with patch.object(evaluate.LexicalIndex, 'search', side_effect=[[row('a')], failure]):
                self.assertEqual(self.run_main(['--questions', str(custom)]), code)
            output, manifest = self.load_run(number)
            self.assertEqual(manifest['execution_status'], status)
            self.assertEqual(len((output / 'results.jsonl').read_text(encoding='utf-8').splitlines()), 1)
            summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
            self.assertFalse(summary['complete'])
            self.assertEqual((summary['processed_questions'], summary['expected_questions']), (1, 2))


if __name__ == '__main__':
    unittest.main()
