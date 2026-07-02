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


def run_linux_profiler(
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

    run_remote_cmd(f"mkdir -p {base_remote_dir}/{module_key}")

    server = load_server_details(server_section_name)
    password = server.get("password", "")

    for mode in ["non_sudo", "sudo"]:

        mode_key = mode
        mode_suffix = "nonsudo" if mode == "non_sudo" else "sudo"

        prefix = (
            "platform_profiler"
            if module_key == "pp"
            else "workload_profiler"
        )

        folder_name = (
            f"{prefix}_{hostname}_{timestamp}_{mode_suffix}"
        )

        full_folder_path = (
            f"{base_remote_dir}/{module_key}/{folder_name}"
        )

        tool_name = (
            "pp"
            if module_key == "pp"
            else "wp"
        )

        profile_url = get_profile_url(module_key, os_type)

        sudo_prefix = ""

        if mode == "sudo":
            sudo_prefix = f"echo '{password}' | sudo -S "

        # Create folder
        status, out, err = run_remote_cmd(
            f"mkdir -p {full_folder_path}"
        )

        if status != 0:
            print(f"[ERROR] Folder creation failed: {err}")
            continue

        # Download binary
        download_cmd = (
            f"wget --no-check-certificate "
            f"-O {full_folder_path}/{tool_name} "
            f"{profile_url}"
        )

        status, out, err = run_remote_cmd(download_cmd)

        if status != 0:
            print(f"[ERROR] Download failed:\n{err}")
            continue

        run_remote_cmd(
            f"chmod +x {full_folder_path}/{tool_name}"
        )

        # IMPORTANT FIX
        if module_key == "pp":

            run_cmd = f"""
            cd {base_remote_dir}/{module_key} &&
            {sudo_prefix}./{folder_name}/{tool_name} \
            --osip localhost \
            --output {folder_name} \
            > {folder_name}/results.txt 2>&1
            """

        else:

            d_val = duration or "60"
            i_val = interval or "5"
            t_val = tag or "default_tag"

            run_cmd = f"""
            cd {base_remote_dir}/{module_key} &&
            {sudo_prefix}./{folder_name}/{tool_name} \
            -w \
            -d {d_val} \
            -i {i_val} \
            -t {t_val} \
            --output {folder_name} \
            > {folder_name}/results.txt 2>&1
            """

        status, out, err = run_remote_cmd(run_cmd)

        if status != 0:
            print(f"[ERROR] Execution failed:\n{err}")
            continue

        # Remove binary
        run_remote_cmd(
            f"{sudo_prefix}rm -f {full_folder_path}/{tool_name}"
        )

        # Zip
        zip_file = f"{full_folder_path}.zip"

        zip_cmd = f"""
        cd {base_remote_dir}/{module_key} &&
        {sudo_prefix}zip -r {folder_name}.zip {folder_name}
        """

        status, out, err = run_remote_cmd(zip_cmd)

        if status != 0:
            print(f"[ERROR] Zip failed:\n{err}")
            continue

        if mode == "sudo":
            run_remote_cmd(
                f"{sudo_prefix}chmod 644 {zip_file}"
            )

        # Transfer
        try:
            sftp = ssh.open_sftp()

            local_dir = output_paths[mode_key]

            local_zip_path = (
                local_dir / f"{folder_name}.zip"
            )

            sftp.get(zip_file, str(local_zip_path))

            sftp.close()

            print(
                f"[INFO] Downloaded: {local_zip_path}"
            )

        except Exception as sftp_err:
            print(f"[ERROR] SFTP failed: {sftp_err}")

        # Cleanup
        run_remote_cmd(
            f"{sudo_prefix}rm -rf {full_folder_path}"
        )

        run_remote_cmd(
            f"{sudo_prefix}rm -f {zip_file}"
        )


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

    hostname = get_remote_hostname(
        ssh,
        server_section_name
    )

    import datetime

    timestamp = datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    base_remote_dir = "profiling_tools_validation"

    run_remote_cmd(
        f'powershell -Command "'
        f'New-Item -ItemType Directory '
        f'-Force -Path {base_remote_dir}\\{module_key}'
        f'"'
    )

    for mode in ["non_sudo", "sudo"]:

        mode_key = mode

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

        tool_name = (
            "pp"
            if module_key == "pp"
            else "wp"
        )

        profile_url = get_profile_url(
            module_key,
            os_type
        )

        # Create folder
        create_cmd = (
            f'powershell -Command "'
            f'New-Item -ItemType Directory '
            f'-Force '
            f'-Path \'{full_folder_path}\''
            f'"'
        )

        status, out, err = run_remote_cmd(create_cmd)

        if status != 0:
            print(f"[ERROR] Folder creation failed:\n{err}")
            continue

        # Download
        download_cmd = f'''
        powershell -Command "
        [Net.ServicePointManager]::SecurityProtocol =
        [Net.SecurityProtocolType]::Tls12;

        Invoke-WebRequest
        -Uri '{profile_url}'
        -OutFile '{full_folder_path}\\{tool_name}.exe'
        "
        '''

        status, out, err = run_remote_cmd(download_cmd)

        if status != 0:
            print(f"[ERROR] Download failed:\n{err}")
            continue

        # IMPORTANT FIX
        if module_key == "pp":

            args = (
                f'--osip localhost '
                f'--output "{folder_name}"'
            )

        else:

            d_val = duration or "60"
            i_val = interval or "5"
            t_val = tag or "default_tag"

            args = (
                f'-w '
                f'-d {d_val} '
                f'-i {i_val} '
                f'-t {t_val} '
                f'--output "{folder_name}"'
            )

        # Execute
        run_cmd = f'''
        powershell -Command "
        cd '{base_remote_dir}\\{module_key}';

        .\\{folder_name}\\{tool_name}.exe {args}
        *> .\\{folder_name}\\results.txt
        "
        '''

        status, out, err = run_remote_cmd(run_cmd)

        if status != 0:
            print(f"[ERROR] Execution failed:\n{err}")
            continue

        # Remove exe
        run_remote_cmd(
            f'powershell -Command "'
            f'Remove-Item -Force '
            f'\'{full_folder_path}\\{tool_name}.exe\''
            f'"'
        )

        # Zip
        zip_file = f"{full_folder_path}.zip"

        zip_cmd = f'''
        powershell -Command "
        Compress-Archive
        -Path '{full_folder_path}'
        -DestinationPath '{zip_file}'
        -Force
        "
        '''

        status, out, err = run_remote_cmd(zip_cmd)

        if status != 0:
            print(f"[ERROR] Zip failed:\n{err}")
            continue

        # Transfer
        try:

            sftp = ssh.open_sftp()

            local_dir = output_paths[mode_key]

            local_zip_path = (
                local_dir / f"{folder_name}.zip"
            )

            sftp.get(
                zip_file,
                str(local_zip_path)
            )

            sftp.close()

            print(
                f"[INFO] Downloaded: {local_zip_path}"
            )

        except Exception as sftp_err:

            print(f"[ERROR] SFTP failed: {sftp_err}")

        # Cleanup
        run_remote_cmd(
            f'powershell -Command "'
            f'Remove-Item -Recurse -Force '
            f'\'{full_folder_path}\''
            f'"'
        )

        run_remote_cmd(
            f'powershell -Command "'
            f'Remove-Item -Force '
            f'\'{zip_file}\''
            f'"'
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

        try:
            ssh.connect(**connect_args)
        except paramiko.ssh_exception.BadAuthenticationType as e:
            if "keyboard-interactive" in e.allowed_types and server.get("password"):
                print(f"[INFO] Password authentication rejected. Attempting keyboard-interactive fallback for {server_section_name}...")
                transport = ssh.get_transport()
                if transport:
                    try:
                        transport.auth_interactive_dumb(
                            server["username"],
                            handler=lambda title, instructions, prompt_list: [server["password"]]
                        )
                        print(f"[INFO] Keyboard-interactive authentication successful for {server_section_name}!")
                    except Exception as interactive_err:
                        raise paramiko.AuthenticationException(
                            f"Keyboard-interactive fallback failed: {interactive_err}"
                        ) from e
                else:
                    raise e
            else:
                raise e

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