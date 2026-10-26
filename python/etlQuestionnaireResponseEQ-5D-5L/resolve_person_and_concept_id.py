# Input: transform_fhir_to_omop (dataframe) - OMOP observation records output from the FHIR-to-OMOP transform node
# Input: get_questionnaire (dataframe) - every Questionnaire resource in the FHIR store (not scoped -
#         get_questionnaire is a db_reader_node, which has no way to depend on another node's output,
#         so it can't be filtered to just the url(s) this batch references; the Questionnaire table is
#         small, so fetching all of it is cheap enough that this isn't worth a second hardcoded copy
#         of the FHIR schema string just to scope it)
# Input: get_fhir_data (dataframe) - the raw QuestionnaireResponse resources, used to read each
#         response's own `questionnaire` canonical reference ('url|version') and `language` (the transform node's output doesn't
#         carry that field through - it only maps specific OMOP columns)
# Output: result (dataframe) - Observation records with resolved person_id, observation_concept_id and
#         value_as_number, and observation_source_value restored from 'qrId::linkId' to plain qrId

OBSERVATION_TYPE_CONCEPT_ID = 32862

# The answer code (value_source_value) must be the level number 1-5. Responses that carry a text code
# (e.g. 'slight-problems', 'OMOP5181559') are ignored for now.
VALID_ANSWER_CODES = {"1", "2", "3", "4", "5"}


def _unwrap_input_value(value):
    return value.result if hasattr(value, "result") else value


def extract_patient_ref(value):
    if isinstance(value, dict):
        return value.get("reference") or value.get("id") or str(value)
    return str(value) if value is not None else None


def normalize_fhir_id(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "/" in s:
        s = s.split("/")[-1]
    return s


def load_person_id_map(database_code: str, schema_name: str) -> dict[str, int]:
    mapping_schema = f"{database_code}_{schema_name}_fhir_mapping"
    dao = DBDao(
        dialect=SupportedDatabaseDialects.TREX,
        database_code=database_code,
    )
    escaped_schema = mapping_schema.replace('"', '""')
    query = f"""
        SELECT fhir_id, omop_id
        FROM "{escaped_schema}"."fhir_omop_key_map"
        WHERE omop_table_name = 'person'
          AND omop_id IS NOT NULL
    """
    rows = dao.execute_sql(query, fetch=True) or []
    result = {}
    for fhir_id, omop_id in rows:
        if fhir_id is None:
            continue
        try:
            omop_int = int(omop_id)
        except Exception:
            continue
        raw_key = str(fhir_id).strip()
        if raw_key:
            result[raw_key] = omop_int
        norm_key = normalize_fhir_id(fhir_id)
        if norm_key:
            result[norm_key] = omop_int
    print(f"[fhir mapping] loaded {len(result)} person mappings from {mapping_schema}.fhir_omop_key_map")
    return result


def build_qr_id_to_questionnaire_ref(fhir_data_df) -> dict[str, tuple]:
    """{QuestionnaireResponse.id: (QuestionnaireResponse.questionnaire, QuestionnaireResponse.language)}.
    `questionnaire` is a canonical reference, normally 'url|version' (e.g. '.../eq5d5l|2.0.0'), not a
    bare url. language is read from _raw (get_fhir_data doesn't select it as a column)."""
    mapping = {}
    for qr_id, ref, raw in zip(fhir_data_df["id"], fhir_data_df["questionnaire"], fhir_data_df["_raw"]):
        if not (qr_id and ref):
            continue
        language = None
        try:
            language = json.loads(raw).get("language")
        except Exception:
            pass
        mapping[qr_id] = (ref, language)
    return mapping


def split_canonical(ref: str) -> tuple:
    """'url|version' -> (url, version); a bare url -> (url, None)."""
    url, _, version = str(ref).strip().partition("|")
    return url, (version or None)


def build_questionnaires(questionnaire_df) -> list[dict]:
    """One entry per Questionnaire resource: {url, version, language, key, items}. key is the canonical
    reference 'url|version' (just url when there's no version) - language is kept as a separate field,
    not part of the key. Several resources can share a url (versions, translations), so the store is
    kept as a list and matched with find_questionnaire(). item[] is read from _raw rather than the
    item column - that column is a native Postgres composite/array type (not JSON); _raw is valid JSON."""
    entries = []
    for url, raw in zip(questionnaire_df["url"], questionnaire_df["_raw"]):
        if not url:
            continue
        try:
            questionnaire = json.loads(raw)
        except Exception:
            continue
        version = questionnaire.get("version")
        language = questionnaire.get("language")
        entries.append({
            "url": url,
            "version": version,
            "language": language,
            "key": f"{url}|{version}" if version else url,
            "items": questionnaire.get("item") or [],
        })
    return entries


def find_questionnaire(entries: list, ref: str, language) -> dict | None:
    """Match a response's canonical reference (and language) to a Questionnaire resource.
    url must match; version must match when the reference carries one. If several remain (e.g.
    translations), prefer the one whose language equals the response's, then one with no language
    set; otherwise fall back to the first candidate. With no version in the reference, the highest
    version string wins."""
    url, version = split_canonical(ref)
    candidates = [e for e in entries if e["url"] == url and (version is None or e["version"] == version)]
    if not candidates:
        return None
    if version is None:
        candidates.sort(key=lambda e: str(e["version"] or ""), reverse=True)
    if len(candidates) > 1:
        for wanted in (language, None):
            same_language = [e for e in candidates if e["language"] == wanted]
            if same_language:
                return same_language[0]
    return candidates[0]


def extract_link_id_snomed_codes(items: list) -> dict[str, str]:
    """{linkId: snomed concept_code} for every Questionnaire item that declares a SNOMED coding."""
    codes = {}
    for item in items or []:
        link_id = item.get("linkId")
        if not link_id:
            continue
        for coding in item.get("code", []) or []:
            if coding.get("code"):
                codes[link_id] = coding["code"]
                break
    return codes


def resolve_snomed_to_concept_ids(snomed_codes: set, database_code: str, schema_name: str) -> dict:
    """SNOMED concept_code -> standard OMOP concept_id, direct match against the concept table in
    schema_name - the vocab schema (vocabulary_id='SNOMED', standard_concept='S') - the Questionnaire's codes are expected to
    already be standard SNOMED concepts, not source codes needing a concept_relationship 'Maps to' hop.
    """
    if not snomed_codes:
        return {}
    dao = SqlAlchemyDao(database_code=database_code)
    escaped_schema = schema_name.replace('"', '""')
    codes_list = "', '".join(c.replace("'", "''") for c in snomed_codes)
    query = sql.text(f"""
        SELECT concept_code, concept_id
        FROM "{escaped_schema}"."concept"
        WHERE vocabulary_id = 'SNOMED'
          AND standard_concept = 'S'
          AND concept_code IN ('{codes_list}')
    """)
    rows = dao.execute_sqlalchemy_statement(query, lambda r: r.fetchall()) or []
    result = {code: int(concept_id) for code, concept_id in rows}
    missing = snomed_codes - result.keys()
    if missing:
        print(f"[concept resolution] no standard SNOMED concept found for codes: {sorted(missing)}")
    return result


def exec(myinput):
    data = _unwrap_input_value(myinput.get("transform_fhir_to_omop"))
    questionnaire_df = _unwrap_input_value(myinput.get("get_questionnaire"))
    fhir_data_df = _unwrap_input_value(myinput.get("get_fhir_data"))

    if data is None or data.empty:
        return pd.DataFrame()

    if not dest_db or not dest_schema:
        raise ValueError("Missing `dest_db` or `dest_schema`")

    # Vocabulary can live in its own schema (e.g. 'cdmvocab') rather than the dataset's CDM schema,
    # whose concept table may be empty. Falls back to dest_schema when vocab_schema isn't set.
    concept_schema = globals().get("vocab_schema") or dest_schema
    print(f"[concept resolution] looking up SNOMED concepts in {concept_schema}.concept")

    if questionnaire_df is None or questionnaire_df.empty:
        raise ValueError("No Questionnaire resource returned by get_questionnaire")
    if fhir_data_df is None or fhir_data_df.empty:
        raise ValueError("No QuestionnaireResponse resource returned by get_fhir_data")

    qr_id_to_ref = build_qr_id_to_questionnaire_ref(fhir_data_df)
    print(f"[questionnaire] {len(qr_id_to_ref)} QuestionnaireResponse(s) reference a questionnaire")

    questionnaires = build_questionnaires(questionnaire_df)
    print(f"[questionnaire] {len(questionnaires)} Questionnaire resource(s) in store: "
          f"{sorted(e['key'] for e in questionnaires)}")

    # Computed lazily per Questionnaire (url|version) and cached - most runs only ever touch one or two distinct
    # Questionnaires even with many responses, so this avoids re-querying concept per row.
    link_id_to_concept_id_by_key: dict[str, dict] = {}

    def link_id_to_concept_id_for(questionnaire: dict | None) -> dict:
        if questionnaire is None:
            return {}
        url = questionnaire["key"]
        if url not in link_id_to_concept_id_by_key:
            items = questionnaire["items"]
            link_id_to_snomed = extract_link_id_snomed_codes(items)
            if "mobility" not in link_id_to_snomed:
                # get_fhir_data has no WHERE filter (the QuestionnaireResponse table can hold
                # other instruments' responses too) - rather than hardcode this pipeline's
                # Questionnaire url, treat "does this Questionnaire have a mobility item with a
                # SNOMED code" as the signal that it's actually EQ-5D-5L-shaped, and skip it
                # (not an error - just means this response belongs to a different instrument).
                print(f"[questionnaire] {url}: no 'mobility' item with a SNOMED code - "
                      f"doesn't look like EQ-5D-5L, skipping")
                link_id_to_concept_id_by_key[url] = {}
            else:
                snomed_to_concept_id = resolve_snomed_to_concept_ids(
                    set(link_id_to_snomed.values()), dest_db, concept_schema
                )
                resolved = {
                    link_id: snomed_to_concept_id[code]
                    for link_id, code in link_id_to_snomed.items()
                    if code in snomed_to_concept_id
                }
                unresolved = sorted(set(link_id_to_snomed) - set(resolved))
                if unresolved:
                    print(f"[questionnaire] {url}: SNOMED code not found in {concept_schema}.concept for "
                          f"{unresolved} - rows for these items will be skipped")
                print(f"[questionnaire] {url}: resolved observation_concept_id by linkId: {resolved}")
                link_id_to_concept_id_by_key[url] = resolved
        return link_id_to_concept_id_by_key[url]

    person_id_map = load_person_id_map(dest_db, dest_schema)
    if not person_id_map:
        raise ValueError(
            f"No person mappings found in {dest_db}_{dest_schema}_fhir_mapping.fhir_omop_key_map — "
            "run the person pipeline before the observation pipeline"
        )

    print(f"[resolve] columns: {list(data.columns)}, rows: {len(data)}")

    result_rows = []
    skipped_person = []
    skipped_no_questionnaire_ref = []
    skipped_no_questionnaire_match = []
    skipped_concept = []
    skipped_answer_code = []
    for _, row in data.iterrows():
        raw_ref = extract_patient_ref(row.get("person_id"))
        normalized_ref = normalize_fhir_id(raw_ref)
        raw_ref_key = str(raw_ref).strip() if raw_ref is not None else None

        person_id = person_id_map.get(raw_ref_key) or person_id_map.get(normalized_ref)
        if person_id is None:
            skipped_person.append(raw_ref_key)
            continue

        # observation_source_value is 'qrId::linkId' at this point (see EQ5D5L-to-OMOP-Observation's
        # setSourceValue rule) - the linkId identifies which dimension this row is, and qrId is used
        # to look up which specific Questionnaire this response was answered against.
        source_value = row.get("observation_source_value") or ""
        qr_id, sep, link_id = source_value.partition("::")
        link_id = link_id if sep else None

        answer_code = str(row.get("value_source_value") or "").strip()
        if answer_code not in VALID_ANSWER_CODES:
            skipped_answer_code.append((qr_id, link_id, answer_code))
            continue

        qr_ref = qr_id_to_ref.get(qr_id)
        if qr_ref is None:
            skipped_no_questionnaire_ref.append(qr_id)
            continue
        questionnaire_ref, qr_language = qr_ref

        questionnaire = find_questionnaire(questionnaires, questionnaire_ref, qr_language)
        if questionnaire is None:
            skipped_no_questionnaire_match.append((questionnaire_ref, qr_language))
            continue

        concept_id = link_id_to_concept_id_for(questionnaire).get(link_id)
        if concept_id is None:
            skipped_concept.append((questionnaire["key"], link_id))
            continue

        entry = row.to_dict()
        entry["person_id"] = person_id
        entry["observation_source_value"] = qr_id
        entry["observation_concept_id"] = concept_id
        entry["observation_type_concept_id"] = OBSERVATION_TYPE_CONCEPT_ID
        entry["value_as_number"] = float(answer_code)
        result_rows.append(entry)

    if skipped_person:
        print(f"[resolve] skipped {len(skipped_person)} rows with no person mapping: {skipped_person[:10]}")
    if skipped_answer_code:
        print(f"[resolve] skipped {len(skipped_answer_code)} rows whose answer code is not 1-5 (text codes are "
              f"ignored for now), qrIds: {sorted({s[0] for s in skipped_answer_code})[:10]}, "
              f"codes: {sorted({s[2] for s in skipped_answer_code})[:10]}")
    if skipped_no_questionnaire_ref:
        print(f"[resolve] skipped {len(skipped_no_questionnaire_ref)} rows whose qrId has no matching "
              f"QuestionnaireResponse.questionnaire reference: {set(skipped_no_questionnaire_ref)}")
    if skipped_no_questionnaire_match:
        print(f"[resolve] skipped {len(skipped_no_questionnaire_match)} rows whose (questionnaire ref, language) "
              f"matches no Questionnaire url|version in the store: {set(skipped_no_questionnaire_match)}")
    if skipped_concept:
        print(f"[resolve] skipped {len(skipped_concept)} rows with no resolved observation_concept_id "
              f"for (questionnaire url|version, linkId): {set(skipped_concept)}")

    if not result_rows:
        raise ValueError(
            f"All {len(data)} rows skipped - no person_id, questionnaire reference, or "
            f"observation_concept_id match found. Unmatched person refs: {skipped_person[:5]}. "
            f"Rows with a non-1-5 answer code: {len(skipped_answer_code)}. "
            f"qrIds with no questionnaire reference: {set(skipped_no_questionnaire_ref)}. "
            f"Refs with no matching Questionnaire: {set(skipped_no_questionnaire_match)}. "
            f"Unmatched (questionnaire url|version, linkId): {set(skipped_concept)}"
        )

    result_df = pd.DataFrame(result_rows)
    print(f"[resolve] output shape: {result_df.shape}")
    return result_df.reset_index(drop=True)
