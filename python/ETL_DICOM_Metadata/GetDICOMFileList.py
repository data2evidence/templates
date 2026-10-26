from pathlib import Path
from typing import Any, List

def exec(myinput: Any) -> List[str]:
  """
  Recursively search for all DICOM files in the specified directory.
  
  This function scans the DICOM images directory and returns a list of absolute
  paths to all files with .dcm or .DCM extensions.
  
  Args:
      myinput: Any.
  
  Returns:
      List[str]: List of absolute file paths to all DICOM files found in the directory.
  """
  # This is the file path of the dicom files mounted to the flow run container
  dicom_file_abs_path: str = "/app/externalfiles/dicom-images-test"
  root_dir: Path = Path(dicom_file_abs_path)
  dcm_files: List[str] = [str(path) for path in root_dir.rglob('*.dcm')] + [str(path) for path in root_dir.rglob('*.DCM')]
  print(f"Found {len(dcm_files)} DICOM files for processing!")

  return dcm_files