def exec(myinput) -> dict[str, str]:
  """
  Execute database table truncation and schema mapping for CDM and vocabulary tables.
  
  This function creates a mapping of OMOP CDM (Common Data Model) and vocabulary tables
  to their respective database schemas, and optionally truncates these tables before
  returning the mapping.
  
  Args:
    myinput: Input parameter (currently unused, reserved for future functionality).
    
  Returns:
    dict[str, str]: A dictionary mapping table names to their schema names.
      Keys are table names (e.g., 'person', 'concept'), values are schema names.
      
  Raises:
    Exception: If any tables fail truncation and skip_if_error is False, or if
      truncation fails for any tables when skip_if_error is True (after attempting
      all tables).
      
  Note:
    - Requires global variables: cdm_schema, vocab_schema, database_code, truncate_tables, skip_truncate_if_error
    - truncate_tables flag controls whether tables are truncated (default: True)
    - skip_if_error flag controls error handling during truncation (default: False)
  """

  # From shared variables
  cdm_schema_var: str = cdm_schema 
  vocab_schema_var: str = vocab_schema
  database_code_var: str = database_code
  truncate_tables_var: bool = eval(truncate_tables) # If set to true, tables will be truncated
  skip_if_error: bool = eval(skip_truncate_if_error) # If set to true, tables that failed to be truncated will be ignored

  # List of OMOP CDM clinical data tables
  cdm_table_list: list[str] = [
    "person",
    "observation_period",
    "visit_occurrence",
    "visit_detail",
    "condition_occurrence",
    "drug_exposure",
    "procedure_occurrence",
    "device_exposure",
    "measurement",
    "observation",
    "death",
    "note",
    "note_nlp",
    "specimen",
    "fact_relationship",
    "location",
    "care_site",
    "provider",
    "payer_plan_period",
    "cost",
    "drug_era",
    "dose_era",
    "condition_era",
    "metadata",
    "cdm_source",
    "attribute_definition"
  ]

  # List of OMOP vocabulary tables
  vocab_table_list: list[str] = [
    "concept",
    "vocabulary",
    "domain",
    "concept_class",
    "concept_relationship",
    "relationship",
    "concept_synonym",
    "concept_ancestor",
    "source_to_concept_map",
    "drug_strength"
  ]

  # Mapping of table names to their respective schemas
  table_schema_map: dict[str, str] = {
    **{table: cdm_schema_var for table in cdm_table_list},
    **{table: vocab_schema_var for table in vocab_table_list},
  }

  if truncate_tables_var:
    truncate_success: dict[str, bool] = {}

    dbdao = DBDao(database_code=database_code_var)

    for table, schema in table_schema_map.items():
      try: 
        dbdao.truncate_table(schema, table)
      except Exception as e:
        truncate_success[table] = False
        if skip_if_error:
          continue
        else:
          raise
      else:
        truncate_success[table] = True

    false_count = sum(1 for v in truncate_success.values() if v is False)
    if false_count > 0:
      false_keys = [k for k, v in truncate_success.items() if v is False]
      raise Exception(f"Some tables failed truncation: {false_keys}")

    return table_schema_map
  return table_schema_map