# US Birth Data to OMOP ETL Template

This runbook explains how to import and run
[`ETL_US_BirthData_to_OMOP.json`](./ETL_US_BirthData_to_OMOP.json).

## Data source

The input is the 2022 US birth public-use data from the CDC/NCHS
[Vital Statistics Online Data Portal](https://www.cdc.gov/nchs/data_access/vitalstatsonline.htm).

The template currently retains `nat2022` in several variable names and staging-file names. These are implementation names; when loading 2022 data, verify that the fixed-width positions used by the parser match the 2022 User Guide before running the complete dataset.

This guide uses:

```text
Unziped_2022_US_birth_data.txt
```

The mapping input is:

```text
Merged_US_Birth_Data.csv # will be uploaded locally
```

## Prerequisites

- A running D2E environment.
- An OMOP CDM 5.4 dataset created before running the ETL.
- The dataset ID copied from the Datasets page.
- The destination database code and schema name.
- The fixed-width birth-data file available on the host.
- The `Merged_US_Birth_Data.csv` mapping file.

## Step 1: Mount the source-data directory

Mount the host directory containing the fixed-width source file into the flow container at `/app/data_load`:

- Open a terminal in the d2e directory.
- Run the following commands to define directories:

```sh
export BIRTH_DATA_DIR="/absolute/path/to/birth_data"
yq -i '.services.alp-dataflow-gen-worker.volumes = ((.services.alp-dataflow-gen-worker.volumes // []) + [strenv(BIRTH_DATA_DIR) + ":/app/data_load"] | unique)' docker-compose.yml
```

Restart D2E to apply the updated container mount:

```sh
d2e stop
d2e start
```

After the restart, verify that the worker can see the mounted files:

```sh
docker exec alp-dataflow-gen-worker ls -l /app/data_load
```

## Step 2: Import and save the template

1. Import `ETL_US_BirthData_to_OMOP.json` in the ETL page within admin portal.
2. Save the imported flow immediately.


## Step 3: Create the dataset and set `dataset_id`

Create the destination OMOP CDM 5.4 dataset before running the flow. Creating it through the Dataset page.

Copy the dataset ID returned and set the flow variable:

```text
dataset_id=<dataset UUID>
```

Example:

```text
dataset_id=ccedce26-6db6-4732-8948-c64ed0ba7cd2
```


## Step 4: Configure the source filename and destination

- Set the source-file variable "nat2022_filename" to the filename inside `/app/data_load`:
- Set the correct destination database and schema in the flow configuration:

```text
nat2022_filename=${filename_of_Unziped_2022_US_birth_data.txt}
destination_database_code=<database code>
destination_schema_name=<OMOP schema name>
```
- The default chunk size is:

```text
chunk_size=200000
```

## Step 5: Upload local mapping table via CSV node

- In CSV node, upload the mapping table using exact same name as `Merged_US_Birth_Data.csv`.
- Ensure that the CSV node name is `csv_node_0`

*The Python transform expects its mapping DataFrame from `csv_node_0`. A differently named or disconnected node will cause the flow to fail.

## Step 6: Run the flow

Run the complete flow. Its main stages are:

1. Parse the fixed-width file and create a staging CSV.
2. Load the mapping from `csv_node_0`.
3. Transform the birth records into OMOP CDM 5.4 rows.
4. Truncate and populate the destination OMOP tables.
5. Verify the inserted row counts.
6. Remove temporary staging files.
7. Populate the static PROVIDER dimension.

The ETL writes the following tables:

- `person`
- `visit_occurrence`
- `observation`
- `measurement`
- `condition_occurrence`
- `procedure_occurrence`
- `payer_plan_period`
- `provider`

## Step 7: Verify the cache tables

First confirm that the tables exist in the expected catalog and schema:

- cache_catalog: can be found in trex 

```sql
SELECT
    table_catalog,
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_catalog = '<cache_catalog>'
  AND table_schema = '<schema_name>'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

Then generate exact `COUNT(*)` queries for all tables in the destination schema:

```sql
SELECT string_agg(
    'SELECT '''
    || replace(table_name, '''', '''''')
    || ''' AS table_name, COUNT(*) AS row_count FROM "'
    || replace(table_catalog, '"', '""')
    || '"."'
    || replace(table_schema, '"', '""')
    || '"."'
    || replace(table_name, '"', '""')
    || '"',
    ' UNION ALL '
) AS count_sql
FROM information_schema.tables
WHERE table_catalog = '<cache_catalog>'
  AND table_schema = '<schema_name>'
  AND table_type = 'BASE TABLE';
```

Copy and execute the generated SQL. Add this to the end if desired:

```sql
ORDER BY row_count DESC;
```

## Re-running the test

The ETL truncates its destination tables before loading them. For example, after each successful run of the ten-record sample, the PERSON table should contain 30 rows, not an accumulated multiple such as 60 or 150.

Verify this with an exact count:

```sql
SELECT COUNT(*) AS row_count
FROM "<cache_catalog>"."<schema_name>"."person";
```

If this returns 30 while `duckdb_tables().estimated_size` shows an older value, trust `COUNT(*)`.

## Common failures

- **Import libraries disappear:** Save the flow immediately after importing the JSON.
- **Mapping input is missing:** Recreate the CSV node, name it `csv_node_0`, load `Merged_US_Birth_Data.csv`, and connect it to `transform_facts`.
- **Source file is not found:** Confirm the host-directory mount and `nat2022_filename` value.
- **Wrong cache receives data:** Confirm that `dataset_id` is the ID returned for the intended Web API dataset.
- **Wrong destination:** Confirm both `destination_database_code` and `destination_schema_name`.
