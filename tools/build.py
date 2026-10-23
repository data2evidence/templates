#!/usr/bin/env python3
"""Copy python/<flow>/<node>.py into flows/<flow>.json; never execute ETL code."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def python_nodes(value):
    if isinstance(value, dict):
        if value.get('type') == 'python_node':
            yield value
        for child in value.values():
            yield from python_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from python_nodes(child)


def node_files(document):
    """Shared filename mapping: duplicate names use their full unique node IDs."""
    nodes = list(python_nodes(document))
    names = Counter(node['data']['name'] for node in nodes)
    ids = [node['id'] for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError('Python node IDs must be unique across the flow')
    result = {}
    for node in nodes:
        name, node_id = node['data']['name'], node['id']
        for value in (name, node_id):
            if not isinstance(value, str) or not value or any(c in value for c in '/\\\0') or value in ('.', '..'):
                raise ValueError(f'Node name and ID must be usable as filenames: {value!r}')
        stem = f'{name}__{node_id}' if names[name] > 1 else name
        if stem in result:
            raise ValueError(f'Conflicting script filename: {stem}.py')
        result[stem] = node
    return result


def render(template, source):
    original = template.read_bytes()
    document = json.loads(original)
    nodes = node_files(document)
    files = {path.stem: path for path in source.glob('*.py')}
    missing, extra = nodes.keys() - files.keys(), files.keys() - nodes.keys()
    if missing or extra:
        raise ValueError(f'{template.name}: missing scripts {sorted(missing)}; unmatched scripts {sorted(extra)}')
    changed = False
    for stem, node in nodes.items():
        data = node['data']
        code = files[stem].read_bytes().decode('utf-8')
        if data.get('python_code') != code:
            data['python_code'] = code
            changed = True
    # Leave unchanged templates byte-for-byte intact, regardless of formatting.
    return (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode('utf-8') if changed else original


def build(root, flow=None, check=False):
    directories = {path.name: path for path in (root / 'python').iterdir() if path.is_dir() and not path.name.startswith(('.', '__'))}
    if flow is not None:
        if flow not in directories:
            raise ValueError(f'No Python source directory for flow: {flow}')
        directories = {flow: directories[flow]}
    pending = []
    # Validate every selected flow before writing any template.
    for name, source in sorted(directories.items()):
        template = root / 'flows' / f'{name}.json'
        output = render(template, source)
        if output != template.read_bytes():
            pending.append((template, output))
    if check:
        for template, _ in pending:
            print(f'Out of date: {template.name}')
        if pending:
            print('Run: python3 tools/build.py')
            return 1
    else:
        for template, output in pending:
            template.write_bytes(output)
            print(f'Updated: {template.name}')
    print(f'Checked {len(directories)} flow(s); {len(pending)} {"out of date" if check else "updated"}.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flow', nargs='?', help='Flow filename without .json; default: all managed flows')
    parser.add_argument('--check', action='store_true', help='Report stale JSON without writing')
    args = parser.parse_args()
    try:
        return build(ROOT, args.flow, args.check)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
