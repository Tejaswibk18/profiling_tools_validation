from pathlib import Path


BASE_OUTPUT = Path(
    "outputs/pp/linux"
)


def create_output_folders():

    paths = {
        "sudo": BASE_OUTPUT / "with_sudo",
        "non_sudo": BASE_OUTPUT / "without_sudo"
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