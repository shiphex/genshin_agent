"""Lossless presentation controls and explicitly synthetic first-turn history."""
from copy import deepcopy
import json

from Benchmarks.support.common import encoded


def render_content(content):
    lines = []
    for collection, singular in [('turns', 'turn'), ('sections', 'section')]:
        lines.append(collection + ':')
        for number, item in enumerate(content[collection], 1):
            lines.append(f'{singular} {number}')
            for key, value in item.items():
                if key == 'options':
                    lines.append('options:')
                    for index, option in enumerate(value, 1):
                        lines.append(f'option {index}')
                        lines.extend(f'{k}: {encoded(v)}' for k, v in option.items())
                    lines.append('end options')
                else:
                    lines.append(f'{key}: {encoded(value)}')
    return '\n'.join(lines)


def parse_content(text):
    result = {'turns': [], 'sections': []}
    collection, current, option = None, None, None
    for line in text.splitlines():
        if line in ('turns:', 'sections:'):
            collection = line[:-1]; current = option = None
        elif line.startswith(('turn ', 'section ')):
            current = {}; result[collection].append(current); option = None
        elif line == 'options:':
            current['options'] = []
        elif line.startswith('option '):
            option = {}; current['options'].append(option)
        elif line == 'end options':
            option = None
        else:
            key, value = line.split(': ', 1)
            (option if option is not None else current)[key] = json.loads(value)
    return result


def as_text(model_evidence):
    result = deepcopy(model_evidence)
    result['text'] = render_content(result.pop('content'))
    return result


def require_mapped(anchors):
    if not anchors or any(not a.get('ids') for a in anchors):
        raise ValueError('every required source anchor must map to a V2 chunk')
    return anchors


def correct_history(question, evidence, supporting_id, system):
    if supporting_id not in {e['id'] for e in evidence}:
        raise ValueError('correct history requires a reviewed supporting ID')
    supporting = next(e for e in evidence if e['id'] == supporting_id)
    qualification = '根据所给 Wiki 编纂，' if (supporting.get('knowledge_type') == 'wiki_compilation'
        or supporting.get('source', {}).get('kind') == 'wiki_compilation') else ''
    return {'synthetic_history': True, 'first_turn_model_requests': 0,
            'end_to_end_score': 'not_applicable', 'messages': [
        {'role': 'system', 'content': system}, {'role': 'user', 'content': question},
        {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'controlled-history', 'type': 'function', 'function': {
                'name': 'search_story', 'arguments': encoded({'query': '温迪 神之心 女士 夺走'})}}]},
        {'role': 'tool', 'tool_call_id': 'controlled-history',
         'content': encoded({'ok': True, 'result': {'evidence': evidence}})},
        {'role': 'assistant', 'content': f'{qualification}夺走温迪神之心的是「女士」。[{supporting_id}]'}]}
