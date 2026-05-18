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


def get_profile_url(module_key, os_name):
    config = load_config()

    # Map module_key to section name in config.ini
    section_map = {
        "pp": "platform_profiler",
        "wp": "workload_profiler"
    }
    section = section_map.get(module_key, "platform_profiler")

    return config.get(
        section,
        os_name,
        fallback="https://dummyjson.com/users"
    )


def load_server_details(os_name):

    config = configparser.ConfigParser()

    config.read(SERVER_CONFIG)

    if not config.has_section(os_name):
        raise ValueError(f"Missing config section: [{os_name}]")

    return {
        "host": config.get(os_name, "ip", fallback=config.get(os_name, "host", fallback="")),
        "username": config.get(os_name, "username", fallback=config.get(os_name, "user", fallback="")),
        "password": config.get(os_name, "password", fallback=None),
        "key_path": config.get(os_name, "ssh_key", fallback=None)
    }


def fetch_json(module_key, os_name):

    response = requests.get(
        get_profile_url(module_key, os_name),
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



def connect_to_server(keys, module_key, os_name):

    server = load_server_details(os_name)

    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    try:

        connect_args = {
            "hostname": server["host"],
            "username": server["username"]
        }
        if server.get("key_path"):
            connect_args["key_filename"] = server["key_path"]
        elif server.get("password"):
            connect_args["password"] = server["password"]

        ssh.connect(**connect_args)

        print(
            f"\n[INFO] SSH Connection Successful to {os_name.upper()}"
        )

        output_paths = create_output_folders(module_key, os_name)

        # 2. Create a folder
        folder_name = "profiler_test_dir"
        mkdir_cmd = f"mkdir -p {folder_name}" if os_name != "windows" else f"mkdir {folder_name}"
        _, stdout, _ = ssh.exec_command(mkdir_cmd)
        stdout.read() # Wait for completion
        
        profile_url = get_profile_url(module_key, os_name)
        
        # 3. Download the tool
        if os_name == "windows":
            download_cmd = f'powershell -Command "Invoke-WebRequest -Uri {profile_url} -OutFile {folder_name}\downloaded_tool.txt"'
        else:
            download_cmd = f'wget -O {folder_name}/downloaded_tool.txt {profile_url}'
            
        _, stdout, _ = ssh.exec_command(download_cmd)
        stdout.read() # Wait for completion
        
        # 4. Run the tool (Simulated by running uname/systeminfo and saving to results.txt)
        if os_name == "windows":
            run_cmd = f"systeminfo > {folder_name}\\results.txt"
        else:
            run_cmd = f"uname -a > {folder_name}/results.txt"
            
        _, stdout, _ = ssh.exec_command(run_cmd)
        stdout.read() # Wait for completion
        
        # 5. Copy the results back
        if os_name == "windows":
            copy_cmd = f"type {folder_name}\\results.txt"
        else:
            copy_cmd = f"cat {folder_name}/results.txt"
            
        execute_command(
            ssh,
            copy_cmd,
            output_paths["non_sudo"],
            f"{os_name}_details.txt"
        )
        print("[INFO] Non-Sudo Data Collected Successfully")

        execute_command(
            ssh,
            copy_cmd,
            output_paths["sudo"],
            f"{os_name}_details.txt"
        )
        print("[INFO] Sudo Data Collected Successfully")

        # 6. Delete the folder that we created
        if os_name == "windows":
            delete_cmd = f"rmdir /s /q {folder_name}"
        else:
            delete_cmd = f"rm -rf {folder_name}"
            
        _, stdout, _ = ssh.exec_command(delete_cmd)
        stdout.read() # Wait for completion

        data = fetch_json(module_key, os_name)

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