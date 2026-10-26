def exec(myinput):

    base_url = "https://raw.githubusercontent.com/OHDSI/ClinicalTrialsWG-TB/refs/heads/main/seeds/stcm/"

    seed_data = {}
    for name in ["drug_route", "source_to_concept_map"]:
        csv_url = base_url + name + ".csv"
        df = pd.read_csv(csv_url)
        df.columns = [col.lower() for col in df.columns]
        seed_data[name] = df

    return seed_data