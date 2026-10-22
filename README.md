Flow templates

## Editing Python nodes

Edit Python in `python/<flow>/<node-name>.py`. The existing
`flows/<flow>.json` owns the graph and all other configuration.
MIMIC is the first managed template: see [its Python files](python/mimic_omop/).

From the repository root, using Python 3.10+ with no extra dependencies:

```sh
python3 tools/build.py              # Update all managed templates
python3 tools/build.py mimic_omop   # Update one template
python3 tools/build.py --check     # Verify without writing (also used by CI)
```

Import `flows/mimic_omop.json` into the canvas as before. Commit both the Python
changes and updated JSON. Review `.py` diffs for code and JSON diffs for graph
changes. The tool copies code strings; it does not execute the ETL.

### Adding another template

Extract the existing JSON first (use its filename without `.json`):

```sh
python3 tools/extract.py mimic_omop  # One template
python3 tools/extract.py             # All templates
```

This creates `python/<flow>/<node-name>.py` directly from each node's
`python_code`, preserving the exact code and leaving the JSON untouched.
Existing identical files are skipped; differing files cause an error before
any writes, protecting local edits. Templates without Python nodes are skipped.
No tool changes or separate source graph are needed. Unique node names keep
`<node-name>.py`. Duplicate names use `<node-name>__<full-node-id>.py`, so each
node has its own file even when the code is identical. Both tools use the same
mapping, including inside nested flows; Python node IDs must be unique.
Names and IDs must be usable as filenames. Renaming a node or introducing a
duplicate name may require renaming existing files; extract into a separate
review directory to see the expected filenames. Non-Python nodes need no files.

Missing scripts, unmatched scripts, duplicate Python node IDs, or a missing
JSON template cause the build to fail before writing any selected flow. Only
templates with changed code are written; flows without a Python directory are
untouched. Changed JSON is formatted with two-space indentation.

Python files are authoritative for code. If you edit Python in the canvas,
extract a review copy and reconcile its Python files before building, or the
build will replace those edits with the file contents. Graph edits stay in JSON.

```sh
python3 tools/extract.py mimic_omop --output-dir /tmp/flow-review
```

The review files are written to `/tmp/flow-review/mimic_omop/`. Compare them
with `python/mimic_omop/` and copy back the changes you want to keep. Both tools
also handle Python nodes inside nested flows.

Run tooling tests with:

```sh
python3 -B -m unittest discover -s tools -p 'test_build.py' -v
```
