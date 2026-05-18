from pathlib import Path


def create_output_folders(module_key, os_name):

    base_output = Path(
        f"outputs/{module_key}/{os_name}"
    )

    paths = {
        "sudo": base_output / "with_sudo",
        "non_sudo": base_output / "without_sudo"
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