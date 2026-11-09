"""Validate planned interventions independently of whether their fields exist."""
from copy import deepcopy
import json

from rag.scripts.corpus_schema import assert_snapshot_match
from .evidence import parse_content


def validate_inputs(corpus, suite, raw_root):
    assert_snapshot_match(corpus, suite.get('source_snapshot'))
    if str(suite.get('source_snapshot', '')).replace('\\', '/').split('/')[-1] != raw_root.name:
        raise ValueError('scenario/raw snapshot mismatch')


def validate_request(payload, *, forced):
    messages = payload.get('messages', [])
    prefix = {'role': 'assistant', 'content': '<tool_call>\n'}
    if forced:
        tools = payload.get('tools', [])
        if (not messages or messages[-1] != prefix or payload.get('tool_choice') != 'required'
                or payload.get('continue_final_message') != 'content'
                or payload.get('add_generation_prompt') is not False or len(tools) != 1
                or tools[0].get('function', {}).get('name') != 'search_story'):
            raise ValueError('planned forced first request is missing its required fields')
    elif (any(m == prefix for m in messages) or 'continue_final_message' in payload
          or 'add_generation_prompt' in payload or payload.get('tool_choice') == 'required'):
        raise ValueError('forced prefill leaked into an ordinary request')
    if payload.get('chat_template_kwargs', {}).get('enable_thinking') is not False:
        raise ValueError('experiment requires thinking disabled')


def assert_presentation_pair(structured, flat, message_indices):
    normalized = deepcopy(flat)
    for index in message_indices:
        left = json.loads(structured['messages'][index]['content'])
        right = json.loads(normalized['messages'][index]['content'])
        for hit in right['result']['evidence']:
            hit['content'] = parse_content(hit.pop('text'))
        if left != right:
            raise ValueError('presentation changed evidence information')
        normalized['messages'][index]['content'] = structured['messages'][index]['content']
    if normalized != structured:
        raise ValueError('presentation pair changed fields outside the planned tool content')
