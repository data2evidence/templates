import pandas as pd
import numpy as np

from typing import Any, Dict
from zipfile import ZipFile
from pathlib import Path

# Directory where downloaded and extracted files are stored
DOWNLOADS_DIR = Path("/app/downloads")


def exec(myinput: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
  """
  Main execution function to download, unzip, and load CDM data from uploaded files.
  
  This function retrieves the uploaded CDM data file from storage, extracts it,
  and transforms all CSV files into pandas DataFrames.
  
  Args:
    myinput: Dictionary containing workflow input data with 'UploadCDMData' key
      that includes 'node_id' and 'filename' in its result.
      
  Returns:
    Dict[str, pd.DataFrame]: Dictionary mapping table names (lowercase) to their
      corresponding transformed DataFrames.
      
  Note:
    - Requires global variables: encoding, delimiter
    - Downloads file to DOWNLOADS_DIR
    - Extracts zip contents to DOWNLOADS_DIR
  """
  # Extract node_id and filename from workflow input
  node_id: str = myinput.get("UploadCDMData").result.get("node_id")
  filename: str = myinput.get("UploadCDMData").result.get("filename")

  # Download the file from remote storage
  download_file_from_storage(node_id, filename)
  
  # Extract the zip file contents
  unzip_file(filename)

  # Get encoding and delimiter from global configuration
  encoding_var: str = encoding
  delimiter_var: str = delimiter

  # Determine the unzipped folder path (same name as zip file without extension)
  unzipped_folder: Path = DOWNLOADS_DIR / Path(filename).stem
  
  # Load and transform all CSV files in the folder
  return load_and_transform(unzipped_folder, encoding_var, delimiter_var)


def load_and_transform(folder: Path, encoding: str = "utf-8", delimiter: str = ",") -> Dict[str, pd.DataFrame]:
  """
  Read and transform all CSV files in a folder into DataFrames.
  
  This function iterates through all CSV files in the specified folder, reads each
  into a pandas DataFrame, applies transformations, and returns a dictionary mapping
  table names to their DataFrames.
  
  Args:
    folder: Path to the directory containing CSV files.
    encoding: Character encoding for reading CSV files (default: "utf-8").
    delimiter: Field delimiter for CSV files (default: ",").
    
  Returns:
    Dict[str, pd.DataFrame]: Dictionary where keys are lowercase table names
      (derived from CSV filenames) and values are transformed DataFrames.
  """
  excluded_tables = exclude_tables.split(",")

  return {
    file_path.stem.lower(): transform_data(
      file_path.stem.lower(),
      pd.read_csv(file_path, encoding=encoding, delimiter=delimiter),
    )
    for file_path in sorted(folder.iterdir())
    if file_path.is_file() and file_path.suffix.lower() == ".csv" and file_path.stem.lower() not in excluded_tables
  }



def transform_data(table: str, df: pd.DataFrame) -> pd.DataFrame:
  """
  Apply table-specific transformations and standardize DataFrame format.
  
  This function applies data cleaning and standardization to OMOP CDM tables,
  including filling null vocabulary IDs, removing empty columns, and normalizing
  column names to lowercase.
  
  Args:
    table: The name of the table (lowercase) being transformed.
    df: The DataFrame to transform.
    
  Returns:
    pd.DataFrame: The transformed DataFrame with:
      - Filled VOCABULARY_ID for vocabulary and concept tables
      - "nan" strings replaced with np.nan
      - Empty columns removed
      - Column names converted to lowercase
  """
  # Fill missing VOCABULARY_ID for vocabulary and concept tables
  if table in ('vocabulary', 'concept'):
    df['VOCABULARY_ID'] = df['VOCABULARY_ID'].fillna('None')
  
  # Replace string "nan" with actual NaN values
  df = df.replace("nan", np.nan)
  
  # Remove columns that are entirely empty
  df.dropna(axis=1, how='all', inplace=True)
  
  # Standardize column names to lowercase
  df.columns = df.columns.str.lower()
  
  return df


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
  return storage_api.download_file_to_path(node_id, filename, DOWNLOADS_DIR)


def unzip_file(zip_name: str) -> None:
  """
  Extract contents of a zip file to the downloads directory.
  
  Args:
    zip_name: The name of the zip file to extract (must exist in DOWNLOADS_DIR).
    
  Raises:
    FileNotFoundError: If the specified zip file does not exist in DOWNLOADS_DIR.
  """
  # Construct full path to the zip file
  zip_path: Path = DOWNLOADS_DIR / zip_name

  # Verify the zip file exists
  if not zip_path.is_file():
    raise FileNotFoundError(f"'{zip_name}' not found in '{DOWNLOADS_DIR}'")

  # Extract all contents to the downloads directory
  with ZipFile(zip_path, "r") as zf:
    zf.extractall(DOWNLOADS_DIR)