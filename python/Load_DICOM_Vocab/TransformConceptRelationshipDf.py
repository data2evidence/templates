import pickle
import numpy as np

from pathlib import Path
from typing import Any, Dict

def exec(myinput: Dict[str, Any]) -> pd.DataFrame:
  """
  Combine multiple DICOM concept relationship dataframes into a single staging dataframe.
  
  This function processes three sources of DICOM data:
  1. Cs_values_maps_to_value (Code String values mapped to values)
  2. Cs_values_maps_to (Code String values mappings)
  3. Part3_to_part16_relationship_via_CID (from pickle file in storage)
  
  The function downloads a pickle file containing concept relationships, converts
  date columns to datetime format, assigns default date ranges to the other datasets,
  and combines all three into a single dataframe.
  
  Args:
      myinput: Dictionary containing workflow data with the following expected keys:
               - "UploadAttributes-CodeStringValues": Result containing cs_values_maps_to_value DataFrame
               - "UploadCs_values_maps_to": Result containing cs_values_maps_to DataFrame
               - "UploadAttributes-CID-ValueSets": Result containing node_id and filename for pickle file
  
  Returns:
      pd.DataFrame: Combined dataframe with all concept relationships, including properly
                    formatted valid_start_date and valid_end_date columns.
  """
  cs_values_maps_to_value_df: pd.DataFrame = myinput.get("UploadAttributes-CodeStringValues").result
  cs_values_maps_to_df: pd.DataFrame = myinput.get("UploadCs_values_maps_to").result
  
  node_id: str = myinput.get("UploadAttributes-CID-ValueSets").result.get("node_id")
  filename: str = myinput.get("UploadAttributes-CID-ValueSets").result.get("filename")
  
  # Download the pickle file from remote storage
  download_file_from_storage(node_id, filename)

  filepath: Path = Path(DOWNLOADS_DIR) / filename

  concept_relationship_staging: pd.DataFrame = pd.read_pickle(filepath)

  # Convert date columns from integer (YYYYMMDD) to datetime using vectorized operations
  concept_relationship_staging['valid_start_date'] = pd.to_datetime(
      concept_relationship_staging['valid_start_date'], 
      format='%Y%m%d', 
      errors='coerce'
  )

  concept_relationship_staging['valid_end_date'] = pd.to_datetime(
      concept_relationship_staging['valid_end_date'], 
      format='%Y%m%d', 
      errors='coerce'
  )

  # Assign constant dates to all rows (vectorized - no loops needed)
  cs_values_maps_to_value_df['valid_start_date'] = pd.to_datetime('1993-01-01')
  cs_values_maps_to_value_df['valid_end_date'] = pd.to_datetime('2099-12-31')

  cs_values_maps_to_df['valid_start_date'] = pd.to_datetime('1993-01-01')
  cs_values_maps_to_df['valid_end_date'] = pd.to_datetime('2099-12-31')

  # Combine the three dataframes into one
  combined_df: pd.DataFrame = pd.concat([concept_relationship_staging, cs_values_maps_to_value_df, cs_values_maps_to_df], ignore_index=True)

  return combined_df


def download_file_from_storage(node_id: str, filename: str) -> Path:
  """
  Download a file from Supabase storage to the downloads directory.
  
  Args:
    node_id: The storage node identifier where the file is located.
    filename: The name of the file to download.
    
  Returns:
    Path: The path to the downloaded file.
  """
  storage_api = SupabaseStorageAPI()
  return storage_api.download_file_to_path(node_id, filename, Path(DOWNLOADS_DIR))