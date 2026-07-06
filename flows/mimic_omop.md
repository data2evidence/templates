# MIMIC_OMOP flow template

`mimic_omop.json` is a dataflow template that converts a [MIMIC-IV](https://physionet.org/content/mimiciv/) dataset into the [OMOP CDM 5.3](https://ohdsi.github.io/CommonDataModel/cdm53.html) format. The conversion runs inside an intermediate [DuckDB](https://duckdb.org/) file and can then export the resulting CDM schema to a Postgres or SAP HANA database for use with ATLAS and other OHDSI tools.

## Prerequisites

1. **MIMIC-IV CSV files** available inside the dataflow execution runtime (the container that executes the flow) at `/app/mimic_omop/mimic`, keeping the PhysioNet folder layout (files may be `.csv` or `.csv.gz`):

   ```
   /app/mimic_omop/mimic
       hosp/
           admissions.csv.gz
           ...
       icu/
           chartevents.csv.gz
           ...
   ```

2. **OMOP vocabulary files** downloaded from [Athena](https://athena.ohdsi.org/) (tab-delimited CSVs such as `CONCEPT.csv`, `VOCABULARY.csv`, ...) available at `/app/mimic_omop/vocab`. Files without a matching staging table (e.g. `CONCEPT_CPT4.csv`) are skipped with a warning.

3. **The `mimic_omop_conversion_plugin`** installed in the dataflow execution runtime. The template only contains orchestration code; the DDL, staging, ETL, and unload SQL scripts are read from `flows/mimic_omop_conversion_plugin/external/`.

4. A **target database** registered in d2e (only needed when exporting): the `database_code` must resolve to a Postgres or HANA database reachable from the execution runtime.

## System setup for the full MIMIC-IV dataset

Complementary setup notes for running the conversion on a complete MIMIC-IV dataset (supported versions: **v2.2** and **v3.1**; waveform and clinical note data are not convered).

### Transform the vocabulary files

The Athena vocabulary CSVs must be transformed to the expected quoted format before loading (see [load-vocab.md](https://github.com/data2evidence/d2e/blob/dev2/docs/2-load/7-load-vocab.md)):

```bash
mkdir transformed
for CSV_FILE in *.csv; do sed "s/\"/\"\"/g;s/\t/\"\t\"/g;s/\(.*\)/\"\1\"/" $CSV_FILE >> ./transformed/$CSV_FILE; done
```

This escapes existing double quotes, wraps each value in double quotes (safely handling embedded tabs and newlines), and writes the processed files to `transformed/`. Mount the `transformed/` folder as the vocabulary directory.

### Mount the data volumes

Add the following entries to `PREFECT_DOCKER_VOLUMES` in the d2e `.env` file so the data is visible at the paths the flow expects:

```
/path/to/mimic/data:/app/mimic_omop/mimic
/path/to/vocabulary/data:/app/mimic_omop/vocab
```

### Memory and disk requirements

> **Warning:** insufficient RAM or disk space will crash the container with an out-of-memory (OOM) error. The staging of ICU tables and `cdm_drug_era.sql` are the most memory-intensive steps.

Set `D2E_DUCKDB_THREADS` and `D2E_DUCKDB_MEMORY_LIMIT` in the `.env` file. Minimum recommended resources, benchmarked on a 32 GB RAM / 512 GB disk server (MIMIC-IV v2.2, full dataset):

- Container memory limit: ≥ 20 GB
- DuckDB memory limit: 15 GB
- DuckDB threads: 4
- Peak disk usage: ~100 GB

### Estimated runtimes

Benchmarked on the same 32 GB RAM / 512 GB disk server (MIMIC-IV v2.2, full dataset):

| Stage | Duration |
| --- | --- |
| Loading MIMIC-IV v2.2 + OMOP vocabulary into DuckDB | ~25 min |
| Staging | ~20 min |
| ETL transformations | ~50 min |
| Unloading CDM to DuckDB file (~61 GB) | ~5 min |
| Exporting DuckDB → PostgreSQL | ~25 min |
| Final PostgreSQL database size | ~46 GB |

## How to use

1. In the d2e Dataflow UI, import `mimic_omop.json` as a new dataflow (or select the built-in template).
2. Adjust the flow variables (see below) — at minimum `flow_action_type`, `database_code`, and `schema_name`.
3. Run the flow. Progress for each stage is written to the Prefect run logs.

## Flow variables

| Variable | Default | Description |
| --- | --- | --- |
| `flow_action_type` | `mimic_to_database` | Which part of the pipeline to run. One of `mimic_to_database`, `mimic_to_duckdb`, `duckdb_to_database` (see run modes below). |
| `database_code` | `demo_database` | Code of the target database registered in d2e. Used only when exporting. |
| `schema_name` | `dataflow_ui_mimic` | Schema created in the target database to hold the exported CDM tables. |
| `overwrite_schema` | `True` | If the target schema already exists: `True` drops and recreates it, `False` fails the run. |
| `use_trex_connection` | `False` | `False` uses the direct path (DuckDB `ATTACH` for Postgres, SQLAlchemy chunked inserts for HANA). `True` exports through the trex pgwire passthrough (works for both Postgres and HANA). |
| `chunk_size` | `5000` | Number of rows per insert batch during export. |
| `load_mimic_vocab` | `True` | `False` skips the load and staging stages (`load_mimic_data`, `load_vocab`, `staging_mimic`), e.g. to re-run only the ETL against a DuckDB file that already contains staged data. |
| `duckdb_file_name` | `/app/mimic_omop/mimic/mimic_omop_duckdb` | Path of the intermediate DuckDB file. |

### Run modes (`flow_action_type`)

- **`mimic_to_database`** — full pipeline: load CSVs, build the CDM in DuckDB, export to the target database, then delete the DuckDB file.
- **`mimic_to_duckdb`** — build the CDM in DuckDB only. The DuckDB file is kept (with the final tables in its `cdm` schema) and nothing is exported. Useful for validating the conversion or exporting later.
- **`duckdb_to_database`** — export only: take an existing DuckDB file produced by a previous `mimic_to_duckdb` run and export its `cdm` schema to the target database. The file is not deleted.
### Database Connection (use_trex_connection)
For the full dataset, set `use_trex_connection = False` so the export uses the direct database connection — exporting through the trex passthrough takes considerably longer.

### Prefect variables (optional tuning)

These are read from [Prefect Variables](https://docs.prefect.io/latest/concepts/variables/), not from the flow variables above:

| Variable | Default | Description |
| --- | --- | --- |
| `duckdb_memory_limit` | *(unset — DuckDB default)* | DuckDB `memory_limit`, e.g. `15GB`. |
| `duckdb_threads` | `4` | DuckDB `threads` setting. |

In a d2e deployment these are set via `D2E_DUCKDB_MEMORY_LIMIT` and `D2E_DUCKDB_THREADS` in the `.env` file (see the system setup section above).

## Pipeline stages

The template contains seven python nodes executed in sequence:

| # | Node | What it does | Runs in |
| --- | --- | --- | --- |
| 1 | `load_mimic_data` | Loads the raw `hosp/` and `icu/` CSVs into `mimiciv_hosp` / `mimiciv_icu` schemas of the DuckDB file. | `mimic_to_database`, `mimic_to_duckdb` (and `load_mimic_vocab=True`) |
| 2 | `load_vocab` | Loads the Athena vocabulary CSVs into `mimic_staging` and generates the MIMIC custom vocabularies and concept mappings. | same as above |
| 3 | `staging_mimic` | Creates the `mimic_etl` schema, stages core/hosp/icu data, copies the vocabularies in, then drops the raw input schemas. | same as above |
| 4 | `etl_transformation` | Runs the 33 MIMIC-to-OMOP transformation scripts (lookups, clinical tables, era tables, metadata) inside `mimic_etl`. | `mimic_to_database`, `mimic_to_duckdb` |
| 5 | `cdm_table` | Creates the final `cdm` schema, unloads the transformed data into the OMOP CDM tables, then drops `mimic_etl`. | `mimic_to_database`, `mimic_to_duckdb` |
| 6 | `duckdb_database` | Exports the `cdm` schema to the target database (trex passthrough or legacy Postgres/HANA path). | `mimic_to_database`, `duckdb_to_database` |
| 7 | `cleanup` | Deletes the intermediate DuckDB file. | `mimic_to_database` only |

## Notes

- The ETL is based on the OHDSI [MIMIC-IV to OMOP conversion](https://github.com/OHDSI/MIMIC) SQL, adapted for DuckDB.
- Loading the full MIMIC-IV dataset is resource-intensive; set `duckdb_memory_limit`/`duckdb_threads` to match the execution runtime's resources if the defaults struggle.
- Each run with `load_mimic_vocab=True` rebuilds staging schemas from scratch (`DROP SCHEMA ... CASCADE`), so re-runs are idempotent with respect to the DuckDB file.
