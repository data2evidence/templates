# Input: resolve_person_and_set_vas_concept_id (dataframe) - Measurement records (VAS) with resolved person_id and concept ids
# Output: result (dataframe) - Measurement records with assigned measurement_id values, ready for db insert

def exec(myinput):
    data = myinput.get("resolve_person_and_set_vas_concept_id").result

    if data is None or data.empty:
        return data

    data = data.dropna(subset=["measurement_source_value"])
    if data.empty:
        return data

    dao = SqlAlchemyDao(database_code=dest_db)
    fhir_ids = data["measurement_source_value"].unique().tolist()

    omop_meta = sql.MetaData(schema=dest_schema)
    measurement_table = sql.Table("measurement", omop_meta, autoload_with=dao.engine)

    # 1. Look up existing (source_value, concept_id) → measurement_id BEFORE deleting
    existing_rows = dao.execute_sqlalchemy_statement(
        sql.select(
            measurement_table.c.measurement_source_value,
            measurement_table.c.measurement_concept_id,
            measurement_table.c.measurement_id,
        ).where(measurement_table.c.measurement_source_value.in_(fhir_ids)),
        lambda r: r.fetchall(),
    ) or []
    existing = {(row[0], row[1]): row[2] for row in existing_rows}
    print(f"Found {len(existing)} existing measurement rows to reuse")

    # 2. Delete existing measurement rows for these FHIR IDs
    deleted = dao.execute_sqlalchemy_statement(
        measurement_table.delete().where(
            measurement_table.c.measurement_source_value.in_(fhir_ids)
        ),
        lambda r: r.rowcount,
    )
    print(f"Deleted {deleted} rows from {dest_schema}.measurement")

    # 3. Assign IDs — reuse by (source_value, concept_id), mint new for new records
    max_id = dao.execute_sqlalchemy_statement(
        sql.select(sql.func.coalesce(sql.func.max(measurement_table.c.measurement_id), 0)),
        lambda r: r.scalar(),
    )

    data = data.copy()
    next_id = max(max_id, max(existing.values(), default=0)) + 1
    assigned_ids = []
    for _, row in data.iterrows():
        key = (row["measurement_source_value"], int(row["measurement_concept_id"]))
        if key in existing:
            assigned_ids.append(existing[key])
        else:
            assigned_ids.append(next_id)
            next_id += 1

    data["measurement_id"] = assigned_ids
    reused = sum(1 for i in assigned_ids if i in {v for v in existing.values()})
    print(f"Assigned measurement_ids: {reused} reused, {len(assigned_ids) - reused} new")
    return data
