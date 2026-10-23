def exec(myinput):
    """Delete the intermediate DuckDB file."""
    logger = get_run_logger()
    if flow_action_type in ['mimic_to_database']:
        logger.info("<--------- Cleaning up DuckDB file --------->")
        os.remove(duckdb_file_name)
        logger.info(f"File '{duckdb_file_name}' deleted successfully.")
        logger.info("<--------- Workflow complete --------->")
