import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from rag.scripts import export_hf_dataset as hf


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


class HuggingFaceDatasetExportTests(unittest.TestCase):
    def make_source(self, root, rows=None):
        source = root / "source"
        source.mkdir()
        rows = rows or [
            {"id": "a", "title": "题目", "type": "quests", "parent_id": "parsed/a.json",
             "text": "剧情原文", "source_file": "parsed/a.json", "source_pointer": ["/正文"],
             "source_spans": [{"start": 0, "end": 4}], "source_kind": "wiki_excerpt"},
            {"id": "b", "title": "编纂", "type": "books", "parent_id": "parsed/b.json",
             "text": "整理文字", "source_file": "parsed/b.json", "source_pointer": ["/正文"],
             "source_spans": [{"start": 0, "end": 4}], "source_kind": "wiki_compilation"},
        ]
        (source / "corpus.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        write_json(source / "audit.json", {"processed": len(rows)})
        (source / "exclusions.jsonl").write_text('{"reason":"example"}\n', encoding="utf-8")
        (source / "coverage.md").write_text("# 覆盖\n", encoding="utf-8")
        (source / "not-for-release.txt").write_text("local only\n", encoding="utf-8")
        return source

    def test_builds_exact_release_inventory_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source(root)
            output = root / "release"

            manifest = hf.build_release(source, output, expected_rows=2, input_snapshot="snapshot-test")

            data = output / "data/full/genshin_wiki_data_20260605"
            self.assertEqual(
                {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()},
                {"README.md", ".gitattributes", "data/full/genshin_wiki_data_20260605/corpus.jsonl",
                 "data/full/genshin_wiki_data_20260605/audit.json",
                 "data/full/genshin_wiki_data_20260605/exclusions.jsonl",
                 "data/full/genshin_wiki_data_20260605/coverage.md",
                 "data/full/genshin_wiki_data_20260605/manifest.json"},
            )
            self.assertEqual(manifest["rows"], 2)
            self.assertEqual(manifest["input_snapshot"], "snapshot-test")
            self.assertEqual(manifest["files"]["corpus.jsonl"]["sha256"],
                             hashlib.sha256((data / "corpus.jsonl").read_bytes()).hexdigest())
            self.assertIn("license: other", (output / "README.md").read_text(encoding="utf-8"))
            self.assertIn("filter=lfs", (output / ".gitattributes").read_text(encoding="utf-8"))
            self.assertNotIn("not-for-release", "\n".join(str(path) for path in output.rglob("*")))
            self.assertEqual(hf.verify_release(output, expected_rows=2), manifest)

    def test_rejects_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source(root)
            output = root / "release"
            output.mkdir()

            with self.assertRaisesRegex(ValueError, "new"):
                hf.build_release(source, output, expected_rows=2, input_snapshot="snapshot-test")

    def test_rejects_invalid_corpus_row_before_writing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source(root, rows=[{"id": "missing-required-fields"}])
            output = root / "release"

            with self.assertRaisesRegex(ValueError, "required"):
                hf.build_release(source, output, expected_rows=1, input_snapshot="snapshot-test")
            self.assertFalse(output.exists())

    def test_verification_detects_hash_and_row_count_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source(root)
            output = root / "release"
            hf.build_release(source, output, expected_rows=2, input_snapshot="snapshot-test")
            corpus = output / "data/full/genshin_wiki_data_20260605/corpus.jsonl"
            corpus.write_text(corpus.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "row count|hash"):
                hf.verify_release(output, expected_rows=2)


if __name__ == "__main__":
    unittest.main()
