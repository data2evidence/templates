async def exec(myinput):
  cdm = myinput["InsertPersonRecords"].result
  
  engine = cdm.engine

  vec = CdmVector()

  # https://github.com/OHDSI/QueryLibrary/blob/master/inst/shinyApps/QueryLibrary/queries/person/PE02.md
  async with cdm.session() as session:
    result = await vec.query_library(cdm, resource='person', query_name='PE02')
    df = vec.result_to_df(result)

    await session.close()
  await engine.dispose()
    
  return df