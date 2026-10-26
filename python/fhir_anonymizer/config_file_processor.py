from _shared_flow_utils.api.SupabaseStorageAPI import SupabaseStorageAPI

def exec(myinput):
  node_id = myinput["JsonConfiguration"].result.get("node_id")
  filename = myinput["JsonConfiguration"].result.get("filename")
  raw_data = SupabaseStorageAPI().get_file(node_id, filename)
  output_folder = Path("./downloads/config_file")

  output_folder.mkdir(exist_ok=True)
  save_path = output_folder / filename
  save_path.write_bytes(raw_data)
  return save_path