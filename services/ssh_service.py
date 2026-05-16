import requests
import paramiko
import configparser

from services.config_service import load_config
from services.logger_service import log_error

from services.output_service import (
    create_output_folders,
    save_output
)

SERVER_CONFIG = "server_details.ini"


def get_profile_url():
    config = load_config()

    return config.get(
        "linux",
        "profile_url"
    )


def load_server_details():

    config = configparser.ConfigParser()

    config.read(SERVER_CONFIG)

    required_keys = (
        "ip",
        "username",
        "ssh_key"
    )

    missing = [
        key for key in required_keys
        if not config.has_option("linux", key)
    ]

    if missing:
        raise ValueError(
            f"Missing config keys : {', '.join(missing)}"
        )

    return {
        "host": config.get("linux", "ip"),
        "username": config.get("linux", "username"),
        "key_path": config.get("linux", "ssh_key")
    }


def fetch_json():

    response = requests.get(
        get_profile_url(),
        timeout=10
    )

    response.raise_for_status()

    return response.json()


def extract_nested_value(data, keys):

    if not keys:
        return [data]

    key = keys[0]

    results = []

    try:

        if isinstance(data, list):

            for item in data:
                results.extend(
                    extract_nested_value(
                        item,
                        keys
                    )
                )

        elif isinstance(data, dict):

            if key in data:

                results.extend(
                    extract_nested_value(
                        data[key],
                        keys[1:]
                    )
                )

    except Exception:
        pass

    return results


def validate_keys(data, keys):

    validation_results = []

    for key in map(str.strip, keys):

        try:
            cleaned_key = (
                key.replace("[", "")
                   .replace("]", "")
            )

            nested_keys = cleaned_key.split(".")

            values = extract_nested_value(
                data,
                nested_keys
            )

            if not values:

                validation_results.append(
                    f"[FAIL] {key} : KEY NOT FOUND"
                )

                continue

            for value in values:

                result = (
                    "NULL VALUE"
                    if value is None
                    else f"FOUND -> {value}"
                )

                validation_results.append(
                    f"[PASS] {key} : {result}"
                )

        except Exception as error:

            validation_results.append(
                f"[ERROR] {key} : {error}"
            )

    return "\n".join(validation_results)

    
def execute_command(
    ssh,
    command,
    output_path,
    filename
):

    stdin, stdout, stderr = ssh.exec_command(
        command
    )

    output = stdout.read().decode()

    error = stderr.read().decode()

    content = error or output

    save_output(
        output_path,
        filename,
        content
    )

    return content



def connect_linux_server(keys):

    server = load_server_details()

    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    try:

        ssh.connect(
            hostname=server["host"],
            username=server["username"],
            key_filename=server["key_path"]
        )

        print(
            "\n[INFO] SSH Connection Successful"
        )

        output_paths = create_output_folders()

        execute_command(
            ssh,
            "uname -a",
            output_paths["non_sudo"],
            "linux_details.txt"
        )

        print(
            "[INFO] Non-Sudo Data Collected Successfully"
        )

        execute_command(
            ssh,
            "sudo uname -a",
            output_paths["sudo"],
            "linux_details.txt"
        )

        print(
            "[INFO] Sudo Data Collected Successfully"
        )

        data = fetch_json()

        print(
            "[INFO] JSON Data Collected Successfully"
        )

        validation_output = validate_keys(
            data,
            keys
        )

        save_output(
            output_paths["non_sudo"],
            "validation_results.txt",
            validation_output
        )

        save_output(
            output_paths["sudo"],
            "validation_results.txt",
            validation_output
        )

        print(
            "[INFO] Validation Results Stored Successfully"
        )

    except paramiko.AuthenticationException:

        message = "Authentication Failed"

        print(f"\n[ERROR] {message}")

        log_error(message)

    except paramiko.SSHException as error:

        message = f"SSH Error : {error}"

        print(f"\n[ERROR] {message}")

        log_error(message)

    except requests.RequestException as error:

        message = f"API Error : {error}"

        print(f"\n[ERROR] {message}")

        log_error(message)

    except ValueError as error:

        message = f"Config Error : {error}"

        print(f"\n[ERROR] {message}")

        log_error(message)

    except Exception as error:

        message = str(error)

        print(f"\n[ERROR] {message}")

        log_error(message)

    finally:

        ssh.close()

        print(
            "\n[INFO] SSH Connection Closed"
        )