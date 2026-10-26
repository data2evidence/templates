SqlDir = 'flows/mimic_omop_conversion_plugin/external'
CreateVocabTable = f'{SqlDir}/vocabulary-refresh/create_vocab_input_tables.sql'
CustomVocabDir = f'{SqlDir}/vocabulary-refresh/'
vocab_dir = '/app/mimic_omop/vocab'

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

def create_table(conn: duckdb.DuckDBPyConnection, sql_file: str, schema_name: str = None) -> None:
    """Run a DDL file, substituting @schema_name when present."""
    with open(sql_file, 'r') as file:
        sql_qry = file.read()
        if "@schema_name" in sql_qry:
            sql_qry = sql_qry.replace('@schema_name', schema_name)
        conn.execute(sql_qry)

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
    """Load OMOP vocabularies and build MIMIC custom vocabularies."""
    logger = get_run_logger()

    if (flow_action_type in ['mimic_to_database','mimic_to_duckdb']) and load_mimic_vocab == "True":
        logger.info('Start loading vocab')
        DUCKDB_MEMORY_LIMIT = Variable.get("duckdb_memory_limit", default="")
        DUCKDB_THREADS = int(Variable.get("duckdb_threads", default="4"))
        with duckdb.connect(duckdb_file_name) as conn:
            config_duckdb(conn, memory_limit=DUCKDB_MEMORY_LIMIT, threads=DUCKDB_THREADS)
            create_schema(conn, 'mimic_staging')
            create_table(conn, CreateVocabTable)
            # insert vocab tables; only files with a matching staging table (skips e.g. CONCEPT_CPT4, CONCEPT_RECOMMENDED)
            staging_tables = {x[0] for x in conn.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'mimic_staging'").fetchall()}
            csv_files = glob.glob(os.path.join(vocab_dir, "**/*.csv*"), recursive=True)
            for file in csv_files:
                csv_name = os.path.basename(file).split('.')[0].lower()
                table_name = '_'.join(['mimic_staging.tmp', csv_name])
                if f'tmp_{csv_name}' not in staging_tables:
                    logger.warning(f"Skipping {os.path.basename(file)}: no staging table {table_name}")
                    continue
                try:
                    query = f"""
                    TRUNCATE TABLE {table_name};
                    COPY {table_name} FROM '{file}' (DATEFORMAT '%Y%m%d', DELIMITER '\t', FORMAT CSV, HEADER, QUOTE '"',ESCAPE '\"');
                    """
                    conn.execute(query)
                    logger.info(f"Loading {table_name.replace('mimic_staging.tmp_', '')} done")
                except Exception as e:
                    logger.error(f"Error loading {file}: {str(e)}")
                    raise Exception()
            # generate_custom_vocab
            CustomVocabSqls = ['create_voc_from_tmp.sql',
                'custom_mapping_load.sql',
                'custom_vocabularies.sql',
                'vocabulary_cleanup.sql']
            CustomVocabLogs = ['Building vocabularies from temporary staging tables',
                'Loading custom concept mappings',
                'Generating custom vocabularies',
                'Cleaning up temporary vocabulary tables']
            try:
                execute_raw_sql_from_file(conn, CustomVocabDir, CustomVocabSqls, CustomVocabLogs)
            except Exception as e:
                logger.error(f"Error generating custom vocabularies: {str(e)}")
                raise Exception()
