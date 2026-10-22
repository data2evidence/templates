async def main(myinput):
    LLM_config = myinput.get("LLM_config").result
    user_info = myinput.get("user_info").result
    dbdao = DBDao(database_code=database_code)
    os.environ["AZURE_OPENAI_API_KEY"] = Secret.load("azure-openai-api-key").get()

    with dbdao.ibis_connect() as conn:
        note = conn.table(note_table, database=schema_name)
        record = note.select(['note_id','note_text']).execute()
        rst = dict()
        for note_id, note_text in record.values:
            output = await extract_entities(
                input_data=note_text,
                schema=user_info,
                model_config=LLM_config,
                output_format=output_format,
                mode = mode
                )
            rst[str(note_id)] = output
        return rst

def exec(myinput):
    return asyncio.run(main(myinput))

    