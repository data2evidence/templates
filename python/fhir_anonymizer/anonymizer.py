import subprocess

def exec(myinput) -> str:
    input_dir = myinput["SetConstants"].result.get("INPUT_DIR")
    ANONYMIZER = myinput["SetConstants"].result.get("ANONYMIZER")
    output_dir = myinput["SetConstants"].result.get("OUTPUT_DIR")

    config_dir = Path(myinput["SetConstants"].result.get("CONFIG_FILE"))
    # Get the first (and presumably only) file inside the folder
    config_file = next(config_dir.glob("*"))
    print(f"Take input from {input_dir} anonymize with {ANONYMIZER}, with config at {config_file}, output to {output_dir}")
    # Run the anonymizer tool
    cmd = [
        "dotnet", ANONYMIZER,
        "-i", input_dir,
        "-o", output_dir,
        "-b", input_dir,
        "-c", str(config_file)
    ]
    subprocess.run(cmd, check=True)
    return output_dir
    