# Input: transform_fhir_to_measurement (dataframe) - OMOP measurement records (eq_vas only) output from the FHIR-to-OMOP transform node
# Input: get_questionnaire (dataframe) - every Questionnaire resource; the VAS item's own SNOMED code is
#         read from the Questionnaire each response was answered against
# Input: get_fhir_data (dataframe) - the raw QuestionnaireResponse resources, for each response's
#         `questionnaire` canonical reference ('url|version') and `language`
# Output: result (dataframe) - Measurement records with resolved person_id, measurement_concept_id resolved from
#         the Questionnaire's VAS item SNOMED code via the vocab schema's concept table, the fixed
#         measurement_type_concept_id, and measurement_source_value restored to plain qrId. value_as_number is
#         already set directly by the structure map (extractVasDecimal copies answer.valueDecimal natively) - no
#         Python-side numeric cast needed, unlike the Observation branch's coded dimension answers.

MEASUREMENT_TYPE_CONCEPT_ID = 32862

# linkIds the VAS question can carry in the Questionnaire / QuestionnaireResponse
VAS_LINK_IDS = ("health-today", "eq_vas")


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


def vas_snomed_code(items: list):
    """The SNOMED code declared on the Questionnaire's VAS item, or None."""
    codes = extract_link_id_snomed_codes(items)
    for link_id in VAS_LINK_IDS:
        if codes.get(link_id):
            return codes[link_id]
    return None


def exec(myinput):
    data = _unwrap_input_value(myinput.get("transform_fhir_to_measurement"))
    questionnaire_df = _unwrap_input_value(myinput.get("get_questionnaire"))
    fhir_data_df = _unwrap_input_value(myinput.get("get_fhir_data"))

    if data is None or data.empty:
        return pd.DataFrame()

    if not dest_db or not dest_schema:
        raise ValueError("Missing `dest_db` or `dest_schema`")

    if questionnaire_df is None or questionnaire_df.empty:
        raise ValueError("No Questionnaire resource returned by get_questionnaire")
    if fhir_data_df is None or fhir_data_df.empty:
        raise ValueError("No QuestionnaireResponse resource returned by get_fhir_data")

    # Vocabulary can live in its own schema (e.g. 'cdmvocab'); falls back to dest_schema when unset.
    concept_schema = globals().get("vocab_schema") or dest_schema
    print(f"[concept resolution] looking up SNOMED concepts in {concept_schema}.concept")

    qr_id_to_ref = build_qr_id_to_questionnaire_ref(fhir_data_df)
    questionnaires = build_questionnaires(questionnaire_df)

    # Computed lazily per Questionnaire (url|version) and cached.
    vas_concept_by_key: dict[str, int | None] = {}

    def vas_concept_id_for(questionnaire: dict) -> int | None:
        key = questionnaire["key"]
        if key not in vas_concept_by_key:
            code = vas_snomed_code(questionnaire["items"])
            if code is None:
                print(f"[questionnaire] {key}: no VAS item ({', '.join(VAS_LINK_IDS)}) with a SNOMED code - skipping")
                vas_concept_by_key[key] = None
            else:
                resolved = resolve_snomed_to_concept_ids({code}, dest_db, concept_schema).get(code)
                if resolved is None:
                    print(f"[questionnaire] {key}: VAS SNOMED code {code} not found in {concept_schema}.concept - skipping")
                else:
                    print(f"[questionnaire] {key}: VAS measurement_concept_id = {resolved} (SNOMED {code})")
                vas_concept_by_key[key] = resolved
        return vas_concept_by_key[key]

    person_id_map = load_person_id_map(dest_db, dest_schema)
    if not person_id_map:
        raise ValueError(
            f"No person mappings found in {dest_db}_{dest_schema}_fhir_mapping.fhir_omop_key_map — "
            "run the person pipeline before the measurement (VAS) pipeline"
        )

    print(f"[resolve] columns: {list(data.columns)}, rows: {len(data)}")

    result_rows = []
    skipped_person = []
    skipped_no_questionnaire = []
    skipped_concept = []
    for _, row in data.iterrows():
        raw_ref = extract_patient_ref(row.get("person_id"))
        normalized_ref = normalize_fhir_id(raw_ref)
        raw_ref_key = str(raw_ref).strip() if raw_ref is not None else None

        person_id = person_id_map.get(raw_ref_key) or person_id_map.get(normalized_ref)
        if person_id is None:
            skipped_person.append(raw_ref_key)
            continue

        source_value = row.get("measurement_source_value") or ""
        qr_id, sep, _link_id = source_value.partition("::")

        qr_ref = qr_id_to_ref.get(qr_id)
        questionnaire = find_questionnaire(questionnaires, qr_ref[0], qr_ref[1]) if qr_ref else None
        if questionnaire is None:
            skipped_no_questionnaire.append(qr_ref[0] if qr_ref else qr_id)
            continue

        concept_id = vas_concept_id_for(questionnaire)
        if concept_id is None:
            skipped_concept.append(questionnaire["key"])
            continue

        entry = row.to_dict()
        entry["person_id"] = person_id
        entry["measurement_source_value"] = qr_id
        entry["measurement_concept_id"] = concept_id
        entry["measurement_type_concept_id"] = MEASUREMENT_TYPE_CONCEPT_ID
        result_rows.append(entry)

    if skipped_person:
        print(f"[resolve] skipped {len(skipped_person)} rows with no person mapping: {skipped_person[:10]}")
    if skipped_no_questionnaire:
        print(f"[resolve] skipped {len(skipped_no_questionnaire)} rows whose response matches no Questionnaire "
              f"url|version in the store: {set(skipped_no_questionnaire)}")
    if skipped_concept:
        print(f"[resolve] skipped {len(skipped_concept)} rows with no resolved VAS measurement_concept_id "
              f"for Questionnaire(s): {set(skipped_concept)}")

    if not result_rows:
        raise ValueError(
            f"All {len(data)} rows skipped. No person mapping: {len(skipped_person)} "
            f"(e.g. {skipped_person[:5]}); no matching Questionnaire: {len(skipped_no_questionnaire)}; "
            f"no resolved VAS concept: {len(skipped_concept)}"
        )

    result_df = pd.DataFrame(result_rows)
    print(f"[resolve] output shape: {result_df.shape}")
    return result_df.reset_index(drop=True)
