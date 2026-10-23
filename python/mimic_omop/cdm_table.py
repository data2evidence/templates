CdmDir = 'flows/mimic_omop_conversion_plugin/external/unload/'

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

def exec(myinput):
    """Build the final cdm schema and drop mimic_etl."""
    logger = get_run_logger()
    CdmSqls = ['OMOPCDM_duckdb_5.3_ddl_adapted.sql', 'unload_to_atlas_gen.sql']
    CdmLogs = ['Creating final OMOP CDM DuckDB schema', 'Unloading CDM data for ATLAS']
    if flow_action_type in ['mimic_to_database','mimic_to_duckdb']:
        logger.info("*** Creating final CDM tables and copy data into them ***")
        DUCKDB_MEMORY_LIMIT = Variable.get("duckdb_memory_limit", default="")
        DUCKDB_THREADS = int(Variable.get("duckdb_threads", default="4"))
        with duckdb.connect(duckdb_file_name) as conn:
            config_duckdb(conn, memory_limit=DUCKDB_MEMORY_LIMIT, threads=DUCKDB_THREADS)
            try:
                create_schema(conn, 'cdm')
                execute_raw_sql_from_file(conn, CdmDir, CdmSqls, CdmLogs)
            except Exception as e:
                logger.error(f"Error creating final cdm data: {str(e)}")
                raise Exception()
        # Cleanup schemas
        with duckdb.connect(duckdb_file_name) as conn:
            conn.execute("DROP SCHEMA mimic_etl CASCADE")
