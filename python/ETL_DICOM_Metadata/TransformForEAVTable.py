import numpy as np
from typing import Any, Dict, List
from datetime import datetime

def exec(myinput: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """
    Transform DICOM metadata into OMOP CDM tables for imaging data.
    
    This function processes mapped DICOM concepts and creates records for three OMOP CDM tables:
    - image_occurrence: Contains image-specific metadata (study/series UIDs, modality, anatomic site)
    - procedure_occurrence: Records imaging procedures performed
    - visit_occurrence: Records patient visits when imaging was performed
    
    The function performs the following operations:
    1. Extracts key DICOM tags (Study Date, Patient ID, Modality, Body Part Examined)
    2. Pivots data to create one record per image series
    3. Maps Patient IDs to person_ids from the person table
    4. Maps DICOM codes to concept IDs (modality and anatomic site)
    5. Generates sequential IDs for each table
    6. Creates properly formatted records for each OMOP table
    
    Args:
        myinput: Dictionary containing workflow data with the following expected keys:
                 - "MappedConceptsDf": Result containing mapped DICOM concepts DataFrame
                 - "ConceptIDTagsDf": Result containing concept ID mappings DataFrame
                 - "GetNextRecordIDs": Result with next available IDs for each table
    
    Returns:
        Dict[str, pd.DataFrame]: Dictionary containing four DataFrames:
                                - "image_occurrence": Image occurrence table records
                                - "procedure_occurrence": Procedure occurrence table records
                                - "visit_occurrence": Visit occurrence table records
                                - "transformed_df": Full transformed DataFrame with all fields
    
    Note:
        - Uses person_id=0 for unmatched patients
        - Uses concept_id=0 for unmapped codes
        - Defaults to visit_type_concept_id=32817 (EHR) and visit_concept_id=9202 (Outpatient)
        - Missing study dates default to 1993-01-01 (earliest vocabulary valid date)
    """
    mapped_concepts_df: pd.DataFrame = myinput["MappedConceptsDf"].result
    concept_df: pd.DataFrame = myinput["ConceptIDTagsDf"].result

    next_po_id: int = myinput["GetNextRecordIDs"].result.get("procedure_occurrence")
    next_vo_id: int = myinput["GetNextRecordIDs"].result.get("visit_occurrence")
    next_io_id: int = myinput["GetNextRecordIDs"].result.get("image_occurrence")
    
    # Tags used for image_occurrence, procedure_occurrence, visit_occurrence
    # 00080020: Study Date, 00100020: Patient ID, 00080060: Modality
    # 00180015: Body Part Examined (Optional in Image Occurrence table)
    tags_for_columns: List[str] = ["00080020", "00100020", "00080060", "00180015"]

    # Select only rows with the above tags
    df_subset: pd.DataFrame = mapped_concepts_df[mapped_concepts_df["tag"].isin(tags_for_columns)][["image_study_uid",
                                                                                      "image_series_uid",
                                                                                      "tag",
                                                                                      "value"]]
    
    # Pivot to wide format and select only keep unique series uids
    df_subset_pivoted: pd.DataFrame = df_subset.pivot_table(
        index=["image_study_uid", "image_series_uid"], columns="tag", values="value", aggfunc="first")
    df_subset_pivoted.reset_index(inplace=True)
    df_subset_pivoted = df_subset_pivoted.drop_duplicates(
        subset=["image_study_uid", "image_series_uid"])

    # Create "00180015" BodyPartExamined column if it doesn't exist and fill with NaN
    if '00180015' not in df_subset_pivoted.columns:
        df_subset_pivoted['00180015'] = np.nan
        df_subset_pivoted['00180015'] = df_subset_pivoted['00180015'].astype('object')

    # Create "00080020" StudyDate column if it doesn't exist and fill with 19930101 i.e. earliest vocab valid date
    if '00080020' not in df_subset_pivoted.columns:
        df_subset_pivoted['00080020'] = "19930101"


    # Map Person ID
    person_id_col: str = "person_id"
    patient_id_col: str = "person_source_value"

    dbdao: DBDao = DBDao(database_code=database_code)

    with dbdao.ibis_connect() as conn:
        mapping_table = conn.table("person",
                                   database=person_mapping_schema)

        mapping_df = mapping_table[[person_id_col, patient_id_col]].execute()

    transformed_df: pd.DataFrame = df_subset_pivoted.merge(mapping_df[[person_id_col, patient_id_col]],
                                                  how="left", left_on="00100020", right_on=patient_id_col)
    transformed_df.rename(
        columns={person_id_col: 'person_id'}, inplace=True)

    # Use person_id = 0 for unmatched patient_ids
    transformed_df['person_id'] = transformed_df['person_id'].fillna(
        0)
    transformed_df['person_id'] = transformed_df['person_id'].astype(
        'Int64')

    # Get concept id for modality and body part
    concept_df['concept_code'] = concept_df['concept_code'].astype(str)
    concept_df['concept_code'] = concept_df['concept_code'].str.upper()

    # Todo: Update with standard concept ids
    # Get concept id for BodyPartExamined -> anatomic_site_concept_id
    print("Mapping BodyPartExamined tag to concept_id..")
    transformed_df = transformed_df.merge(concept_df[["concept_id", "concept_code"]],
                                                    how="left", left_on="00180015", right_on="concept_code")
    transformed_df.rename(
        columns={"concept_id": "anatomic_site_concept_id"}, inplace=True)

    # Use anatomic_site_concept_id = 0 for unmatched patient_ids
    transformed_df['anatomic_site_concept_id'] = transformed_df['anatomic_site_concept_id'].fillna(
        0)
    transformed_df['anatomic_site_concept_id'] = transformed_df['anatomic_site_concept_id'].astype(
        'Int64')

    # Todo: Update with standard concept id
    # Get concept id for Modality -> modality_concept_id
    print("Mapping Modality tag to concept_id..")
    transformed_df = transformed_df.merge(concept_df[["concept_id", "concept_code"]],
                                                    how="left", left_on="00080060", right_on="concept_code")
    transformed_df.rename(
        columns={"concept_id": "modality_concept_id"}, inplace=True)

    # Use modality_concept_id = 0 for unmatched patient_ids
    transformed_df['modality_concept_id'] = transformed_df['modality_concept_id'].fillna(
        0)
    transformed_df['modality_concept_id'] = transformed_df['modality_concept_id'].astype(
        'Int64')

    # Todo: Update wadors_uri, local_path, visit_type_concept_id & visit_concept_id
    transformed_df['image_occurrence_date'] = pd.to_datetime(
        transformed_df['00080020'])
    transformed_df['image_occurrence_date'] = transformed_df['image_occurrence_date'].fillna(
        pd.to_datetime("1993-01-01"))

    transformed_df['visit_type_concept_id'] = 32817  # EHR
    transformed_df['visit_concept_id'] = 9202  # Outpatient visit

    transformed_df['image_occurrence_id'] = pd.Series(range(next_io_id,
                                                                 next_io_id + len(transformed_df)))
    transformed_df['procedure_occurrence_id'] = pd.Series(range(next_po_id,
                                                                     next_po_id + len(transformed_df)))
    transformed_df['visit_occurrence_id'] = pd.Series(range(next_vo_id,
                                                                 next_vo_id + len(transformed_df)))

    print("Successfully created records for image occurrence, procedure occurrence and visit occurrence tables!")
        
    # return transformed_df

    return {
        "image_occurrence": image_occurrence(transformed_df),
        "procedure_occurrence": procedure_occurrence(transformed_df),
        "visit_occurrence": visit_occurrence(transformed_df),
        "transformed_df": transformed_df
    }


def image_occurrence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create image_occurrence table records from transformed DICOM data.
    
    Extracts and returns only the columns required for the OMOP CDM image_occurrence table,
    which contains metadata about medical imaging studies.
    
    Args:
        df: Transformed DataFrame containing all processed DICOM metadata and IDs.
    
    Returns:
        pd.DataFrame: DataFrame with image_occurrence table columns:
                     - image_occurrence_id: Unique identifier for the image
                     - person_id: Foreign key to person table
                     - procedure_occurrence_id: Foreign key linking to the procedure
                     - visit_occurrence_id: Foreign key linking to the visit
                     - anatomic_site_concept_id: Concept for body part examined
                     - image_occurrence_date: Date the image was acquired
                     - image_study_uid: DICOM Study Instance UID
                     - image_series_uid: DICOM Series Instance UID
                     - modality_concept_id: Concept for imaging modality (CT, MRI, etc.)
    """
    image_occurrence_columns: List[str] = [
        "image_occurrence_id",
        "person_id",
        "procedure_occurrence_id",
        "visit_occurrence_id",
        "anatomic_site_concept_id",
        "image_occurrence_date",
        "image_study_uid",
        "image_series_uid",
        "modality_concept_id"
    ]
    return df[image_occurrence_columns]


def procedure_occurrence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create procedure_occurrence table records from transformed DICOM data.
    
    Extracts relevant columns and renames them to match the OMOP CDM procedure_occurrence
    table schema. Each imaging study is treated as a procedure.
    
    Args:
        df: Transformed DataFrame containing all processed DICOM metadata and IDs.
    
    Returns:
        pd.DataFrame: DataFrame with procedure_occurrence table columns:
                     - procedure_occurrence_id: Unique identifier for the procedure
                     - person_id: Foreign key to person table
                     - procedure_concept_id: Concept representing the imaging procedure
                     - procedure_date: Date the procedure was performed
                     - procedure_type_concept_id: Concept for procedure type (e.g., EHR)
    """
    procedure_occurrence_columns: List[str] = [
        "procedure_occurrence_id",
        "person_id",
        "modality_concept_id",
        "image_occurrence_date",
        "visit_type_concept_id"
    ]

    df_po: pd.DataFrame = df[procedure_occurrence_columns].rename(
        columns={
            "modality_concept_id": "procedure_concept_id",
            "image_occurrence_date": "procedure_date",
            "visit_type_concept_id": "procedure_type_concept_id"
        }
    )
    return df_po

def visit_occurrence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create visit_occurrence table records from transformed DICOM data.
    
    Extracts relevant columns and renames them to match the OMOP CDM visit_occurrence
    table schema. Sets visit_end_date equal to visit_start_date since imaging visits
    are typically single-day events.
    
    Args:
        df: Transformed DataFrame containing all processed DICOM metadata and IDs.
    
    Returns:
        pd.DataFrame: DataFrame with visit_occurrence table columns:
                     - visit_occurrence_id: Unique identifier for the visit
                     - person_id: Foreign key to person table
                     - visit_concept_id: Concept representing visit type (e.g., Outpatient)
                     - visit_start_date: Date the visit started
                     - visit_end_date: Date the visit ended (same as start for imaging)
                     - visit_type_concept_id: Concept for visit type source (e.g., EHR)
    """
    visit_occurrence_columns: List[str] = [
        "visit_occurrence_id",
        "person_id",
        "visit_concept_id",
        "image_occurrence_date",
        "visit_type_concept_id"
    ]

    df_vo: pd.DataFrame = df[visit_occurrence_columns].rename(
        columns={
            "image_occurrence_date": "visit_start_date"
        }
    )

    df_vo["visit_end_date"] = df_vo["visit_start_date"]

    return df_vo