"""Charts expose the recorded location proxies without changing evaluation data."""
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from rag.scripts import evaluate_retrieval as evaluate
from rag.scripts import retrieval_report as report


def result(identity, matched, annotated, kind='fact', difficulty='easy'):
    return {'question_id': identity, 'type': kind, 'difficulty': difficulty, 'retrieval_seconds': .01,
            'source_location': {'annotated_locations': annotated, 'matched_locations': matched,
                                'hit_at_k': int(matched > 0) if annotated else None,
                                'coverage_at_k': matched / annotated if annotated else None, 'sources': []}}


def summary(rows, expected=None, status='completed'):
    value = evaluate.summarize(rows, len(rows) if expected is None else expected, status, .5)
    value.update(top_k=5, identity={'questions': {'version': '0.5', 'sha256': 'q' * 64},
                                 'corpus': {'sha256': 'c' * 64}})
    return value


class ReportTests(unittest.TestCase):
    def test_distribution_includes_empty_labels_and_exact_ratio_boundaries(self):
        rows = [result('a', 0, 2), result('b', 1, 3), result('c', 1, 2),
                result('d', 2, 2), result('e', 0, 0)]
        self.assertEqual(report.coverage_distribution(rows), [1, 1, 1, 1, 1])

    def test_group_metrics_use_only_labelled_questions_and_preserve_macro_micro_difference(self):
        rows = [result('a', 1, 1), result('b', 1, 3), result('c', 0, 0)]
        group = report.group_metrics(rows, 'type')[0]
        self.assertEqual((group['questions'], group['scored'], group['hits']), (3, 2, 2))
        self.assertAlmostEqual(group['macro'], 2 / 3)
        self.assertEqual(group['micro'], .5)

    def test_svg_and_markdown_have_numeric_fallbacks_and_preserve_input_summary(self):
        rows = [result('a', 1, 2)]
        data = summary(rows)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            report.write_report(output, data, rows)
            svg = ET.parse(output / 'metrics.svg').getroot()
            self.assertEqual(svg.attrib['role'], 'img')
            labels = ''.join(svg.itertext())
            self.assertIn('50.00%', labels)
            markdown = (output / 'report.md').read_text(encoding='utf-8')
            self.assertIn('](metrics.svg)', markdown)
            self.assertIn('| 来源位置 Hit@5 | 100.00% |', markdown)
            self.assertIn('| 微平均 Coverage@5 | 50.00% |', markdown)
            self.assertIn('语义覆盖和最终答案正确性均未评测', markdown)
            self.assertEqual(data, summary(rows))
            with self.assertRaises(FileExistsError):
                report.write_report(output, data, rows)

    def test_partial_unlabelled_run_is_explicit_and_never_drawn_as_zero_success(self):
        rows = [result('unlabelled', 0, 0)]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            report.write_report(output, summary(rows, 2, 'interrupted'), rows)
            labels = ''.join(ET.parse(output / 'metrics.svg').getroot().itertext())
            self.assertIn('未完成', labels)
            self.assertIn('1/2', labels)
            self.assertIn('未计分', labels)
            self.assertNotIn('0.00%', labels)
            self.assertIsNone(report.group_metrics(rows, 'type')[0]['macro'])


if __name__ == '__main__':
    unittest.main()
