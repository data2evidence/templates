from typing import Dict, Any

def exec(myinput: Any) -> Dict[str, int]:
  """
  Retrieve the next available record IDs for multiple database tables.
  
  This function initializes a database DAO connection and fetches the next
  sequential record IDs for various OMOP CDM and Medical Imaging schema tables.
  These IDs are used to ensure unique identifiers when inserting new records.
  
  Returns:
      Dict[str, int]: A dictionary mapping table names to their next available record IDs.
                     Keys include:
                     - image_occurrence: Next ID for image_occurrence table
                     - procedure_occurrence: Next ID for procedure_occurrence table
                     - visit_occurrence: Next ID for visit_occurrence table
                     - measurement: Next ID for measurement table
                     - image_feature: Next ID for image_feature table
                     - dicom_file_metadata: Next ID for dicom_file_metadata table
  """
  dbdao: DBDao = DBDao(database_code=database_code)
  
  return {
    "image_occurrence": dbdao.get_next_record_id(mi_schema, "image_occurrence", "image_occurrence_id"),
    "procedure_occurrence": dbdao.get_next_record_id(cdm_schema, "procedure_occurrence", "procedure_occurrence_id"),
    "visit_occurrence": dbdao.get_next_record_id(cdm_schema, "visit_occurrence", "visit_occurrence_id"),
    "measurement": dbdao.get_next_record_id(cdm_schema, "measurement", "measurement_id"),
    "image_feature": dbdao.get_next_record_id(mi_schema, "image_feature", "image_feature_id"),
    "dicom_file_metadata": dbdao.get_next_record_id(mi_schema, "dicom_file_metadata", "metadata_id")
  }