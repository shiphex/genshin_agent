"""Relocate frozen question sources into a new snapshot; never edit the baseline or raw data."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import ZipFile

try:
    from . import artifact_catalog, corpus_schema
    from .prepare_rag_mvp import resolve_pointer, read_json
except ImportError:
    import artifact_catalog, corpus_schema
    from prepare_rag_mvp import resolve_pointer, read_json

PROJECT = Path(__file__).resolve().parents[2]


def comparison_text(text):
    """Known display-only equivalences, used for matching, never for writing a source."""
    text = re.sub(r'\{\{颜色\|[^|{}]*\|([^{}]*)\}\}', r'\1', text)
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    text = re.sub(r'\[\[([^|\[\]]+)(?:\|([^\[\]]+))?\]\]', lambda m: m[2] or m[1], text)
    return re.sub(r'\s+', '', html.unescape(text))


def question_objects(document):
    if isinstance(document, dict):
        if 'id' in document and 'sources' in document:
            yield document
        else:
            for value in document.values():
                yield from question_objects(value)
    elif isinstance(document, list):
        for value in document:
            yield from question_objects(value)


def migrate_document(document, old_loader, new_loader, snapshot, *, allow_incomplete=False):
    candidate = deepcopy(document)
    report = []
    for question in question_objects(candidate):
        for source in question['sources']:
            file, pointer = source['file'], source['pointer']
            if not file.startswith('parsed/') or any(t in file for t in ('..', '\\', ':')):
                raise ValueError('invalid question source file')
            old, new = old_loader(file), new_loader(file)
            original = resolve_pointer(old, pointer)
            if not isinstance(original, str) or not original.strip():
                raise ValueError('old source must be nonempty text')
            if 'text' in source and source['text'] != original:
                raise ValueError('frozen source text differs from old snapshot')
            entry = {'question_id': question['id'], 'file': file, 'old_pointer': pointer,
                     'old_text': original, 'new_pointer': None, 'status': 'unresolved'}
            candidates = []
            match = re.fullmatch(r'(.*/对话)/(\d+)(/.*)', pointer)
            if match:
                base, index, tail = match.groups()
                old_row = resolve_pointer(old, base + '/' + index)
                entry['old_row'] = old_row
                try:
                    rows = resolve_pointer(new, base)
                except (KeyError, IndexError, TypeError):
                    rows = []
                for j, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    target = base + '/' + str(j) + tail
                    try:
                        actual = resolve_pointer(new, target)
                    except (KeyError, IndexError, TypeError):
                        continue
                    if not isinstance(actual, str):
                        continue
                    status = None
                    if all(row.get(k) == v for k, v in old_row.items()):
                        status = 'exact_row'
                    else:
                        same_stage = row.get('所属任务流程') == old_row.get('所属任务流程')
                        same_speaker = row.get('说话者') == old_row.get('说话者')
                        same_kind = row.get('类型') == old_row.get('类型')
                        equivalent = comparison_text(actual) == comparison_text(original)
                        speaker = old_row.get('说话者')
                        prefixed = (isinstance(speaker, str) and speaker and
                                    any(actual.startswith(speaker + colon) and comparison_text(actual[len(speaker)+1:]) == comparison_text(original)
                                        for colon in (':', '：')))
                        if same_stage and prefixed and not row.get('说话者') and row.get('类型') in ('narration', '旁白'):
                            status = 'upstream_attribution_pending'
                        elif same_stage and equivalent and same_kind:
                            status = 'display_change' if same_speaker else 'upstream_speaker_change'
                    if status:
                        candidates.append((target, actual, row, status))
                exact = [c for c in candidates if c[3] == 'exact_row']
                if exact:
                    candidates = exact
            else:
                try:
                    actual = resolve_pointer(new, pointer)
                    if isinstance(actual, str) and comparison_text(actual) == comparison_text(original):
                        candidates = [(pointer, actual, None, 'unchanged' if actual == original else 'display_change')]
                except (KeyError, IndexError, TypeError):
                    pass
            if len(candidates) == 1:
                target, actual, row, status = candidates[0]
                entry.update(new_pointer=target, new_text=actual, status=status)
                if row is not None:
                    entry['new_row'] = row
                source['pointer'] = target
                if 'text' in source:
                    source['text'] = actual
            else:
                entry['candidate_pointers'] = [c[0] for c in candidates]
                source['migration_status'] = 'unresolved'
                source['original_snapshot'] = document.get('source_snapshot')
            report.append(entry)
    incomplete = any(r['status'] == 'unresolved' for r in report)
    if incomplete and not allow_incomplete:
        return None, report
    if 'questions' in candidate:
        candidate['version'] = '0.6'
        candidate['source_snapshot'] = 'data/raw/' + snapshot
        candidate['migration_status'] = 'candidate_incomplete' if incomplete else 'located'
    return candidate, report


class ArchiveReader:
    def __init__(self, path):
        self.archive = ZipFile(path)
        self.lookup, self.cache = {}, {}
        for info in self.archive.infolist():
            name = info.filename if info.flag_bits & 0x800 else info.filename.encode('cp437').decode('gbk')
            if name in self.lookup:
                raise ValueError('ambiguous archive filename')
            self.lookup[name] = info

    def read(self, file):
        if file not in self.cache:
            self.cache[file] = json.loads(self.archive.read(self.lookup[file]).decode('utf-8-sig'))
        return self.cache[file]

    def close(self):
        self.archive.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-archive', type=Path, required=True)
    parser.add_argument('--raw-root', type=Path)
    parser.add_argument('--questions', type=Path, default=PROJECT / 'rag/eval/questions.json')
    parser.add_argument('--review20', type=Path, default=PROJECT / 'rag/eval/review20.json')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    output, archive = None, None
    try:
        catalog = artifact_catalog.load_catalog(PROJECT)
        raw = (args.raw_root or PROJECT / catalog['raw_input']['path']).resolve()
        archive = ArchiveReader(args.old_archive)
        cache = {}
        def load(file):
            path = (raw / file).resolve()
            if not path.is_relative_to(raw / 'parsed'):
                raise ValueError('source outside parsed')
            if file not in cache:
                cache[file] = read_json(path)
            return cache[file]
        output = artifact_catalog.reserve_output(PROJECT, 'prepared', args.output_dir)
        artifacts, report = {}, []
        for path in (args.questions, args.review20):
            candidate, entries = migrate_document(read_json(path), archive.read, load, raw.name, allow_incomplete=True)
            for entry in entries:
                entry['input'] = path.name
            report.extend(entries)
            if candidate is not None:
                artifacts[path.name] = candidate
        issues = []
        for entry in report:
            if entry['status'] not in ('upstream_attribution_pending', 'upstream_speaker_change', 'display_change', 'unresolved'):
                continue
            name = 'pages/' + PurePosixPath(entry['file']).name
            page = raw / name
            old_bytes = archive.archive.read(archive.lookup[name])
            new_bytes = page.read_bytes()
            pages = json.loads(new_bytes.decode('utf-8-sig'))['query']['pages']
            raw_text = next(iter(pages.values()))['revisions'][0]['slots']['main']['*']
            quote = entry['old_text']
            speaker = entry.get('old_row', {}).get('说话者')
            lines = [line for line in raw_text.splitlines() if comparison_text(quote) in comparison_text(line)]
            if speaker:
                lines = [line for line in lines if speaker in line]
            entry['page_evidence'] = {'file': name, 'sha256': hashlib.sha256(new_bytes).hexdigest(),
                'same_original_page': old_bytes == new_bytes, 'matching_lines': lines[:3]}
            if entry['status'] == 'upstream_attribution_pending':
                if old_bytes != new_bytes or not lines:
                    raise ValueError('attribution change needs matching unchanged original page evidence')
                row_pointer = entry['new_pointer'].rsplit('/内容', 1)[0]
                issue = {'file': entry['file'], 'row_pointer': row_pointer,
                         'source_sha256': hashlib.sha256((raw / entry['file']).read_bytes()).hexdigest(),
                         'flags': ['upstream_attribution_pending'], 'page_evidence': entry['page_evidence']}
                if issue not in issues:
                    issues.append(issue)
        inputs = [args.old_archive, args.questions, args.review20, Path(__file__),
                  Path(corpus_schema.__file__), Path(artifact_catalog.__file__), Path(__file__).with_name('prepare_rag_mvp.py')]
        inputs += [raw / f for f in sorted(cache)]
        inputs += sorted({raw / entry['page_evidence']['file'] for entry in report if 'page_evidence' in entry})
        artifact_catalog.seal_inputs(PROJECT, output, inputs,
            {'source_snapshot': raw.name, 'old_archive_sha256': hashlib.sha256(args.old_archive.read_bytes()).hexdigest(),
             'candidate_version': '0.6', 'promote_baseline': False})
        for name, document in artifacts.items():
            (output / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        counts = dict(Counter(entry['status'] for entry in report))
        summary = {'schema_version': 1, 'source_snapshot': raw.name, 'sources': len(report), 'statuses': counts,
                   'candidate_status': 'candidate_incomplete' if counts.get('unresolved') else 'located_with_quality_warnings' if issues else 'located',
                   'review_status': 'not_reviewed', 'entries': report}
        (output / 'migration_report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output / 'source_issues.json').write_text(json.dumps({'schema_version': 1, 'source_snapshot': raw.name, 'issues': issues},
                                                        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name != 'run_manifest.json'}
        metadata = {k: v for k, v in summary.items() if k != 'entries'}
        metadata['artifact_sha256'] = hashes
        artifact_catalog.finish_output(PROJECT, output, 'completed_with_errors' if counts.get('unresolved') else 'completed', metadata)
        print(json.dumps({**metadata, 'output_dir': str(output)}, ensure_ascii=False))
        return int(bool(counts.get('unresolved')))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        if output:
            artifact_catalog.finish_output(PROJECT, output, 'failed')
        print('Migration failed: ' + str(error), file=sys.stderr)
        return 1
    finally:
        if archive:
            archive.close()


if __name__ == '__main__':
    raise SystemExit(main())
