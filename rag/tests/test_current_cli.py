"""Current entrypoints must work without discarded experiment definitions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rag.scripts import prepare_eval
from rag.scripts import artifact_catalog, evaluate_rag_mvp as evaluate
from rag.scripts import prepare_rag_mvp as prepare
import hashlib


class CurrentEntryTests(unittest.TestCase):
    def evaluation_fixture(self, root):
        (root / 'rag/data/corpus').mkdir(parents=True)
        (root / 'rag/eval/smoke').mkdir(parents=True)
        (root / 'rag/config').mkdir()
        corpus = root / 'rag/data/corpus/corpus.jsonl'
        corpus.write_text(json.dumps({'id': 'a', 'title': '原文', 'text': '原文',
                                     'source_file': 'parsed/a.json', 'source_pointer': ['/text']}) + '\n')
        questions = root / 'rag/eval/smoke/questions.jsonl'
        questions.write_text(json.dumps({'id': 'q', 'question': '原文', 'category': 'fact',
                                        'reference_answer': '答', 'expected_evidence': [['a']]}) + '\n')
        (root / 'rag/config/local_api.json').write_text('{"top_k":5}')
        doc = {'schema_version': 2, 'baseline_id': 'test', 'smoke': {'input': 'rag/eval/smoke/questions.jsonl'},
               'datasets': {'full_corpus': {'path': 'rag/data/corpus/corpus.jsonl'}},
               'files': {p.relative_to(root).as_posix(): {'bytes': p.stat().st_size,
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (corpus, questions)}}
        (root / 'rag/catalog.json').write_text(json.dumps(doc))
        return corpus, questions

    def test_default_evaluation_rejects_changed_baseline_corpus_or_questions(self):
        for changed in ('corpus', 'questions'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                corpus, questions = self.evaluation_fixture(root)
                target = corpus if changed == 'corpus' else questions
                # Valid JSON and valid IDs remain; only a baseline value changes.
                value = json.loads(target.read_text())
                value['text' if changed == 'corpus' else 'question'] = 'different valid content'
                target.write_text(json.dumps(value) + '\n')
                with patch.object(evaluate, 'PROJECT', root), patch.object(evaluate, 'RAG_ROOT', root / 'rag'), \
                     patch.object(evaluate, 'api_request', side_effect=AssertionError('must not call API')):
                    self.assertEqual(evaluate.main([]), 1)
                self.assertFalse((root / 'rag/data/outputs').exists())

    def test_report_writer_cannot_overwrite_completed_or_existing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.evaluation_fixture(root)
            output = artifact_catalog.reserve_output(root, 'retrieval')
            target = output / 'results.jsonl'
            target.write_bytes(b'unique output')
            with patch.object(evaluate, 'PROJECT', root):
                with self.assertRaises(ValueError):
                    evaluate.write_report(output, [], {}, True)
                artifact_catalog.finish_output(root, output, 'completed')
                with self.assertRaises(ValueError):
                    evaluate.validate_output_dir(output)
                with self.assertRaises(ValueError):
                    evaluate.write_report(output, [], {}, True)
            self.assertEqual(target.read_bytes(), b'unique output')

    def test_explicit_custom_inputs_still_work_with_pure_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus, questions = self.evaluation_fixture(root)
            custom_corpus, custom_questions = root / 'custom.jsonl', root / 'custom_questions.jsonl'
            custom_corpus.write_bytes(corpus.read_bytes())
            custom_questions.write_bytes(questions.read_bytes())
            with patch.object(evaluate, 'PROJECT', root), patch.object(evaluate, 'RAG_ROOT', root / 'rag'), \
                 patch.object(evaluate, 'api_request', side_effect=AssertionError('must not call API')):
                self.assertEqual(evaluate.main(['--retrieval-only', '--corpus', str(custom_corpus),
                                                '--questions', str(custom_questions)]), 0)
            results = evaluate.load_jsonl(root / 'rag/data/outputs/retrieval/r001/results.jsonl')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['answers'], {})

    def test_profile_cli_records_effective_sampling_without_private_launch_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.evaluation_fixture(root)
            path = root / 'rag/config/local_api.json'
            path.write_text(json.dumps({'top_k': 5, 'profile': 'standard',
                'generation': {'temperature': 0.7, 'top_k': 20},
                'profiles': {'standard': {'max_tokens': 64, 'enable_thinking': True,
                                          'thinking_budget_tokens': 32}}}))
            path.with_name('local_api.local.json').write_text(json.dumps({
                'llama_cpp': {'model_path': 'private-model-sentinel.gguf', 'device': 'private-device-sentinel'}}))
            with patch.object(evaluate, 'PROJECT', root), patch.object(evaluate, 'RAG_ROOT', root / 'rag'), \
                 patch.object(evaluate, 'api_request', side_effect=AssertionError('must not call API')):
                self.assertEqual(evaluate.main(['--retrieval-only', '--profile', 'standard']), 0)
            output = root / 'rag/data/outputs/retrieval/r001'
            summary = json.loads((output / 'summary.json').read_text())
            manifest = json.loads((output / 'run_manifest.json').read_text())
            self.assertEqual(summary['temperature'], 0.7)
            self.assertEqual(summary['top_k'], 5)
            self.assertEqual(summary['generation']['top_k'], 20)
            self.assertEqual(summary['profile'], 'standard')
            self.assertEqual(summary['generation'], manifest['parameters']['generation'])
            self.assertNotIn('private-model-sentinel', json.dumps(manifest))
            self.assertNotIn('private-device-sentinel', json.dumps(summary))

    def test_full_preparation_is_default_and_does_not_promote_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.evaluation_fixture(root)
            raw = root / 'data/raw/test-snapshot'
            parsed = raw / 'parsed/weapons/a.json'
            parsed.parent.mkdir(parents=True)
            parsed.write_text(json.dumps({'名称': '遗物', '故事': '他曾击败魔兽。'}), encoding='utf-8')
            (raw / 'pages').mkdir()
            (raw / 'pages/a.json').write_text(json.dumps({'query': {'pages': {'1': {
                'pageid': 1, 'ns': 0, 'title': '遗物',
                'revisions': [{'slots': {'main': {'*': '{{武器\n|名称=遗物}}'}}}]
            }}}}), encoding='utf-8')
            before = (root / 'rag/catalog.json').read_bytes(), parsed.read_bytes()
            with patch.object(prepare, 'PROJECT', root), patch.object(evaluate, 'PROJECT', root):
                self.assertEqual(prepare.main(['--raw-root', str(raw)]), 0)
            records = evaluate.load_jsonl(root / 'rag/data/outputs/corpus/r001/corpus.jsonl')
            self.assertTrue(any(r['text'] == '他曾击败魔兽。' for r in records))
            self.assertTrue(all('source_spans' in r and 'source_kind' in r for r in records))
            self.assertEqual(((root / 'rag/catalog.json').read_bytes(), parsed.read_bytes()), before)
    def test_preparation_help_describes_full_default_and_has_no_sample_selection(self):
        result = subprocess.run([sys.executable, '-B', 'rag/scripts/prepare_rag_mvp.py', '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('--selection', result.stdout)
        self.assertIn('--all', result.stdout)

    def test_evaluation_rejects_removed_sample_mode(self):
        result = subprocess.run([sys.executable, '-B', 'rag/scripts/evaluate_rag_mvp.py', '--dataset', 'sample'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid choice', result.stderr)

    def test_question_preparation_reads_current_input_and_never_changes_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / 'data/raw/genshin_wiki_data_20260605/parsed/books/a.json'
            raw.parent.mkdir(parents=True)
            raw.write_text('{"text":"原文"}', encoding='utf-8')
            questions = root / 'rag/eval/questions.json'
            questions.parent.mkdir(parents=True)
            document = {'version': '0.5', 'custom_header': 'preserved', 'questions': [
                {'id': 'q', 'answer': '答', 'sources': [{'file': 'parsed/books/a.json', 'pointer': '/text'}]}]}
            questions.write_text(json.dumps(document), encoding='utf-8')
            catalog = root / 'rag/catalog.json'
            catalog.write_text(json.dumps({'schema_version': 2, 'baseline_id': 'test',
                                           'datasets': {'story_dev': {'path': 'rag/eval/questions.json'}}, 'files': {}}))
            before = catalog.read_bytes(), questions.read_bytes(), raw.read_bytes()
            with patch.object(prepare_eval, 'PROJECT', root):
                self.assertEqual(prepare_eval.main([]), 0)
                existing = root / 'rag/data/outputs/prepared/r001/questions.json'
                self.assertEqual(prepare_eval.main(['--output', str(existing)]), 1)
            generated = json.loads(existing.read_text(encoding='utf-8'))
            self.assertEqual(generated['custom_header'], 'preserved')
            self.assertEqual(generated['questions'][0]['sources'][0]['text'], '原文')
            self.assertEqual((catalog.read_bytes(), questions.read_bytes(), raw.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
