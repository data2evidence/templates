CdmDir = 'flows/mimic_omop_conversion_plugin/external/unload/'
PostgresDDL = f'{CdmDir}export_postgresql_5.3_ddl_adapted.sql'
HANADDL = f'{CdmDir}export_hana_5.3_ddl_adapted.sql'

def create_table(conn: duckdb.DuckDBPyConnection, sql_file: str, schema_name: str = None) -> None:
    """Run a DDL file, substituting @schema_name when present."""
    with open(sql_file, 'r') as file:
        sql_qry = file.read()
        if "@schema_name" in sql_qry:
            sql_qry = sql_qry.replace('@schema_name', schema_name)
        conn.execute(sql_qry)

def export_data(duckdb_file_name: str, schema_name: str, to_dbdao, overwrite_schema: bool, chunk_size: int) -> None:
    """Legacy export: DuckDB ATTACH bulk insert for Postgres, SQLAlchemy chunked inserts for HANA."""
    logger = get_run_logger()
    db_credentials = to_dbdao.tenant_configs
    dialect = to_dbdao.dialect
    if to_dbdao.check_schema_exists(schema_name):
        if overwrite_schema:
            to_dbdao.drop_schema(schema_name, cascade=True)
        else:
            logger.error(f"Schema '{schema_name}' exists! To overwrite the existing schema, set 'Overwrite Schema' to True")
            raise ValueError()
    to_dbdao.create_schema(schema_name)
    match dialect:
        case SupportedDatabaseDialects.POSTGRES:
            attach_qry = f"""ATTACH 'host={db_credentials.host} port={db_credentials.port} dbname={db_credentials.databaseName}
            user={db_credentials.adminUser} password={db_credentials.adminPassword.get_secret_value()}'
            AS pg (TYPE POSTGRES, SCHEMA {schema_name});
            """
            # Attach Posgres Database
            with duckdb.connect(duckdb_file_name) as conn:
                conn.execute(attach_qry)
                # Creat schema and tables in postgres database
                create_table(conn, PostgresDDL, schema_name=schema_name)
                tables = conn.execute(f"SELECT table_name FROM duckdb_tables() WHERE (database_name = 'pg')").fetchall()
                tables = [x[0] for x in tables]
                for table in tables:
                    logger.info(f"Inserting into {schema_name}.{table}")
                    conn.execute(f"""
                    INSERT INTO pg.{schema_name}.{table}
                    SELECT * FROM cdm.{table};
                    """)
                conn.execute("DETACH pg;")

        case SupportedDatabaseDialects.HANA:
            create_sqls = open(HANADDL).read().replace('@schema_name', schema_name).split(';')[:-1]
            for create_sql in create_sqls:
                with to_dbdao.engine.connect() as hana_conn:
                    hana_conn.execute(text(create_sql))
                    hana_conn.commit()
            tables = to_dbdao.get_table_names(schema=schema_name)
            for table in tables:
                logger.info(f"Inserting into {schema_name}.{table}")
                tmp = 0
                for chunk, percent in read_table_chunks(duckdb_file_name, table, chunk_size=chunk_size):
                    if percent != tmp:
                        flag = True
                        tmp = percent
                    else:
                        flag = False
                    if not chunk.empty:
                        insert_to_hana_direct(to_dbdao, chunk, schema_name, table)
                    if flag:
                        logger.info(f"{int(percent)}% of table '{table}' is inserted")
                logger.info(f"100% of table '{table}' is inserted")

def read_table_chunks(duckdb_file_name: str, table: str, chunk_size: int):
    """Yield (DataFrame chunk, percent complete) for a cdm table."""
    with duckdb.connect(duckdb_file_name) as conn:
        count = conn.execute(f"SELECT COUNT(*) FROM cdm.{table}").fetchone()[0]
        for offset in range(0, count, chunk_size):
            chunk = conn.execute(f"""
                SELECT * FROM cdm.{table}
                LIMIT {chunk_size} OFFSET {offset}
            """).df()
            percent = (offset/count * 100)//10 * 10
            yield chunk, percent

def insert_to_hana_direct(to_dbdao, chunk, schema_name: str, table: str) -> None:
    """Insert one DataFrame chunk into a HANA table via SQLAlchemy."""
    with to_dbdao.engine.connect() as hana_conn:
        # Use Upper case for HANA
        chunk.columns = chunk.columns.str.upper()
        # Replace np.nan with None
        chunk.replace([np.nan], [None], inplace=True)
        columns = chunk.columns.tolist()
        columns_str = ', '.join(f'"{col}"' for col in columns)
        placeholders = ','.join(f':{col}' for col in columns)
        insert_stmt = f'INSERT INTO {schema_name}.{table} ({columns_str}) VALUES ({placeholders})'
        data = chunk.to_dict('records')
        hana_conn.execute(text(insert_stmt), data)
        hana_conn.commit()
    to_dbdao.engine.dispose()

def export_data_trex(duckdb_file_name: str, schema_name: str, to_dbdao, overwrite_schema: bool, chunk_size: int, is_hana: bool) -> None:
    """Export the cdm schema through the trex pgwire passthrough (Postgres and HANA targets)."""
    logger = get_run_logger()
    if to_dbdao.check_schema_exists(schema_name):
        if overwrite_schema:
            to_dbdao.drop_schema(schema_name, cascade=True)
        else:
            logger.error(f"Schema '{schema_name}' exists! To overwrite the existing schema, set 'Overwrite Schema' to True")
            raise ValueError()
    to_dbdao.create_schema(schema_name)
    database_ddl = HANADDL if is_hana else PostgresDDL
    # the postgres DDL targets the 'pg.' catalog alias of the legacy duckdb ATTACH
    # path; strip it since trex statements run directly on the target database
    create_sqls = open(database_ddl).read().replace('pg.@schema_name', '@schema_name').replace('@schema_name', schema_name).split(';')[:-1]
    for create_sql in create_sqls:
        to_dbdao.execute_sql(create_sql)
    with duckdb.connect(duckdb_file_name) as conn:
        tables = [x[0] for x in conn.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'cdm'").fetchall()]
    for table in tables:
        target_table = table.upper() if is_hana else table
        logger.info(f"Inserting into {schema_name}.{target_table}")
        tmp = 0
        for chunk, percent in read_table_chunks(duckdb_file_name, table, chunk_size=chunk_size):
            if percent != tmp:
                flag = True
                tmp = percent
            else:
                flag = False
            if not chunk.empty:
                # object dtype + where() nulls both NaN and NaT before pgwire insert
                chunk = chunk.astype(object).where(chunk.notna(), None)
                columns = [c.upper() for c in chunk.columns] if is_hana else list(chunk.columns)
                values = list(chunk.itertuples(index=False, name=None))
                to_dbdao.batch_insert_values(schema_name, target_table, columns, values)
            if flag:
                logger.info(f"{int(percent)}% of table '{table}' is inserted")
        logger.info(f"100% of table '{table}' is inserted")

def exec(myinput):
    """Export the cdm schema to the target database."""
    logger = get_run_logger()
    if flow_action_type in ['mimic_to_database','duckdb_to_database']:
        logger.info("<--------- Exporting CDM tables to Database --------->")
        if eval(use_trex_connection):
            # trex pgwire passthrough serves both Postgres and HANA targets; the dao
            # reports dialect 'trex', so probe the real dialect separately
            is_hana = DBDao(dialect=None, database_code=database_code).dialect == SupportedDatabaseDialects.HANA
            to_dbdao = DBDao(dialect=SupportedDatabaseDialects.TREX, database_code=database_code)
            to_dbdao.is_hana = is_hana
            export_data_trex(duckdb_file_name=duckdb_file_name, schema_name=schema_name, to_dbdao=to_dbdao, overwrite_schema=eval(overwrite_schema), chunk_size=int(chunk_size), is_hana=is_hana)
        else:
            # admin-portal ETL runs have no dataset id, so no cache_id: the dataset
            # PA/CDM config session variables only apply to registered datasets
            to_dbdao = DBDao(database_code=database_code)
            export_data(duckdb_file_name=duckdb_file_name, schema_name=schema_name, to_dbdao=to_dbdao, overwrite_schema=eval(overwrite_schema), chunk_size=int(chunk_size))
