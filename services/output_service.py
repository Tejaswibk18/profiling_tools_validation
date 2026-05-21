from pathlib import Path


def create_output_folders(module_key, os_type, server_name):
    """
    Creates local output folders according to the required structure:
    outputs/<module_key>/<os_type>/<mode>
    
    Modes:
      - Linux/Arm: 'sudo' and 'nonsudo'
      - Windows: 'administrator' and 'normal user'
    """
    os_type = os_type.lower()
    
    if os_type == "windows":
        paths = {
            "sudo": Path("outputs") / module_key / os_type / "administrator",
            "non_sudo": Path("outputs") / module_key / os_type / "normal user"
        }
    else:
        paths = {
            "sudo": Path("outputs") / module_key / os_type / "sudo",
            "non_sudo": Path("outputs") / module_key / os_type / "nonsudo"
        }

    for path in paths.values():
        path.mkdir(
            parents=True,
            exist_ok=True
        )

    return paths


def save_output(path, filename, content):

    file_path = path / filename

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(content)