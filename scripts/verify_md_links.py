"""Check repository Markdown links without loading local data or external URLs.

V0 supports inline/reference links and images, ATX/setext headings and <a id>.
It is a deliberately bounded scanner, not a complete CommonMark renderer.
"""
import argparse
import html
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import unquote, urlsplit


LOCAL_ROOTS = ('data/', 'rag/data/')
FROZEN_SOURCES = {'rag/docs/recovery/crawler_handoff.md': 'frozen crawler recovery handoff'}
LABEL = re.compile(r'!?\[((?:\\.|[^\]\\\n])+)\]')
INLINE_CODE = re.compile(r'(`+)(?!`)(.+?)(?<!`)\1(?!`)', re.DOTALL)


def repository_files(root):
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others',
                             '--exclude-standard', '-z'], capture_output=True, timeout=20)
    if result.returncode:
        raise ValueError('git ls-files failed: ' + result.stderr.decode('utf-8', errors='replace'))
    return set(result.stdout.decode('utf-8').split('\0')) - {''}


def visible_text(source):
    """Mask comments, frontmatter and code blocks while retaining line positions."""
    source = re.sub(r'<!--[\s\S]*?-->', lambda m: re.sub(r'[^\n]', ' ', m[0]), source)
    lines = source.splitlines(keepends=True)
    fence, frontmatter = None, bool(lines and lines[0].strip() == '---')
    output = []
    for index, line in enumerate(lines):
        masked = False
        if frontmatter:
            masked = True
            if index and line.strip() == '---':
                frontmatter = False
        elif fence:
            masked = True
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$', line):
                fence = None
        else:
            match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if match:
                fence, masked = match[1], True
            elif line.startswith(('    ', '\t')):
                masked = True
        output.append(re.sub(r'[^\n]', ' ', line) if masked else line)
    return ''.join(output)


def destination(text, start):
    """Read <space-containing> or balanced unquoted destination; ignore title."""
    start += len(text[start:]) - len(text[start:].lstrip())
    if start < len(text) and text[start] == '<':
        end = text.find('>', start + 1)
        return (text[start + 1:end], end + 1) if end >= 0 else ('', start)
    end, depth = start, 0
    while end < len(text):
        char = text[end]
        if char == '\\' and end + 1 < len(text):
            end += 2
            continue
        if char == '(':
            depth += 1
        elif char == ')':
            if not depth:
                break
            depth -= 1
        elif char.isspace() and not depth:
            break
        end += 1
    return text[start:end], end


def reference_key(label):
    return ' '.join(label.split()).casefold()


def inline_link_end(line, end):
    """Consume the optional quoted title so its literal brackets aren't links."""
    cursor = end
    while cursor < len(line) and line[cursor].isspace():
        cursor += 1
    if cursor < len(line) and line[cursor] in '\"\'(':
        closing = ')' if line[cursor] == '(' else line[cursor]
        cursor += 1
        while cursor < len(line):
            if line[cursor] == '\\':
                cursor += 2
            elif line[cursor] == closing:
                cursor += 1
                break
            else:
                cursor += 1
        while cursor < len(line) and line[cursor].isspace():
            cursor += 1
    return cursor + 1 if line[cursor:cursor + 1] == ')' else end


def links(text):
    text = INLINE_CODE.sub(lambda m: re.sub(r'[^\n]', ' ', m[0]), text)
    definitions, output = {}, []
    for number, line in enumerate(text.splitlines(), 1):
        definition = re.match(r'^ {0,3}\[([^\]]+)\]:\s*(.*)$', line)
        if definition:
            url, _ = destination(definition[2], 0)
            definitions.setdefault(reference_key(definition[1]), url)
            output.append((number, url, None))
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r'^ {0,3}\[[^\]]+\]:', line):
            continue
        consumed = 0
        for label in LABEL.finditer(line):
            if label.start() < consumed or (label.start() and line[label.start() - 1] == '\\'):
                continue
            end = label.end()
            if line[end:end + 1] == '(':
                url, consumed = destination(line, end + 1)
                consumed = inline_link_end(line, consumed)
                output.append((number, url, None))
            elif line[end:end + 1] == '[':
                close = line.find(']', end + 1)
                if close >= 0:
                    key = reference_key(line[end + 1:close] or label[1])
                    output.append((number, definitions.get(key, ''), None if key in definitions else key))
                    consumed = close + 1
            elif reference_key(label[1]) in definitions:
                output.append((number, definitions[reference_key(label[1])], None))
    return sorted(output)


def heading_text(title):
    def prose(text):
        text = re.sub(r'!?\[([^\]]+)\](?:\([^)]*\)|\[[^\]]*\])', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        return re.sub(r'(?<!\w)(\*{1,2}|_{1,2})(?=\S)(.+?)(?<=\S)\1(?!\w)', r'\2', text)

    result, end = [], 0
    for code in INLINE_CODE.finditer(title):
        result.extend([prose(title[end:code.start()]), code[2]])
        end = code.end()
    result.append(prose(title[end:]))
    return html.unescape(''.join(result))


def anchors(text):
    result = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        heading = re.match(r'^ {0,3}#{1,6}\s+(.+?)(?:\s+#+\s*)?$', line)
        title = heading[1] if heading else None
        if title is None and index + 1 < len(lines) and line.strip() and re.match(r'^ {0,3}(?:=+|-+)\s*$', lines[index + 1]):
            title = line.strip()
        if title is None:
            continue
        title = heading_text(title).lower()
        base = ''.join(c for c in title if unicodedata.category(c)[0] in 'LN' or c in '_ -').replace(' ', '-')
        slug, counter = base, 0
        while slug in result:
            counter += 1
            slug = f'{base}-{counter}'
        result.add(slug)
    clean = INLINE_CODE.sub('', text)
    result.update(re.findall(r'<a\s+[^>]*\b(?:id|name)=["\']([^"\']+)["\']', clean))
    return result


def verify(root):
    files = repository_files(root)
    errors, notices, cache = [], [], {}
    sources = sorted(name for name in files if name.endswith('.md') and (root / name).is_file())
    for name in sources:
        if name in FROZEN_SOURCES:
            notices.append(f'FROZEN {name}: {FROZEN_SOURCES[name]} (source excluded; inbound links checked)')
            continue
        source = root / name
        for line, url, missing in links(visible_text(source.read_text(encoding='utf-8-sig'))):
            where = f'{name}:{line}: {url}'
            if missing is not None:
                errors.append(f'{name}:{line}: undefined reference [{missing}]')
                continue
            if url.startswith('//') or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', url):
                continue
            parts = urlsplit(html.unescape(url))
            raw = re.sub(r'\\([() ])', r'\1', unquote(parts.path))
            if raw.startswith('/') or '\\' in raw:
                errors.append(where + ': use a repository-relative path')
                continue
            target = (source.parent / raw).resolve() if raw else source.resolve()
            if not target.is_relative_to(root):
                errors.append(where + ': path outside repository')
                continue
            relative = target.relative_to(root).as_posix()
            if relative not in files and any(relative == prefix.rstrip('/') or relative.startswith(prefix)
                                             for prefix in LOCAL_ROOTS):
                notices.append(where + ': LOCAL not supplied by Git; not validated')
                continue
            supplied = relative in files or (target.is_dir() and
                       (target == root or any(f.startswith(relative + '/') for f in files)))
            if not supplied or not target.exists():
                errors.append(where + ': missing repository target (absent or excluded from Git discovery)')
                continue
            if parts.fragment and target.suffix.lower() == '.md':
                if target not in cache:
                    cache[target] = anchors(visible_text(target.read_text(encoding='utf-8-sig')))
                if unquote(parts.fragment) not in cache[target]:
                    errors.append(where + ': missing Markdown anchor')
    return errors, notices, len(sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        errors, notices, count = verify(args.root.resolve())
        for notice in notices:
            print(notice)
        for error in errors:
            print(error, file=sys.stderr)
        print(f'Markdown links: {count} sources, {len(errors)} errors, {len(notices)} explicit exclusions')
        return int(bool(errors))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Markdown links failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
