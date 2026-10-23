# Input: transform_to_person (dataframe) - transformed OMOP person rows from the mapping node
# Output: result (dataframe) - person rows with stable/reused `person_id` values


def _normalize_fhir_id(value):
    if value is None:
        return None
    s = str(value).strip()
    return s.split("/")[-1] if "/" in s else s


DEFAULTS = {
    "gender_concept_id": 0,
    "year_of_birth": 0,
    "race_concept_id": 0,
    "ethnicity_concept_id": 0,
}


# Demo only: overwrite each person's demographics with one of these sample profiles. The profile is
# picked from a hash of the FHIR id, so a patient gets the same values on every run. Set
# USE_DEMO_DEMOGRAPHICS = False to keep the values the structure map produced.
USE_DEMO_DEMOGRAPHICS = True
DEMO_DEMOGRAPHICS = [
    # (year_of_birth, gender_concept_id, race_concept_id, ethnicity_concept_id)
    (1968, 8532, 38003599, 38003564),
    (1959, 8507, 8527, 38003564),
    (1969, 8532, 38003599, 38003564),
    (1986, 8507, 8527, 38003563),
    (1973, 8532, 8527, 38003563),
    (1978, 8532, 8527, 38003564),
    (1985, 8507, 8515, 38003563),
    (1981, 8507, 38003599, 38003564),
    (1950, 8507, 8527, 38003563),
    (1954, 8507, 8515, 38003564),
    (1970, 8532, 38003599, 38003564),
    (1955, 8532, 8515, 38003563),
    (1962, 8507, 8515, 38003564),
    (1955, 8507, 8527, 38003564),
    (1956, 8532, 8515, 38003563),
    (1951, 8532, 8515, 38003564),
    (1977, 8532, 8527, 38003563),
    (1959, 8532, 8515, 38003563),
    (1977, 8532, 38003599, 38003563),
    (1972, 8532, 8515, 38003563),
    (1952, 8532, 8515, 38003564),
    (1979, 8507, 38003599, 38003564),
    (1951, 8532, 8515, 38003564),
    (1967, 8532, 38003599, 38003563),
    (1982, 8532, 8515, 38003563),
]


def _apply_demo_demographics(df):
    import hashlib

    def profile(source_value):
        digest = hashlib.md5(str(source_value).encode("utf-8")).hexdigest()
        return DEMO_DEMOGRAPHICS[int(digest, 16) % len(DEMO_DEMOGRAPHICS)]

    profiles = df["person_source_value"].map(profile)
    for idx, col in enumerate(["year_of_birth", "gender_concept_id", "race_concept_id", "ethnicity_concept_id"]):
        df[col] = profiles.map(lambda p: p[idx])
    # birth_datetime / month / day would contradict the demo year_of_birth - clear them
    for col in ("birth_datetime", "month_of_birth", "day_of_birth"):
        if col in df.columns:
            df[col] = None
    print(f"[demo] assigned demo demographics to {len(df)} person rows")
    return df


def _assign_person_ids(source_values, existing, max_id):
    next_id = max(max_id, max(existing.values(), default=0)) + 1
    assigned = {}
    assigned_ids = []

    for source_val in source_values:
        if source_val in existing:
            person_id = existing[source_val]
        elif source_val in assigned:
            person_id = assigned[source_val]
        else:
            person_id = next_id
            assigned[source_val] = person_id
            next_id += 1
        assigned_ids.append(person_id)

    return assigned_ids


def exec(myinput):
    df = myinput.get("transform_to_person").result
    database_code = dest_db
    schema_name = dest_schema

    if df is None or df.empty:
        return df

    if not database_code or not schema_name:
        raise ValueError("`database_code` and `schema_name` must be provided")

    for col, default in DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
        else:
            df[col] = df[col].fillna(default)

    dao = SqlAlchemyDao(database_code=database_code)
    mapping_dao = DBDao(dialect=SupportedDatabaseDialects.TREX, database_code=database_code)
    mapping_schema = f"{database_code}_{schema_name}_fhir_mapping"

    df["person_source_value"] = df["person_source_value"].apply(_normalize_fhir_id)
    df = df.dropna(subset=["person_source_value"])
    if df.empty:
        return df

    if USE_DEMO_DEMOGRAPHICS:
        df = _apply_demo_demographics(df.copy())

    fhir_ids = df["person_source_value"].unique().tolist()

    # 1. Look up existing person_ids from data_source before deleting
    escaped_schema = mapping_schema.replace('"', '""')
    try:
        rows = mapping_dao.execute_sql(
            f"""
            SELECT DISTINCT ON (fhir_resource_id) fhir_resource_id, omop_id
            FROM "{escaped_schema}"."data_source"
            WHERE omop_table_name = 'person'
              AND omop_id IS NOT NULL
            ORDER BY fhir_resource_id, transformed_at DESC
            """,
            fetch=True,
        ) or []
        existing = {row[0]: int(row[1]) for row in rows if row[1] is not None}
    except Exception:
        existing = {}

    # 2. Delete existing person rows for these FHIR IDs
    omop_meta = sql.MetaData(schema=schema_name)
    person_table = sql.Table("person", omop_meta, autoload_with=dao.engine)

    deleted = dao.execute_sqlalchemy_statement(
        person_table.delete().where(
            person_table.c.person_source_value.in_(fhir_ids)
        ),
        lambda r: r.rowcount,
    )
    print(f"Deleted {deleted} rows from {schema_name}.person")

    # 3. Get max_id from what remains in the table (after deletion)
    max_id = dao.execute_sqlalchemy_statement(
        sql.select(sql.func.coalesce(sql.func.max(person_table.c.person_id), 0)),
        lambda r: r.scalar(),
    )

    # 4. Assign person_ids — reuse existing, mint new for new records
    df = df.copy()
    assigned_ids = _assign_person_ids(df["person_source_value"], existing, max_id)
    df["person_id"] = assigned_ids
    reused = sum(1 for i in assigned_ids if i in existing.values())
    print(f"Assigned person_ids: {reused} reused, {len(assigned_ids) - reused} new")
    return df
