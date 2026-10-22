Flow templates

## Editing Python nodes

- The existing `flows/<flow>.json` contains the complete flow

- Extract python node into
`python/<flow>/<node-name>.py` for easier editing and review, preserving the exact code and leaving the JSON untouched.

- From the repository root, using Python 3.10+ with no extra dependencies:

```sh
python3 tools/build.py              # Update all managed templates
python3 tools/build.py Load_OMOP_CDM_v54   # Update one template
python3 tools/build.py --check     # Verify without writing (also used by CI)
```

### Adding another template

Extract the existing JSON first (use its filename without `.json`):

```sh
python3 tools/extract.py Load_OMOP_CDM_v54  # One template
python3 tools/extract.py             # All templates
```

### Development

For example, to edit the **Load OMOP CDM v5.4** template, run these commands
from the repository root. Use the exact filename stem, including capitalization:

```sh
# Optional: Extract flows/Load_OMOP_CDM_v54.json into readable Python files.
python3 tools/extract.py Load_OMOP_CDM_v54

# Edit the files in python/Load_OMOP_CDM_v54/, then update the JSON.
python3 tools/build.py Load_OMOP_CDM_v54

# Optional: verify that the JSON matches the Python files.
python3 tools/build.py Load_OMOP_CDM_v54 --check
```
