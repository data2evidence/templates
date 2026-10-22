StagDir = 'flows/mimic_omop_conversion_plugin/external/staging'

def execute_raw_sql_from_file(conn: duckdb.DuckDBPyConnection, dir_root: str, sql_files: list, log_messages: list) -> None:
    """Execute SQL files from dir_root in order, logging one message per file."""
    logger = get_run_logger()
    try:
        for (sql_file, log_message) in zip(sql_files, log_messages, strict=True):
            logger.info(log_message)
            with open(os.path.join(dir_root, sql_file), 'r') as file:
                query = file.read()
                conn.execute(query)
    except Exception as e:
        logger.error(f"Error executing {sql_file}: {str(e)}")
        raise

def create_schema(conn: duckdb.DuckDBPyConnection, schema_name: str) -> None:
    """Drop the schema if it exists and recreate it empty."""
    conn.execute(f"""
    DROP SCHEMA IF EXISTS {schema_name} CASCADE ;
    CREATE SCHEMA {schema_name} ;
    """)

def config_duckdb(conn: duckdb.DuckDBPyConnection, memory_limit: str = "", threads: int = 4) -> None:
    """Apply DuckDB tuning; memory_limit is skipped when unset ("" is the d2e default)."""
    if memory_limit:
        conn.execute(f"SET memory_limit='{memory_limit}'")
    conn.execute(f"SET threads={threads}")
    conn.execute("SET preserve_insertion_order=false")

def staging_mimic_data(conn: duckdb.DuckDBPyConnection, StagDir: str, StagSql: list, StagLogs: list) -> None:
    """Create the mimic_etl schema and run the staging SQL scripts."""
    create_schema(conn, 'mimic_etl')
    execute_raw_sql_from_file(conn, StagDir, StagSql, StagLogs)

def exec(myinput):
    """Stage MIMIC data into mimic_etl and drop the raw schemas."""

    StagSql = ['etl_OMOPCDM_postgresql_5.3_ddl_adapted_no_vocab.sql',
                'st_core.sql',
                'st_hosp.sql',
                'st_icu.sql',
                'voc_copy_to_target_dataset.sql']
    StagLogs = ['Creating OMOP CDM staging schema (DDL, no vocab)',
                'Staging MIMIC core tables',
                'Staging MIMIC hospital tables',
                'Staging MIMIC ICU tables',
                'Copying vocabularies to target dataset']

    if flow_action_type in ['mimic_to_database','mimic_to_duckdb'] and load_mimic_vocab == "True":
        DUCKDB_MEMORY_LIMIT = Variable.get("duckdb_memory_limit", default="")
        DUCKDB_THREADS = int(Variable.get("duckdb_threads", default="4"))
        with duckdb.connect(duckdb_file_name) as conn:
            config_duckdb(conn, memory_limit=DUCKDB_MEMORY_LIMIT, threads=DUCKDB_THREADS)
            staging_mimic_data(conn, StagDir, StagSql, StagLogs)
            conn.execute("DROP SCHEMA mimiciv_hosp CASCADE")
            conn.execute("DROP SCHEMA mimiciv_icu CASCADE")
            conn.execute("DROP SCHEMA mimic_staging CASCADE")
