from typing import Any, Dict, Optional
import pandas as pd


def exec(myinput: Dict[str, Any]) -> None:
  """
  Ingest CDM DataFrames into their corresponding database tables.
  
  This function takes transformed OMOP CDM DataFrames and inserts them into
  the appropriate database schemas using SQLAlchemy's to_sql method.
  
  Args:
    myinput: Dictionary containing workflow results with:
      - 'LoadAndTransformFiles': Contains 'result' with Dict[str, pd.DataFrame]
        mapping table names to their DataFrames
      - 'TruncateTables': Contains 'result' with Dict[str, str] mapping
        table names to their schema names
        
  Returns:
    None
    
  Note:
    - Requires global variables: cdm_schema, vocab_schema, database_code
    - Requires DBDao class to be available in scope
    - Uses 'append' mode for table insertion
    - Disposes database connection after completion
  """
  # Extract the dictionary of DataFrames from the LoadAndTransformFiles step
  df_list: Dict[str, pd.DataFrame] = myinput.get("LoadAndTransformFiles").result
  
  # Extract the table-to-schema mapping from the TruncateTables step
  table_schema_map: Dict[str, str] = myinput.get("TruncateTables").result

  # Get configuration from global variables
  database_code_var: str = database_code
  cdm_schema_var: str = cdm_schema 
  vocab_schema_var: str = vocab_schema
  

  # Initialize database connection (not using cache database)
  dbdao = DBDao(database_code=database_code_var)
  dbconn = dbdao.engine

  # Insert each DataFrame into its corresponding database table
  for table, df in df_list.items():
    # Insert DataFrame into the database table
    # - Uses the schema from table_schema_map
    # - Appends to existing data (table should already be truncated)
    # - Does not include DataFrame index as a column
    result: Optional[int] = df.to_sql(
      table, 
      dbconn, 
      schema=table_schema_map[table],
      if_exists='append',
      index=False
    )
  
  # Clean up database connection
  dbconn.dispose()