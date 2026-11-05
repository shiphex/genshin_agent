"""Versioned corpus contracts, source access and compact model evidence (stdlib only)."""
from copy import deepcopy
import hashlib
import json
import re

SCHEMA_VERSION = 2
KNOWLEDGE_TYPES = {'dialogue', 'character_profile', 'character_story', 'character_voice',
                   'entity_lore', 'book_text', 'quest_description', 'wiki_compilation'}
SOURCE_KINDS = {'wiki_excerpt', 'wiki_compilation'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def version(row):
    value = row.get('schema_version', 1)
    if type(value) is not int or value not in (1, 2):
        raise ValueError('unsupported corpus schema_version')
    return value


def source_info(row):
    if version(row) == 2:
        return row['source']
    return {'snapshot': None, 'file': row.get('source_file'), 'kind': row.get('source_kind')}


def iter_units(row):
    """Yield body units in source order; grouped choices expose their individual locators."""
    if version(row) == 2:
        for turn in row['content']['turns']:
            if turn['kind'] == 'choice':
                yield from turn['options']
            else:
                yield turn
        yield from row['content']['sections']


def iter_locations(row):
    info = source_info(row)
    if version(row) == 1:
        spans = row.get('source_spans', [])
        for i, pointer in enumerate(row.get('source_pointer', [])):
            yield info['file'], pointer, spans[i] if i < len(spans) else None
    else:
        for unit in iter_units(row):
            yield info['file'], unit['pointer'], unit['span']


def render_text(content):
    pieces = []
    for turn in content['turns']:
        if turn['kind'] == 'choice':
            pieces.extend('[玩家选项；分支关系未知] ' + option['text'] for option in turn['options'])
        elif turn['kind'] == 'narration':
            pieces.append('[旁白] ' + turn['text'])
        elif turn['kind'] == 'speech':
            pieces.append((turn['speaker'] or '[原文说话者为空]') + '：' + turn['text'])
        else:
            pieces.append('[原文类型未知] ' + turn['text'])
    for section in content['sections']:
        prefix = section['field'] + '：' if section['pointer'].startswith('/角色/') else ''
        pieces.append(prefix + section['text'])
    return '\n\n'.join(pieces)


def record_id(record):
    identity = [SCHEMA_VERSION, record['source'], record['knowledge_type'],
                [(p, s) for _, p, s in iter_locations(record)]]
    return 's2' + hashlib.sha256(canonical(identity).encode('utf-8')).hexdigest()[:24]


def _text(value, name, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError('invalid ' + name)


def _locator(unit):
    p, span = unit.get('pointer'), unit.get('span')
    if not isinstance(p, str) or not p.startswith('/') or re.search(r'~(?![01])', p):
        raise ValueError('invalid body pointer')
    if (not isinstance(span, dict) or set(span) != {'start', 'end'}
            or type(span['start']) is not int or type(span['end']) is not int
            or not 0 <= span['start'] < span['end']):
        raise ValueError('invalid body source span')
    _text(unit.get('text'), 'body text')


def validate_record(row):
    if not isinstance(row, dict):
        raise ValueError('corpus record must be an object')
    if version(row) != 2:
        raise ValueError('expected structured corpus schema 2')
    if set(row) - {'score'} != {'schema_version', 'id', 'title', 'knowledge_type', 'metadata', 'source', 'content', 'text'}:
        raise ValueError('invalid structured record fields')
    for name in ('id', 'title', 'text'):
        _text(row.get(name), name)
    if row['knowledge_type'] not in KNOWLEDGE_TYPES:
        raise ValueError('invalid knowledge_type')
    info = row['source']
    if not isinstance(info, dict) or set(info) != {'snapshot', 'file', 'file_sha256', 'kind'}:
        raise ValueError('invalid source fields')
    _text(info['snapshot'], 'snapshot')
    if (not isinstance(info['file'], str) or not info['file'].startswith('parsed/')
            or any(x in info['file'] for x in ('..', '\\', ':'))):
        raise ValueError('invalid source file')
    if not isinstance(info['file_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', info['file_sha256']):
        raise ValueError('invalid source hash')
    if info['kind'] not in SOURCE_KINDS:
        raise ValueError('invalid source kind')
    meta = row['metadata']
    if not isinstance(meta, dict) or set(meta) != {'source_family', 'entity', 'source_version', 'context'}:
        raise ValueError('invalid metadata fields')
    _text(meta['source_family'], 'source family')
    if not isinstance(meta['entity'], dict) or set(meta['entity']) != {'type', 'name'}:
        raise ValueError('invalid entity')
    for key in ('type', 'name'):
        _text(meta['entity'][key], 'entity ' + key)
    if meta['source_version'] is not None and not isinstance(meta['source_version'], str):
        raise ValueError('invalid source version')
    context = meta['context']
    if not isinstance(context, dict) or set(context) != {'chapter', 'act', 'task_step', 'path', 'related_quests'}:
        raise ValueError('invalid context')
    for name in ('chapter', 'act', 'task_step'):
        if context[name] is not None and not isinstance(context[name], str):
            raise ValueError('invalid context ' + name)
    for name in ('path', 'related_quests'):
        if not isinstance(context[name], list) or not all(isinstance(x, str) for x in context[name]):
            raise ValueError('invalid context ' + name)
    body = row['content']
    if not isinstance(body, dict) or set(body) != {'turns', 'sections'}:
        raise ValueError('invalid content')
    if not all(isinstance(body[k], list) for k in body) or bool(body['turns']) == bool(body['sections']):
        raise ValueError('exactly one body list must be nonempty')
    if bool(body['turns']) != (row['knowledge_type'] == 'dialogue'):
        raise ValueError('knowledge type/body mismatch')
    for turn in body['turns']:
        if set(turn) != {'kind', 'source_type', 'speaker', 'text', 'row_pointer', 'pointer', 'span', 'options', 'quality_flags'}:
            raise ValueError('invalid turn fields')
        if turn['kind'] not in {'speech', 'narration', 'choice', 'unknown'}:
            raise ValueError('invalid turn kind')
        if turn['speaker'] is not None and not isinstance(turn['speaker'], str):
            raise ValueError('invalid speaker')
        if turn['source_type'] is not None and not isinstance(turn['source_type'], str):
            raise ValueError('invalid source type')
        if not isinstance(turn['row_pointer'], str) or not turn['row_pointer'].startswith('/'):
            raise ValueError('invalid row pointer')
        if not isinstance(turn['options'], list) or not isinstance(turn['quality_flags'], list) or not all(isinstance(x, str) for x in turn['quality_flags']):
            raise ValueError('invalid turn lists')
        if turn['kind'] == 'choice':
            if not turn['options'] or any(turn[k] is not None for k in ('text', 'pointer', 'span')):
                raise ValueError('invalid choice group')
            for option in turn['options']:
                if set(option) != {'text', 'pointer', 'span'}:
                    raise ValueError('invalid option fields')
                _locator(option)
        else:
            if turn['options']:
                raise ValueError('non-choice has options')
            _locator(turn)
    for section in body['sections']:
        if set(section) != {'field', 'heading_path', 'text', 'pointer', 'span'}:
            raise ValueError('invalid section fields')
        _text(section['field'], 'section field')
        if not isinstance(section['heading_path'], list) or not all(isinstance(x, str) for x in section['heading_path']):
            raise ValueError('invalid heading path')
        _locator(section)
    if render_text(body) != row['text']:
        raise ValueError('retrieval text differs from structured body')
    if record_id(row) != row['id']:
        raise ValueError('structured record ID differs from sources')


def assert_snapshot_match(corpus, snapshot, *, known_snapshot=None):
    known = {source_info(r)['snapshot'] for r in corpus if source_info(r).get('snapshot')}
    if known_snapshot:
        known.add(str(known_snapshot).replace('\\', '/').rstrip('/').rsplit('/', 1)[-1])
    expected = str(snapshot).replace('\\', '/').rstrip('/').rsplit('/', 1)[-1] if snapshot else None
    if len(known) > 1 or (known and expected and known != {expected}):
        raise ValueError('corpus/question source snapshot mismatch')


def to_model_evidence(row):
    if version(row) == 1:
        return deepcopy({k: v for k, v in row.items() if k != 'score'})
    validate_record(row)
    result = {k: deepcopy(row[k]) for k in ('id', 'title', 'knowledge_type', 'metadata', 'content')}
    result['source'] = {k: row['source'][k] for k in ('snapshot', 'file', 'kind')}
    # source_type, row_pointer and heading_path remain in the local full record.
    for turn in result['content']['turns']:
        for key in ('source_type', 'row_pointer'):
            turn.pop(key)
        if turn['kind'] != 'choice':
            turn.pop('options')
        else:
            for key in ('text', 'pointer', 'span'):
                turn.pop(key)
        if not turn['quality_flags']:
            turn.pop('quality_flags')
    for section in result['content']['sections']:
        section.pop('heading_path')
    return result
