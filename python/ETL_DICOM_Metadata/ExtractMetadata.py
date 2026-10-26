from typing import Any, Dict, List, Generator, Optional
from pydicom import dcmread
from pydicom.dataelem import DataElement
from pydicom.tag import BaseTag

def exec(myinput: Dict[str, Any]) -> pd.DataFrame:
  """
  Extract metadata from DICOM files retrieved from the workflow.
  
  This is the main entry point that retrieves a list of DICOM file paths
  from the workflow input and extracts all metadata elements from each file.
  
  Args:
      myinput: Dictionary containing workflow data, expected to have a
               "GetDICOMFileList" key with result containing DICOM file paths.
  
  Returns:
      pd.DataFrame: DataFrame containing extracted metadata from all DICOM files,
                    with columns for study UIDs, series UIDs, tags, values, and more.
  """
  dcm_files: List[str] = myinput["GetDICOMFileList"].result

  extracted_data_df: pd.DataFrame = extract_data_elements(dcm_files)
  
  return extracted_data_df

def extract_data_elements(dicom_files: List[str]) -> pd.DataFrame:
    """
    Extract all metadata elements from a list of DICOM files.
    
    This function iterates through each DICOM file, extracts key identifiers
    (Study/Series/SOP Instance UIDs), and recursively processes all data elements
    including nested sequences. Skips elements with VR="UN" (Unknown) and handles
    errors gracefully.
    
    Args:
        dicom_files: List of absolute file paths to DICOM files.
    
    Returns:
        pd.DataFrame: DataFrame with extracted metadata including columns:
                     - id: Unique identifier for each metadata record
                     - metadata_source_name: DICOM element name
                     - tag: DICOM tag in string format
                     - VR: Value Representation
                     - value: Element value (None for sequences)
                     - image_study_uid, image_series_uid, sop_instance_id
                     - And more fields...
    
    Raises:
        Exception: If any data elements fail to process.
    
    Note:
        - Asserts that each file has a unique SOP Instance ID
        - Asserts that each metadata record has a unique ID
    """
    extracted_metadata: List[Dict[str, Any]] = []
    error_elements: List[Dict[str, Any]] = []
    generator_fn: Generator[int, None, None] = incrementer()

    print(f"Extracting metadata from {len(dicom_files)} files..")

    for filepath in dicom_files:
        with dcmread(filepath, stop_before_pixels=True, force=True) as dicom_f:

            study_instance_uid = dicom_f.get("StudyInstanceUID")  # [0x0020, 0x000D]
            series_instance_uid = dicom_f.get("SeriesInstanceUID")  # [0x0020, 0x000E]
            sop_instance_uid = dicom_f.get("SOPInstanceUID")  # [0x0008,0x0018]
            instance_number = dicom_f.get("InstanceNumber", None)  # [0x0020,0x0013]

            record = {
                "image_study_uid": study_instance_uid,
                "image_series_uid": series_instance_uid,
                "sop_instance_id": sop_instance_uid,
                "instance_number": instance_number,
                "filepath": str(filepath)
            }



            for data_elem in dicom_f:
                # Filter out values that are too large to store in db
                if data_elem.VR == "UN":
                    continue  # skip
                else:
                    try:
                        extracted_metadata.extend(data_elem_to_dict(
                            data_elem, record, generator_fn))
                    except Exception as e:
                        error_msg = f"Failed to process {data_elem.name}: {e}"
                        error_elements.append(
                            {
                                "filepath": str(filepath),
                                "data_element_name": data_elem.name,
                                "data_element_tag": data_elem.tag,
                                "data_element_vr": data_elem.VR
                            }
                        )
                        print(error_msg)

    print(f"Successfully extracted metadata for {len(extracted_metadata)} data elements")

    if len(error_elements) > 0:
        processing_error_msg = f"Failed to extract metadata for {len(error_elements)} data elements"
        print(processing_error_msg)
        raise Exception(processing_error_msg)

    extracted_metadata_df: pd.DataFrame = pd.DataFrame(extracted_metadata)

    assert extracted_metadata_df["sop_instance_id"].nunique() == len(
        dicom_files)
    assert extracted_metadata_df["id"].nunique() == len(extracted_metadata)

    return extracted_metadata_df



def incrementer() -> Generator[int, None, None]:
    """
    Generate sequential integer IDs starting from 1.
    
    This generator provides unique incremental IDs for metadata records,
    ensuring each extracted data element has a unique identifier.
    
    Yields:
        int: The next sequential integer (1, 2, 3, ...).
    """
    n: int = 1
    while True:
        yield n
        n += 1


def convert_tag_to_string(tag: BaseTag) -> str:
    """
    Convert a DICOM tag to its string representation.
    
    Formats a DICOM tag as an 8-character hexadecimal string by concatenating
    the group and element numbers (e.g., "00100010" for Patient Name).
    
    Args:
        tag: DICOM tag object containing group and element numbers.
    
    Returns:
        str: 8-character hexadecimal string representation (e.g., "00100010").
    """
    tag_str: str = f"{tag.group:04X}{tag.element:04X}"
    return tag_str


def data_elem_to_dict(data_element: DataElement, record: Dict[str, Any], 
                      generator_fn: Generator[int, None, None], 
                      parent_seq_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Recursively convert a DICOM data element to dictionary records.
    
    Processes a single DICOM data element and extracts its metadata. If the element
    is a sequence (VR="SQ"), recursively processes nested data elements within the
    first item of the sequence.
    
    Args:
        data_element: DICOM data element to process.
        record: Base record dictionary containing study/series/SOP UIDs and filepath.
        generator_fn: Generator function providing unique IDs for each record.
        parent_seq_id: ID of the parent sequence if this element is nested, None otherwise.
    
    Returns:
        List[Dict[str, Any]]: List containing the current element's metadata and all
                             nested elements' metadata (if it's a sequence).
    
    Note:
        - For sequences, only the first item (index 0) is processed to avoid excessive data
        - Each nested element maintains a reference to its parent via parent_seq_id
    """
    
    id: int = next(generator_fn)

    result: List[Dict[str, Any]] = [extract_metadata(data_element, record, id, parent_seq_id)]
    
    if data_element.VR == "SQ": # Include nested data elements in sequences
        sq_dataset = data_element.value

        if len(sq_dataset) > 0: # non-empty sequence
            for sq_data_elem in sq_dataset[0]: # Use the 0 idx to access data elements in the dataset in the sequence
                result.extend(data_elem_to_dict(data_element=sq_data_elem, record=record,
                                                generator_fn=generator_fn, parent_seq_id=id))
    return result


def extract_metadata(data_element: DataElement, record: Dict[str, Any], 
                    id: int, parent_sequence_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract metadata from a DICOM data element into a dictionary.
    
    Creates a comprehensive metadata dictionary for a DICOM data element, including
    tag information, value representation, actual value, sequence details, and privacy status.
    
    Args:
        data_element: DICOM data element to extract metadata from.
        record: Base record dictionary containing study/series/SOP UIDs and filepath.
        id: Unique identifier for this metadata record.
        parent_sequence_id: ID of parent sequence if this element is nested, None otherwise.
    
    Returns:
        Dict[str, Any]: Dictionary containing all metadata fields:
                       - id, metadata_source_name, metadata_source_keyword
                       - tag (string), tag_tuple (formatted), VR, value
                       - is_sequence, sequence_length, parent_sequence_id
                       - is_private, private_creator
                       - Plus all fields from the base record
    """
    sequence_length: Optional[int] = get_sequence_length(data_element) if data_element.VR == "SQ" else None
    metadata: Dict[str, Any] = {
        "id": id,
        "metadata_source_name": data_element.name,
        "metadata_source_keyword": data_element.keyword,
        "tag": convert_tag_to_string(data_element.tag),
        "tag_tuple": convert_tag_to_tuple(data_element.tag),
        "VR": data_element.VR,
        "value": None if data_element.VR == "SQ" else extract_data_element_value(data_element),
        "is_sequence": True if data_element.VR == "SQ" else False,
        "sequence_length": sequence_length,
        "parent_sequence_id": parent_sequence_id if parent_sequence_id else None,
        "is_private": data_element.is_private,
        "private_creator": data_element.private_creator,
    }
    metadata.update(record)
    return metadata


def get_sequence_length(data_element: DataElement) -> int:
    """
    Get the number of elements in the first level of a DICOM sequence.
    
    For sequence data elements (VR="SQ"), returns the count of data elements
    contained in the first item of the sequence. Empty sequences return 0.
    
    Args:
        data_element: DICOM sequence data element.
    
    Returns:
        int: Number of data elements in the first sequence item, or 0 if empty.
    """
    if data_element.value:
        sq_dataset = data_element.value  # Access the sequence 
        return len(sq_dataset[0])
    else:
        # Empty sequences don't have a .value
        return 0

def convert_tag_to_tuple(tag: BaseTag) -> str:
    """
    Convert a DICOM tag to its tuple string representation.
    
    Formats a DICOM tag as a tuple-like string with hexadecimal group and element
    numbers (e.g., "(0010,0010)" for Patient Name).
    
    Args:
        tag: DICOM tag object containing group and element numbers.
    
    Returns:
        str: Tuple-formatted string (e.g., "(0010,0010)").
    """
    tag_tuple: str = f"({tag.group:04X},{tag.element:04X})"
    return tag_tuple

def extract_data_element_value(data_element: DataElement) -> Optional[str]:
    """
    Extract and convert a DICOM data element's value to string.
    
    Converts the data element's value to a string representation. Returns None
    if the element has no value.
    
    Args:
        data_element: DICOM data element to extract value from.
    
    Returns:
        Optional[str]: String representation of the value, or None if no value exists.
    
    Note:
        This function is typically not called for sequence elements (VR="SQ"),
        which have their value set to None in the metadata.
    """
    if data_element.value: 
        return str(data_element.value)
    return None
