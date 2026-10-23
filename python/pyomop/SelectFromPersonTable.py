async def exec(myinput):
  cdm = myinput["InsertPersonRecords"].result
  engine = cdm.engine
  async with cdm.session() as session:
    stmt = select(Person).where(Person.person_id == 100)
    result = await session.execute(stmt)
    person_obj = result.scalars().all()[0]

    await session.close()
  await engine.dispose()
    
  return person_obj.gender_concept_id