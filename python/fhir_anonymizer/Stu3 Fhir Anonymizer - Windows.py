from io import BytesIO

def exec(myinput):
  """
    Downloads and extracts the latest Microsoft FHIR Anonymizer CommandLineTool.zip
    into /app/flows/data_transformation/fhir-anonymizer, returning the DLL path.
  """
  TARGET_DIR = Path("/app/downloads/fhir-anonymizer")
  TARGET_DIR.mkdir(parents=True, exist_ok=True)

  print("Fetching latest FHIR Anonymizer release info...")
  #always get the latest version of fhir anonymizer
  release_api = "https://api.github.com/repos/microsoft/Tools-for-Health-Data-Anonymization/releases/latest"
  response = requests.get(release_api)
  response.raise_for_status()
  release_data = response.json()

  # Find the R4 CommandLineTool asset
  assets = release_data.get("assets", [])
  asset = next(
    (a for a in assets if a["name"] == "Microsoft.Health.Fhir.Anonymizer.Stu3.CommandLineTool.zip"),
    None
  )

  if not asset:
    raise RuntimeError("Could not find Microsoft.Health.Fhir.Anonymizer.Stu3.CommandLineTool.zip in latest release")

  asset_url = asset["url"]
  print(f"Downloading asset from GitHub API asset URL: {asset_url}")

  # The asset API URL requires this header to get the binary content
  headers = {"Accept": "application/octet-stream"}
  download = requests.get(asset_url, headers=headers, stream=True)
  download.raise_for_status()

  # Extract directly from memory
  with zipfile.ZipFile(BytesIO(download.content)) as zip_ref:
    zip_ref.extractall(TARGET_DIR)

  dll_path = TARGET_DIR / "Microsoft.Health.Fhir.Anonymizer.Stu3.CommandLineTool.exe"
  print(f"Extracted FHIR Anonymizer to {TARGET_DIR}")
  return str(dll_path)

  