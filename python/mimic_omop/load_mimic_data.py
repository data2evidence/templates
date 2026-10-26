SqlDir = 'flows/mimic_omop_conversion_plugin/external'
MIMICCreateSql = f'{SqlDir}/duckdb_create_mimic.sql'
mimic_dir = '/app/mimic_omop/mimic'

def initialize_id_sequence(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the sequence used to assign staging row ids."""
    conn.execute('CREATE SEQUENCE IF NOT EXISTS main.id_sequence;')

def create_table(conn: duckdb.DuckDBPyConnection, sql_file: str, schema_name: str = None) -> None:
    """Run a DDL file, substituting @schema_name when present."""
    with open(sql_file, 'r') as file:
        sql_qry = file.read()
        if "@schema_name" in sql_qry:
            sql_qry = sql_qry.replace('@schema_name', schema_name)
        conn.execute(sql_qry)

def make_table_name(file_path: str) -> tuple:
    """Map a MIMIC CSV path to ('mimiciv_<module>.<table>', '<module>')."""
    basename = os.path.basename(file_path)
    table_name = basename.split('.')[0]
    pathname = os.path.dirname(file_path)
    dirname = os.path.basename(pathname)
    return f"mimiciv_{dirname}.{table_name}", dirname

def config_duckdb(conn: duckdb.DuckDBPyConnection, memory_limit: str = "", threads: int = 4) -> None:
    """Apply DuckDB tuning; memory_limit is skipped when unset ("" is the d2e default)."""
    if memory_limit:
        conn.execute(f"SET memory_limit='{memory_limit}'")
    conn.execute(f"SET threads={threads}")
    conn.execute("SET preserve_insertion_order=false")

def exec(myinput):
    """Load MIMIC-IV hosp/icu CSVs into DuckDB."""
    logger = get_run_logger()
    if (flow_action_type in ['mimic_to_database','mimic_to_duckdb']) and load_mimic_vocab == "True":
        logger.info('Start loading mimic data')
        DUCKDB_MEMORY_LIMIT = Variable.get("duckdb_memory_limit", default="")
        DUCKDB_THREADS = int(Variable.get("duckdb_threads", default="4"))
        with duckdb.connect(duckdb_file_name) as conn:
            config_duckdb(conn, memory_limit=DUCKDB_MEMORY_LIMIT, threads=DUCKDB_THREADS)
            # initialize_id_sequence
            initialize_id_sequence(conn)
            # create tables
            create_table(conn, MIMICCreateSql)
            # copy csv tables from the hosp and icu subfolders only
            csv_files = glob.glob(os.path.join(mimic_dir, "hosp", "*.csv*")) + glob.glob(os.path.join(mimic_dir, "icu", "*.csv*"))
            for file_path in csv_files:
                table_name, dir_name = make_table_name(file_path)
                try:
                    sql_qry = f"""COPY {table_name} FROM '{file_path}' (ESCAPE '\"', HEADER);"""
                    conn.execute(sql_qry)
                    logger.info(f"Loading {table_name} done")
                except Exception as e:
                    logger.error(f"Error loading {file_path}: {str(e)}")
                    raise Exception()
            return "Load mimic data successful"
