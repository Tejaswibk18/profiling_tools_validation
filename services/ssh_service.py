import paramiko
import configparser

from services.config_service import load_config
from services.logger_service import log_error

from services.output_service import (
    create_output_folders
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
        fallback=""
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


# === DEPRECATED: Kept only for test_cases/ support ===
def extract_nested_value(data, keys):
    if not keys:
        return [data]
    key = keys[0]
    results = []
    try:
        if isinstance(data, list):
            for item in data:
                results.extend(extract_nested_value(item, keys))
        elif isinstance(data, dict):
            if key in data:
                results.extend(extract_nested_value(data[key], keys[1:]))
    except Exception:
        pass
    return results

def validate_keys(data, keys):
    validation_results = []
    for key in map(str.strip, keys):
        try:
            cleaned_key = key.replace("[", "").replace("]", "")
            nested_keys = cleaned_key.split(".")
            values = extract_nested_value(data, nested_keys)
            if not values:
                validation_results.append(f"[FAIL] {key} : KEY NOT FOUND")
                continue
            for value in values:
                result = "NULL VALUE" if value is None else f"FOUND -> {value}"
                validation_results.append(f"[PASS] {key} : {result}")
        except Exception as error:
            validation_results.append(f"[ERROR] {key} : {error}")
    return "\n".join(validation_results)


def connect_to_server(keys, module_key, os_name, duration=None, interval=None, tag=None):

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

        def run_remote_cmd(cmd):
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode()   
            err = stderr.read().decode()
            return exit_status, out, err

        # 2. Create a folder
        folder_name = "profiler_run_dir"
        mkdir_cmd = f"mkdir -p {folder_name}" if os_name != "windows" else f"mkdir {folder_name}"
        status, out, err = run_remote_cmd(mkdir_cmd)
        if status != 0:
            raise RuntimeError(f"Failed to create directory: {err}")
            
        profile_url = get_profile_url(module_key, os_name)
        
        # 3. Download the tool (naming it pp or wp)
        tool_name = "pp" if module_key == "pp" else "wp"
        if os_name == "windows":
            download_cmd = f'powershell -Command "Invoke-WebRequest -Uri {profile_url} -OutFile {folder_name}\\{tool_name}.txt"'
        else:
            download_cmd = f'wget -O {folder_name}/{tool_name} {profile_url}'
            
        status, out, err = run_remote_cmd(download_cmd)
        if status != 0:
            raise RuntimeError(f"Failed to download tool on {os_name}:\n{err}")
            
        if os_name != "windows":
            run_remote_cmd(f"chmod +x {folder_name}/{tool_name}")
        
        # 4. Run the tool
        if module_key == "pp":
            if os_name == "windows":
                run_cmd = f".\\{folder_name}\\{tool_name}.txt --osip localhost > {folder_name}\\results.txt"
            else:
                run_cmd = f"./{folder_name}/{tool_name} --osip localhost > {folder_name}/results.txt"
        elif module_key == "wp":
            d_val = duration if duration else "60"
            i_val = interval if interval else "5"
            t_val = tag if tag else "default_tag"
            
            if os_name == "windows":
                run_cmd = f".\\{folder_name}\\{tool_name}.txt -w -d {d_val} -i {i_val} -t {t_val} > {folder_name}\\results.txt"
            else:
                run_cmd = f"./{folder_name}/{tool_name} -w -d {d_val} -i {i_val} -t {t_val} > {folder_name}/results.txt"
        else:
            if os_name == "windows":
                run_cmd = f"systeminfo > {folder_name}\\results.txt"
            else:
                run_cmd = f"uname -a > {folder_name}/results.txt"
            
        status, out, err = run_remote_cmd(run_cmd)
        if status != 0:
            raise RuntimeError(f"Failed to run tool on {os_name}:\n{err}")
        
        # 5. Make it into zip files ON THE REMOTE SERVER
        zip_file = f"{folder_name}.zip"
        if os_name == "windows":
            zip_cmd = f'powershell -Command "Compress-Archive -Path {folder_name} -DestinationPath {zip_file}"'
        else:
            zip_cmd = f"zip -r {zip_file} {folder_name}"
            
        _, stdout, _ = ssh.exec_command(zip_cmd)
        stdout.read() # Wait for completion
        
        # 6. Bring those data back to our local (using SFTP)
        sftp = ssh.open_sftp()
        local_zip_path = output_paths["non_sudo"] / f"{os_name}_results.zip"
        sftp.get(zip_file, str(local_zip_path))
        sftp.close()
        print(f"[INFO] Successfully brought data back to local: {local_zip_path}")
        
        # 7. Delete the folder and zip file on remote
        if os_name == "windows":
            delete_cmd = f"rmdir /s /q {folder_name} && del {zip_file}"
        else:
            delete_cmd = f"rm -rf {folder_name} {zip_file}"
            
        _, stdout, _ = ssh.exec_command(delete_cmd)
        stdout.read() # Wait for completion

    except paramiko.AuthenticationException:

        message = "Authentication Failed"

        print(f"\n[ERROR] {message}")

        log_error(message)

    except paramiko.SSHException as error:

        message = f"SSH Error : {error}"

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