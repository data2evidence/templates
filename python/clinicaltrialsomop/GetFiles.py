from pathlib import Path

def exec(myinput):
  csv_folder = Path(source_csv_folder)

  # Get only CSV files in the folder
  csv_files = list(csv_folder.glob("*.csv"))
  
  absolute_paths = [csv_file.absolute() for csv_file in sorted(csv_files)]

  return absolute_paths