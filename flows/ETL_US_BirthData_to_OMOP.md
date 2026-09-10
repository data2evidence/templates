# US Birth Data to OMOP ETL Template

This runbook explains how to import and run
[`ETL_US_BirthData_to_OMOP.json`](./ETL_US_BirthData_to_OMOP.json).

## Data source

The input is the 2022 US birth public-use data from the CDC/NCHS
[Vital Statistics Online Data Portal](https://www.cdc.gov/nchs/data_access/vitalstatsonline.htm).

The template currently retains `nat2022` in several variable names and staging-file names. These are implementation names; when loading 2022 data, verify that the fixed-width positions used by the parser match the 2022 User Guide before running the complete dataset.

For a small manual test, this guide uses:

```text
nat2022_sample10_manual_test.txt
```

The mapping input is:

```text
Merged_US_Birth_Data.csv
```

## Prerequisites

- A D2E environment in which the flow service can run the imported template.
- An OMOP CDM 5.4 dataset created before running the ETL.
- The dataset ID returned by the Web API.
- The destination database code and schema name.
- The fixed-width birth-data file available on the host.
- The current `Merged_US_Birth_Data.csv` mapping file.

## Step 1: Mount the source-data directory

Mount the host directory containing the fixed-width source file into the flow container at `/app/data_load`:

```text
/path/to/store/nat2022_sample10_manual_test_txt:/app/data_load
```

The file should therefore be available inside the container as:

```text
/app/data_load/nat2022_sample10_manual_test.txt
```

## Step 2: Import and save the template

1. Import `ETL_US_BirthData_to_OMOP.json` in the ETL page within admin portal.
2. Save the imported flow immediately.


The required libraries are already declared in the JSON template and should still be visible after saving.


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

The ETL converts hyphens in the dataset ID to underscores when deriving the DuckDB/TREX cache catalog name. For the example above, the cache catalog is:

```text
ccedce26_6db6_4732_8948_c64ed0ba7cd2
```

## Step 4: Configure the source filename and destination

Set the source-file variable to the filename inside `/app/data_load`:

```text
nat2022_filename=nat2022_sample10_manual_test.txt
```

Set the correct destination database and schema in the flow configuration:

```text
destination_database_code=<database code>
destination_schema_name=<OMOP schema name>
```

The destination is resolved as:

```text
<cache catalog>.<destination_schema_name>.<table name>
```

The default chunk size is:

```text
chunk_size=200000
```

The small ten-record test does not require changing it.

## Step 5: Recreate the CSV mapping node

1. Delete the imported CSV node.
2. Create a new CSV node.
3. Upload or select the current `Merged_US_Birth_Data.csv`.
4. Ensure that the CSV node name is:

   ```text
   csv_node_0
   ```

5. Connect the new CSV node to the `transform_facts` node.

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

For `nat2022_sample10_manual_test.txt`, the expected PERSON count is:

```text
10 source records × 3 roles (Child, Mother, Father) = 30 PERSON rows
```

## Re-running the test

The ETL truncates its destination tables before loading them. After each successful run of the ten-record sample, the PERSON table should contain 30 rows, not an accumulated multiple such as 60 or 150.

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
- **Apparently stale row counts:** Use `COUNT(*)`, not `duckdb_tables().estimated_size`.
- **Repeated runs accumulate rows:** Verify that the flow can truncate the fully qualified catalog/schema tables and inspect the flow logs for truncation or load errors.
