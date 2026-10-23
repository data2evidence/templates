#!/usr/bin/env python3
"""Extract flows/<flow>.json into python/<flow>/<node>.py without executing code."""
import argparse
import json
from pathlib import Path
import sys

from build import ROOT, node_files


def extract(root, flow=None, output=None):
    templates = {path.stem: path for path in (root / 'flows').glob('*.json')}
    if flow is not None:
        if flow not in templates:
            raise ValueError(f'No JSON template for flow: {flow}')
        templates = {flow: templates[flow]}
    output = Path(output) if output is not None else root / 'python'
    pending = []
    count = 0
    # Validate all files before writing; never overwrite differing local code.
    for name, template in sorted(templates.items()):
        destination = output / name
        expected = set()
        for stem, node in node_files(json.loads(template.read_bytes())).items():
            data = node['data']
            node_name = data['name']
            code = data['python_code']
            if not isinstance(code, str):
                raise ValueError(f'{template.name}: {node_name}: python_code must be a string')
            path = destination / f'{stem}.py'
            expected.add(path.name)
            content = code.encode('utf-8')
            if path.exists():
                if path.read_bytes() != content:
                    raise ValueError(f'Local code differs: {path}. Use --output-dir with a new directory to compare.')
            else:
                pending.append((path, content))
            count += 1
        extra = {path.name for path in destination.glob('*.py')} - expected
        if extra:
            raise ValueError(f'{template.name}: unmatched local scripts {sorted(extra)}. Use a new --output-dir.')
    for path, content in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print(f'Found {count} Python node(s); created {len(pending)} file(s) in {output}.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flow', nargs='?', help='Flow filename without .json; default: all templates')
    parser.add_argument('--output-dir', type=Path, help='Alternative parent directory for review copies')
    args = parser.parse_args()
    try:
        return extract(ROOT, args.flow, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
