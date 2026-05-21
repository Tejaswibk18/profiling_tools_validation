import paramiko
import configparser
from pathlib import Path

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


def get_os_type(section_name, server_details):
    """
    Resolve the OS type (linux, windows, arm) for a given server configuration section.
    """
    os_val = server_details.get("os", "").lower()
    if os_val in ["linux", "windows", "arm"]:
        return os_val
        
    sec_lower = section_name.lower()
    if "linux" in sec_lower:
        return "linux"
    if "arm" in sec_lower:
        return "arm"
    if "windows" in sec_lower:
        return "windows"
        
    return "linux"


def get_remote_hostname(ssh, default_name):
    """
    Retrieves the hostname of the remote server via SSH, falling back to a default name on failure.
    """
    try:
        stdin, stdout, stderr = ssh.exec_command("hostname")
        name = stdout.read().decode().strip()
        if name:
            import re
            # Sanitize hostname to keep only alphanumeric characters, hyphens and underscores
            name = re.sub(r'[^a-zA-Z0-9_\-]', '', name)
            return name
    except Exception:
        pass
    return default_name


def run_linux_profiler(ssh, module_key, os_type, server_section_name, output_paths, duration=None, interval=None, tag=None):
    def run_remote_cmd(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode()   
        err = stderr.read().decode()
        return exit_status, out, err

    hostname = get_remote_hostname(ssh, server_section_name)
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    base_remote_dir = "profiling_tools_validation"
    run_remote_cmd(f"mkdir -p {base_remote_dir}/{module_key}")

    for mode in ["non_sudo", "sudo"]:
        mode_key = "non_sudo" if mode == "non_sudo" else "sudo"
        mode_suffix = "nonsudo" if mode == "non_sudo" else "sudo"
        
        prefix = "platform_profiler" if module_key == "pp" else "workload_profiler"
        folder_name = f"{prefix}_{hostname}_{timestamp}_{mode_suffix}"
        full_folder_path = f"{base_remote_dir}/{module_key}/{folder_name}"

        # Create folder
        status, out, err = run_remote_cmd(f"mkdir -p {full_folder_path}")
        if status != 0:
            print(f"[ERROR] Failed to create directory on {server_section_name} ({os_type}) for {mode}: {err}")
            continue
            
        profile_url = get_profile_url(module_key, os_type)
        tool_name = "pp" if module_key == "pp" else "wp"
        
        # Download tool
        download_cmd = f'wget --no-check-certificate -O {full_folder_path}/{tool_name} {profile_url}'
        status, out, err = run_remote_cmd(download_cmd)
        if status != 0:
            print(f"[ERROR] Failed to download tool on {server_section_name} ({os_type}) for {mode} (Status {status}):\n{err}")
            run_remote_cmd(f"rm -rf {full_folder_path}")
            continue
            
        # Make executable
        run_remote_cmd(f"chmod +x {full_folder_path}/{tool_name}")
        
        server = load_server_details(server_section_name)
        password = server.get("password", "")

        if mode == "sudo":
            sudo_prefix = f"echo '{password}' | sudo -S "
        else:
            sudo_prefix = ""
        
        # Run tool
        if module_key == "pp":
            run_cmd = f"{sudo_prefix}./{full_folder_path}/{tool_name} --osip localhost > {full_folder_path}/results.txt"
        else:
            d_val = duration if duration else "60"
            i_val = interval if interval else "5"
            t_val = tag if tag else "default_tag"
            run_cmd = f"{sudo_prefix}./{full_folder_path}/{tool_name} -w -d {d_val} -i {i_val} -t {t_val} > {full_folder_path}/results.txt"
            
        status, out, err = run_remote_cmd(run_cmd)
        if status != 0:
            print(f"[ERROR] Failed to run tool on {server_section_name} ({os_type}) for {mode} (Status {status}):\n{err}")
            run_remote_cmd(f"{sudo_prefix}rm -rf {full_folder_path}")
            continue
            
        # Delete the binary to save transfer size and keep the folder clean
        run_remote_cmd(f"{sudo_prefix}rm -f {full_folder_path}/{tool_name}")
            
        # Zip folder
        zip_file = f"{full_folder_path}.zip"
        zip_cmd = f"cd {base_remote_dir}/{module_key} && {sudo_prefix}zip -r {folder_name}.zip {folder_name}"
        
        status, out, err = run_remote_cmd(zip_cmd)
        if status != 0:
            print(f"[ERROR] Failed to zip results on {server_section_name} ({os_type}) for {mode} (Status {status}):\n{err}")
            run_remote_cmd(f"{sudo_prefix}rm -rf {full_folder_path}")
            continue
            
        if mode == "sudo":
            run_remote_cmd(f"sudo chmod 644 {zip_file}")
            
        try:
            sftp = ssh.open_sftp()
            local_dir = output_paths[mode_key]
            local_zip_path = local_dir / f"{folder_name}.zip"
            sftp.get(zip_file, str(local_zip_path))
            sftp.close()
            print(f"[INFO] Successfully brought data back to local for {mode} ({server_section_name.upper()}): {local_zip_path}")
        except Exception as sftp_err:
            print(f"[ERROR] SFTP transfer failed for {mode} ({server_section_name.upper()}): {sftp_err}")
            
        run_remote_cmd(f"sudo rm -rf {full_folder_path} && sudo rm -f {zip_file}")


def run_windows_profiler(
    ssh,
    module_key,
    os_type,
    server_section_name,
    output_paths,
    duration=None,
    interval=None,
    tag=None
):
    def run_remote_cmd(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        return exit_status, out, err

    hostname = get_remote_hostname(ssh, server_section_name)

    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    base_remote_dir = "profiling_tools_validation"

    # Create base directory
    run_remote_cmd(
        f'powershell -Command '
        f'"New-Item -ItemType Directory -Force '
        f'-Path \'{base_remote_dir}\\{module_key}\'"'
    )

    for mode in ["non_sudo", "sudo"]:

        mode_key = "non_sudo" if mode == "non_sudo" else "sudo"
        mode_suffix = (
            "normal_user"
            if mode == "non_sudo"
            else "administrator"
        )

        prefix = (
            "platform_profiler"
            if module_key == "pp"
            else "workload_profiler"
        )

        folder_name = (
            f"{prefix}_{hostname}_{timestamp}_{mode_suffix}"
        )

        full_folder_path = (
            f"{base_remote_dir}\\{module_key}\\{folder_name}"
        )

        # Create working directory
        create_cmd = (
            f'powershell -Command '
            f'"New-Item -ItemType Directory -Force '
            f'-Path \'{full_folder_path}\'"'
        )

        status, out, err = run_remote_cmd(create_cmd)

        if status != 0:
            print(
                f"[ERROR] Failed to create directory "
                f"on {server_section_name} ({os_type}) "
                f"for {mode}: {err}"
            )
            continue

        profile_url = get_profile_url(module_key, os_type)

        tool_name = (
            "pp"
            if module_key == "pp"
            else "wp"
        )

        remote_exe = (
            f"{full_folder_path}\\{tool_name}.exe"
        )

        # Download using curl
        download_cmd = (
            f'cmd /c "curl.exe -k -L '
            f'"{profile_url}" '
            f'-o "{remote_exe}""'
        )

        status, out, err = run_remote_cmd(download_cmd)

        if status != 0:
            print(
                f"[ERROR] Failed to download tool "
                f"on {server_section_name} ({os_type}) "
                f"for {mode} (Status {status}):\n"
                f"STDOUT:\n{out}\nSTDERR:\n{err}"
            )

            run_remote_cmd(
                f'powershell -Command '
                f'"Remove-Item -Recurse -Force '
                f'\'{full_folder_path}\'"'
            )

            continue

        # Validate exe exists
        check_cmd = (
            f'powershell -Command '
            f'"Test-Path \'{remote_exe}\'"'
        )

        _, out, _ = run_remote_cmd(check_cmd)

        if "True" not in out:
            print(
                f"[ERROR] Downloaded executable not found "
                f"for {mode}"
            )
            continue

        results_file = (
            f"{full_folder_path}\\results.txt"
        )

        # Build arguments
        if module_key == "pp":
            arguments = (
                f'--osip localhost '
                f'--output "{full_folder_path}"'
            )
        else:
            d_val = duration if duration else "60"
            i_val = interval if interval else "5"
            t_val = tag if tag else "default_tag"

            arguments = (
                f'-w -d {d_val} '
                f'-i {i_val} '
                f'-t {t_val}'
            )

        # NON-SUDO
        if mode == "non_sudo":

            run_cmd = (
                f'powershell -Command '
                f'"& \'{remote_exe}\' '
                f'{arguments} '
                f'> \'{results_file}\' 2>&1"'
            )

        # SUDO / ADMIN MODE
        else:

            # IMPORTANT:
            # Cannot use RedirectStandardOutput with RunAs
            # So output goes directly to profiler output folder

            run_cmd = (
                f'powershell -Command '
                f'"Start-Process '
                f'-FilePath \'{remote_exe}\' '
                f'-ArgumentList \'{arguments}\' '
                f'-Verb RunAs '
                f'-Wait"'
            )

        status, out, err = run_remote_cmd(run_cmd)

        if status != 0:
            print(
                f"[ERROR] Failed to run tool "
                f"on {server_section_name} ({os_type}) "
                f"for {mode} (Status {status}):\n"
                f"STDOUT:\n{out}\nSTDERR:\n{err}"
            )

            run_remote_cmd(
                f'powershell -Command '
                f'"Remove-Item -Recurse -Force '
                f'\'{full_folder_path}\'"'
            )

            continue

        # Remove executable
        run_remote_cmd(
            f'powershell -Command '
            f'"Remove-Item -Force '
            f'\'{remote_exe}\'"'
        )

        # Zip results
        zip_file = f"{full_folder_path}.zip"

        zip_cmd = (
            f'powershell -Command '
            f'"Compress-Archive '
            f'-Path \'{full_folder_path}\' '
            f'-DestinationPath \'{zip_file}\' '
            f'-Force"'
        )

        status, out, err = run_remote_cmd(zip_cmd)

        if status != 0:
            print(
                f"[ERROR] Failed to zip results "
                f"on {server_section_name} ({os_type}) "
                f"for {mode} (Status {status}):\n"
                f"STDOUT:\n{out}\nSTDERR:\n{err}"
            )

            continue

        # Transfer zip
        try:

            sftp = ssh.open_sftp()

            local_dir = output_paths[mode_key]

            local_zip_path = (
                local_dir / f"{folder_name}.zip"
            )

            sftp.get(zip_file, str(local_zip_path))

            sftp.close()

            print(
                f"[INFO] Successfully brought "
                f"data back to local for {mode} "
                f"({server_section_name.upper()}): "
                f"{local_zip_path}"
            )

        except Exception as sftp_err:

            print(
                f"[ERROR] SFTP transfer failed "
                f"for {mode} "
                f"({server_section_name.upper()}): "
                f"{sftp_err}"
            )

        # Cleanup
        run_remote_cmd(
            f'powershell -Command '
            f'"Remove-Item -Recurse -Force '
            f'\'{full_folder_path}\'"'
        )

        run_remote_cmd(
            f'powershell -Command '
            f'"Remove-Item -Force '
            f'\'{zip_file}\'"'
        )


def _write_connection_error(module_key, os_type, message):
    """
    Writes a connection_error.txt into the outputs/<module_key>/<os_type>/ directory
    so the report generator can display failed environments even when no profiling ran.
    """
    try:
        error_dir = Path("outputs") / module_key / os_type.lower()
        error_dir.mkdir(parents=True, exist_ok=True)
        with open(error_dir / "connection_error.txt", "w", encoding="utf-8") as f:
            f.write(message)
    except Exception:
        pass


def connect_to_server(keys, module_key, server_section_name, duration=None, interval=None, tag=None):
    server = load_server_details(server_section_name)
    os_type = get_os_type(server_section_name, server)

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
            f"\n[INFO] SSH Connection Successful to {server_section_name.upper()} ({os_type.upper()})"
        )

        output_paths = create_output_folders(module_key, os_type, server_section_name)

        if os_type == "windows":
            run_windows_profiler(ssh, module_key, os_type, server_section_name, output_paths, duration, interval, tag)
        else:
            run_linux_profiler(ssh, module_key, os_type, server_section_name, output_paths, duration, interval, tag)

    except paramiko.AuthenticationException:
        message = f"Authentication Failed for {server_section_name}"
        print(f"\n[ERROR] {message}")
        log_error(message)
        _write_connection_error(module_key, os_type, message)

    except paramiko.SSHException as error:
        message = f"SSH Error for {server_section_name}: {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)
        _write_connection_error(module_key, os_type, message)

    except ValueError as error:
        message = f"Config Error for {server_section_name}: {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)

    except Exception as error:
        message = f"Error for {server_section_name}: {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)
        _write_connection_error(module_key, os_type, message)

    finally:
        ssh.close()
        print(
            f"\n[INFO] SSH Connection Closed to {server_section_name.upper()}"
        )