def exec(myinput):
  config_file = myinput["config_file_processor"].result
  INPUT_DIR = myinput["data_file_processor"].result
  ANONYMIZER = myinput["R4 Fhir Anonymizer - Mac"].result # please replace this with the tool of your OS
  output_dir = input_dir.parent / "fhir_output"
  output_dir.mkdir(exist_ok=True)
  return {
    "ANONYMIZER" : ANONYMIZER,
    "CONFIG_FILE" : config_file,
    "INPUT_DIR" : str(INPUT_DIR),
    "OUTPUT_DIR" : str(output_dir)
  }