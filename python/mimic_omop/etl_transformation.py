ETLDir = 'flows/mimic_omop_conversion_plugin/external/etl'

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

def config_duckdb(conn: duckdb.DuckDBPyConnection, memory_limit: str = "", threads: int = 4) -> None:
    """Apply DuckDB tuning; memory_limit is skipped when unset ("" is the d2e default)."""
    if memory_limit:
        conn.execute(f"SET memory_limit='{memory_limit}'")
    conn.execute(f"SET threads={threads}")
    conn.execute("SET preserve_insertion_order=false")

def exec(myinput):
    """Run the OMOP CDM ETL transformation scripts."""
    logger = get_run_logger()

    ETLSqls = ['cdm_location.sql',
                'cdm_care_site.sql',
                'cdm_person.sql',
                'cdm_death.sql',
                'lk_vis_part_1.sql',
                'lk_meas_unit.sql',
                # ULLIF(regexp_extract(),'') replace postgres(regexp_match)
                'lk_meas_chartevents.sql',
                'lk_meas_labevents.sql',
                'lk_meas_specimen.sql',
                'lk_meas_outputevents.sql',
                'lk_vis_part_2.sql',
                'cdm_visit_occurrence.sql',
                'cdm_visit_detail.sql',
                'lk_cond_diagnoses.sql',
                'lk_procedure.sql',
                'lk_observation.sql',
                'cdm_condition_occurrence.sql',
                'cdm_procedure_occurrence.sql',
                'cdm_specimen.sql',
                'cdm_measurement.sql',
                'lk_drug.sql',
                'cdm_drug_exposure.sql',
                'cdm_device_exposure.sql',
                'cdm_observation.sql',
                'cdm_observation_period.sql',
                'cdm_finalize_person.sql',
                'cdm_fact_relationship.sql',
                'cdm_condition_era.sql',
                'cdm_drug_era.sql',
                'cdm_dose_era.sql',
                'ext_d_itemid_to_concept.sql',
                'cdm_cdm_source.sql',
                'extra_cdm_tables.sql']
    ETLLogs = ['Populating CDM location table',
                'Populating CDM care site table',
                'Populating CDM person table',
                'Populating CDM death table',
                'Building visit lookup (part 1: admissions and transfers)',
                'Building measurement unit lookup',
                'Building chart events measurement lookup',
                'Building lab events measurement lookup',
                'Building specimen measurement lookup',
                'Building output events measurement lookup',
                'Building visit lookup (part 2: visit grouping)',
                'Populating CDM visit occurrence table',
                'Populating CDM visit detail table',
                'Building condition diagnosis lookup',
                'Building procedure lookup',
                'Building observation lookup',
                'Populating CDM condition occurrence table',
                'Populating CDM procedure occurrence table',
                'Populating CDM specimen table',
                'Populating CDM measurement table',
                'Building drug lookup',
                'Populating CDM drug exposure table',
                'Populating CDM device exposure table',
                'Populating CDM observation table',
                'Populating CDM observation period table',
                'Finalizing CDM person records',
                'Populating CDM fact relationship table',
                'Populating CDM condition era table',
                'Populating CDM drug era table',
                'Populating CDM dose era table',
                'Mapping item IDs to OMOP concepts',
                'Populating CDM source metadata table',
                'Populating extra CDM tables']

    if flow_action_type in ['mimic_to_database','mimic_to_duckdb']:
        DUCKDB_MEMORY_LIMIT = Variable.get("duckdb_memory_limit", default="")
        DUCKDB_THREADS = int(Variable.get("duckdb_threads", default="4"))
        with duckdb.connect(duckdb_file_name) as conn:
            config_duckdb(conn, memory_limit=DUCKDB_MEMORY_LIMIT, threads=DUCKDB_THREADS)
            logger.info("*** Doing ETL transformations ***")
            try:
                execute_raw_sql_from_file(conn, ETLDir, ETLSqls, ETLLogs)
            except Exception as e:
                logger.error(f"Error transforming mimic: {str(e)}")
                raise Exception()
