async def exec(myinput):
  tenant_configs = myinput["GetDBCredentials"].result
  
  cdm = CdmEngineFactory(
    db='pgsql', 
    host=tenant_configs.host, 
    port=tenant_configs.port,
    user=tenant_configs.adminUser,
    pw=tenant_configs.adminPassword.get_secret_value(),
    name=tenant_configs.databaseName, 
    schema=schema_name
  )
  
  engine = cdm.engine

  async with cdm.session() as session:
    async with session.begin():
      session.add(
          Person(
              person_id=100,
              gender_concept_id=8532,
              gender_source_concept_id=8512,
              year_of_birth=1980,
              month_of_birth=1,
              day_of_birth=1,
              birth_datetime=datetime.datetime(1980, 1, 1),
              race_concept_id=8552,
              race_source_concept_id=8552,
              ethnicity_concept_id=38003564,
              ethnicity_source_concept_id=38003564,
          )
      )

      session.add(
          Person(
              person_id=101,
              gender_concept_id=8532,
              gender_source_concept_id=8512,
              year_of_birth=1980,
              month_of_birth=1,
              day_of_birth=1,
              birth_datetime=datetime.datetime(1980, 1, 1),
              race_concept_id=8552,
              race_source_concept_id=8552,
              ethnicity_concept_id=38003564,
              ethnicity_source_concept_id=38003564,
          )
      )
    await session.commit()

    await session.close()
  await engine.dispose()
    
  return cdm