def exec(myinput):
  file_list = myinput["GetFiles"].result

  processed = {}

  for file in file_list:
    domain = file.stem.lower()

    # Process based on domain
    if domain in ["dm", "ds", "sv", "cm"]:

      source_df = pd.read_csv(file)

      # Convert columns to lowercase for consistent handling

      source_df.columns = [col.lower() for col in source_df.columns]

      # Special case handling
      match domain:
        case "cm": # Concomitant Medications
          convert_col_to_integer('visitnum', source_df)
          convert_col_to_integer('cmstdy', source_df)
          convert_col_to_integer('cmendy', source_df)

          source_df['cm_concat'] = source_df['cmtrt'].astype(str) + '|' + source_df['cmdose'].astype(str) + '|' + source_df['cmdosu'].astype(str) + '|' + source_df['cmroute'].astype(str)
          
        case "ds": # Disposition
          convert_col_to_integer('visitnum', source_df)
          convert_col_to_integer('dsstdy', source_df)
          # Todo: Uncomment
          # convert_col_to_integer('livedy', source_df)
          # convert_col_to_integer('totcldur', source_df)


        case "sv":
          convert_col_to_integer('svstdy', source_df)
          convert_col_to_integer('svendy', source_df)

      processed[domain] = source_df

  return processed

def convert_col_to_integer(col, df):
    df[col] = df[col].apply(lambda x: None if pd.isna(x) else int(x))



    