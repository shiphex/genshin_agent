"""Offline Markdown and SVG presentation of recorded retrieval-location metrics."""
from html import escape


METRICS = [('来源位置 Hit', 'source_location_hit_at_k'),
           ('宏平均 Coverage', 'source_location_macro_coverage_at_k'),
           ('微平均 Coverage', 'source_location_micro_coverage_at_k')]
BINS = ['未命中 · 0%', '部分命中 · (0, 50%)', '部分命中 · [50%, 100%)',
        '全部标注位置 · 100%', '无标注 · 未计分']
LABELS = {'fact': '事实', 'causal': '因果', 'worldbuilding': '世界观', 'relationship': '关系',
          'easy': '简单', 'medium': '中等', 'hard': '困难'}


def percentage(value):
    return '未计分' if value is None else f'{value:.2%}'


def coverage_distribution(results):
    counts = [0] * len(BINS)
    for row in results:
        location = row['source_location']
        n, d = location['matched_locations'], location['annotated_locations']
        index = 4 if not d else 0 if not n else 3 if n == d else 1 if n * 2 < d else 2
        counts[index] += 1
    return counts


def group_metrics(results, field):
    groups = {}
    for result in results:
        groups.setdefault(result[field], []).append(result['source_location'])
    rows = []
    order = ('easy', 'medium', 'hard') if field == 'difficulty' else ('fact', 'causal', 'worldbuilding', 'relationship')
    for label, locations in sorted(groups.items(), key=lambda item: (order.index(item[0]) if item[0] in order else len(order), item[0])):
        scored = [r for r in locations if r['annotated_locations']]
        annotated = sum(r['annotated_locations'] for r in scored)
        rows.append({'label': label, 'questions': len(locations), 'scored': len(scored),
                     'hits': sum(r['matched_locations'] > 0 for r in scored),
                     'macro': sum(r['matched_locations'] / r['annotated_locations'] for r in scored) / len(scored) if scored else None,
                     'micro': sum(r['matched_locations'] for r in scored) / annotated if annotated else None})
    return rows


def chart_svg(run_name, summary, results):
    """Fixed percentage axes; unscored/partial states remain visibly distinct."""
    state = '执行完成' if summary['complete'] else '未完成 · 仅展示已处理题'
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="610" viewBox="0 0 1000 610" '
                'role="img" aria-labelledby="title description">',
                '<title id="title">检索来源位置指标与逐题覆盖分布</title>',
                '<desc id="description">来源定位代理指标；不代表语义覆盖或最终答案正确。无标注单独计数。</desc>',
                '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#263449;font-size:15px}'
                '.small{font-size:13px;fill:#52647a}.heading{font-size:21px;font-weight:600}</style>',
                '<rect width="1000" height="610" rx="14" fill="#f5f7fc"/>',
                '<rect x="20" y="20" width="960" height="570" rx="12" fill="white"/>',
                f'<text x="44" y="55" class="heading">{escape(run_name)} · 来源定位概览 · Top-{summary["top_k"]}</text>',
                f'<text x="44" y="84" class="small">{state} · {summary["processed_questions"]}/{summary["expected_questions"]} 题；'
                f'计分 {summary["scored_questions"]} 题，无标注 {summary["unscored_questions"]} 题</text>',
                '<text x="44" y="109" class="small">位置命中不等于论据完整召回；语义覆盖和最终答案正确性均未评测。</text>']
    left, width = 300, 540
    for tick in (0, 25, 50, 75, 100):
        x = left + width * tick / 100
        elements.extend([f'<line x1="{x}" y1="138" x2="{x}" y2="267" stroke="#e7ecf3"/>',
                         f'<text x="{x}" y="132" text-anchor="middle" class="small">{tick}%</text>'])
    for number, (label, key) in enumerate(METRICS):
        y = 150 + number * 42
        value = summary[key]
        elements.extend([f'<text x="44" y="{y + 17}">{label}@{summary["top_k"]}</text>',
                         f'<rect x="{left}" y="{y}" width="{width}" height="24" rx="4" fill="#eef2f8"/>'])
        if value is not None:
            elements.append(f'<rect x="{left}" y="{y}" width="{value * width:.3f}" height="24" rx="4" fill="#5269bb"/>')
        elements.append(f'<text x="870" y="{y + 17}">{percentage(value)}</text>')
    elements.extend(['<text x="44" y="307" class="heading">逐题标注位置覆盖分布</text>',
                     '<text x="44" y="333" class="small">每题计入一个分组；柱长按已处理题数缩放，右侧标明题数。</text>'])
    for number, (label, count) in enumerate(zip(BINS, coverage_distribution(results))):
        y = 354 + number * 38
        length = width * count / len(results) if results else 0
        elements.extend([f'<text x="44" y="{y + 17}">{escape(label)}</text>',
                         f'<rect x="{left}" y="{y}" width="{width}" height="23" rx="4" fill="#eef2f8"/>',
                         f'<rect x="{left}" y="{y}" width="{length:.3f}" height="23" rx="4" fill="#168481"/>',
                         f'<text x="870" y="{y + 17}">{count} 题</text>'])
    elements.extend(['<text x="44" y="568" class="small">100% 仅表示全部已标注位置被命中；未进入语料的位置保留在 Coverage 分母。</text>', '</svg>'])
    return '\n'.join(elements) + '\n'


def _cell(value):
    return escape(str(value)).replace('|', '\\|').replace('\n', ' ')


def _seconds(value, milliseconds=False):
    if value is None:
        return '未测量'
    return f'{value * 1000:.2f} ms' if milliseconds else f'{value:.3f} s'


def write_report(output, summary, results):
    """Write new presentation files exclusively; callers own run lifecycle/hash sealing."""
    if any((output / name).exists() for name in ('report.md', 'metrics.svg')):
        raise FileExistsError('report presentation already exists')
    state = '执行完成' if summary['complete'] else '未完成，以下仅统计已处理题目'
    lines = ['# 检索评测 V0', '',
             f"运行：`{_cell(output.name)}` · **{state}** · {summary['processed_questions']}/{summary['expected_questions']} 题 · Top-K={summary['top_k']}。", '',
             '> 指标只表示已标注来源的位置命中，是证据获取的代理指标。字段中某个片段命中不证明论据完整召回；'
             '语义覆盖和最终答案正确性均未评测。来源标注也不穷尽等价出处。', '',
             '## 指标总览', '', '| 指标 | 结果 | 统计口径 |', '| --- | ---: | --- |']
    definitions = ['命中至少一个标注位置的题数／计分题数', '每道计分题 Coverage 的等权平均',
                   f"命中 {summary['matched_locations']}/{summary['annotated_locations']} 个逐题唯一标注位置"]
    lines.extend(f"| {label}@{summary['top_k']} | {percentage(summary[key])} | {definition} |"
                 for (label, key), definition in zip(METRICS, definitions))
    lines.extend(['', f"计分 {summary['scored_questions']} 题；无标注 {summary['unscored_questions']} 题。"
                  '未进入语料的位置保留在分母中；失败或中断结果不构成完整评测。', '',
                  '![来源位置指标与逐题标注覆盖分布；下方表格提供数值](metrics.svg)', '',
                  '| 逐题覆盖分组 | 题数 |', '| --- | ---: |'])
    lines.extend(f'| {label} | {count} |' for label, count in zip(BINS, coverage_distribution(results)))
    for field, heading in (('type', '按题型'), ('difficulty', '按难度')):
        lines.extend(['', f'## {heading}', '', '| 分组 | 已处理／计分 | 命中题数 | Hit@K | 宏 Coverage@K | 微 Coverage@K |',
                      '| --- | ---: | ---: | ---: | ---: | ---: |'])
        for group in group_metrics(results, field):
            label = _cell(LABELS.get(group['label'], group['label']))
            hit = group['hits'] / group['scored'] if group['scored'] else None
            lines.append(f"| {label} | {group['questions']}/{group['scored']} | {group['hits']} | "
                         f"{percentage(hit)} | {percentage(group['macro'])} | {percentage(group['micro'])} |")
    timings = summary['retrieval_seconds']
    lines.extend(['', '## 耗时', '', '| 阶段／统计 | 耗时 |', '| --- | ---: |',
                  f"| 索引构建 | {_seconds(summary['index_build_seconds'])} |",
                  f"| 检索总计 | {_seconds(timings['total'])} |"])
    lines.extend(f"| 每题{label} | {_seconds(timings[key], True)} |" for label, key in (('平均', 'mean'), ('中位数', 'median'), ('最大', 'max')))
    lines.extend(['', '每题只计一次 search 调用，不含加载、匹配、写盘；不是端到端耗时或性能回退判定。', '',
                  '## 未进入语料的标注位置', '', '| 题号 | 文件 | Pointer |', '| --- | --- | --- |'])
    lines.extend(f"| {_cell(s['question_id'])} | {_cell(s['file'])} | {_cell(s['pointer'])} |" for s in summary['unmapped_locations'])
    if not summary['unmapped_locations']:
        lines.append('| 无（仅指已处理题目） | — | — |')
    identity = summary['identity']
    lines.extend(['', '## 复现与比较', '',
                  f"协议：`{summary['protocol_id']}`；题库版本：`{_cell(identity['questions']['version'])}`。", '',
                  f"题库 SHA-256：`{identity['questions']['sha256']}`。", '',
                  f"语料 SHA-256：`{identity['corpus']['sha256']}`。", '',
                  '[逐题结果](results.jsonl) · [机器可读汇总](summary.json) · [运行记录](run_manifest.json)。', '',
                  '复现按运行记录的 parameters、inputs 和 executed_source 核对。A/B 固定协议、题库与语料哈希及 Top-K，'
                  '按 question_id 对齐；有意改变的因素单列。运行编号和时间戳不参与指标比较，耗时需同等环境重复采样。'])
    with (output / 'metrics.svg').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(chart_svg(output.name, summary, results))
    with (output / 'report.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines) + '\n')
