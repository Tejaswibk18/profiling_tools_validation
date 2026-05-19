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


def run_linux_profiler(ssh, module_key, os_name, output_paths, duration=None, interval=None, tag=None):
    def run_remote_cmd(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode()   
        err = stderr.read().decode()
        return exit_status, out, err

    for mode in ["non_sudo", "sudo"]:
        # 2. Create a folder
        folder_name = f"profiler_run_dir_{mode}"
        status, out, err = run_remote_cmd(f"mkdir -p {folder_name}")
        if status != 0:
            print(f"[ERROR] Failed to create directory on {os_name} for {mode}: {err}")
            continue
            
        profile_url = get_profile_url(module_key, os_name)
        tool_name = "pp" if module_key == "pp" else "wp"
        download_cmd = f'wget --no-check-certificate -O {folder_name}/{tool_name} {profile_url}'
        
        status, out, err = run_remote_cmd(download_cmd)
        if status != 0:
            print(f"[ERROR] Failed to download tool on {os_name} for {mode} (Status {status}):\n{err}")
            ssh.exec_command(f"rm -rf {folder_name}")
            continue
            
        run_remote_cmd(f"chmod +x {folder_name}/{tool_name}")
        
        sudo_prefix = "sudo " if mode == "sudo" else ""
        
        if module_key == "pp":
            run_cmd = f"{sudo_prefix}./{folder_name}/{tool_name} --osip localhost > {folder_name}/results.txt"
        else:
            d_val = duration if duration else "60"
            i_val = interval if interval else "5"
            t_val = tag if tag else "default_tag"
            run_cmd = f"{sudo_prefix}./{folder_name}/{tool_name} -w -d {d_val} -i {i_val} -t {t_val} > {folder_name}/results.txt"
            
        status, out, err = run_remote_cmd(run_cmd)
        if status != 0:
            print(f"[ERROR] Failed to run tool on {os_name} for {mode} (Status {status}):\n{err}")
            ssh.exec_command(f"{sudo_prefix}rm -rf {folder_name}")
            continue
            
        zip_file = f"{folder_name}.zip"
        zip_cmd = f"{sudo_prefix}zip -r {zip_file} {folder_name}"
        
        status, out, err = run_remote_cmd(zip_cmd)
        if status != 0:
            print(f"[ERROR] Failed to zip results on {os_name} for {mode} (Status {status}):\n{err}")
            ssh.exec_command(f"{sudo_prefix}rm -rf {folder_name}")
            continue
            
        if mode == "sudo":
            run_remote_cmd(f"sudo chmod 644 {zip_file}")
            
        try:
            sftp = ssh.open_sftp()
            local_zip_path = output_paths[mode] / f"{os_name}_results.zip"
            sftp.get(zip_file, str(local_zip_path))
            sftp.close()
            print(f"[INFO] Successfully brought data back to local for {mode} ({os_name.upper()}): {local_zip_path}")
        except Exception as sftp_err:
            print(f"[ERROR] SFTP transfer failed for {mode} ({os_name.upper()}): {sftp_err}")
            
        run_remote_cmd(f"sudo rm -rf {folder_name} && rm -f {zip_file}")


def run_windows_profiler(ssh, module_key, os_name, output_paths, duration=None, interval=None, tag=None):
    def run_remote_cmd(cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode()   
        err = stderr.read().decode()
        return exit_status, out, err

    for mode in ["non_sudo", "sudo"]:
        # 2. Create a folder
        folder_name = f"profiler_run_dir_{mode}"
        status, out, err = run_remote_cmd(f"mkdir {folder_name}")
        if status != 0:
            print(f"[ERROR] Failed to create directory on {os_name} for {mode}: {err}")
            continue
            
        profile_url = get_profile_url(module_key, os_name)
        tool_name = "pp" if module_key == "pp" else "wp"
        download_cmd = f'powershell -Command "Invoke-WebRequest -Uri {profile_url} -OutFile {folder_name}\\{tool_name}.txt"'
        
        status, out, err = run_remote_cmd(download_cmd)
        if status != 0:
            print(f"[ERROR] Failed to download tool on {os_name} for {mode} (Status {status}):\n{err}")
            ssh.exec_command(f"rmdir /s /q {folder_name}")
            continue
            
        if module_key == "pp":
            if mode == "sudo":
                run_cmd = f"powershell -Command \"Start-Process -FilePath '.\\{folder_name}\\{tool_name}.txt' -ArgumentList '--osip localhost' -RedirectStandardOutput '{folder_name}\\results.txt' -Verb RunAs -Wait\""
            else:
                run_cmd = f".\\{folder_name}\\{tool_name}.txt --osip localhost > {folder_name}\\results.txt"
        else:
            d_val = duration if duration else "60"
            i_val = interval if interval else "5"
            t_val = tag if tag else "default_tag"
            if mode == "sudo":
                run_cmd = f"powershell -Command \"Start-Process -FilePath '.\\{folder_name}\\{tool_name}.txt' -ArgumentList '-w -d {d_val} -i {i_val} -t {t_val}' -RedirectStandardOutput '{folder_name}\\results.txt' -Verb RunAs -Wait\""
            else:
                run_cmd = f".\\{folder_name}\\{tool_name}.txt -w -d {d_val} -i {i_val} -t {t_val} > {folder_name}\\results.txt"
                
        status, out, err = run_remote_cmd(run_cmd)
        if status != 0:
            print(f"[ERROR] Failed to run tool on {os_name} for {mode} (Status {status}):\n{err}")
            ssh.exec_command(f"rmdir /s /q {folder_name}")
            continue
            
        zip_file = f"{folder_name}.zip"
        zip_cmd = f'powershell -Command "Compress-Archive -Path {folder_name} -DestinationPath {zip_file}"'
        
        status, out, err = run_remote_cmd(zip_cmd)
        if status != 0:
            print(f"[ERROR] Failed to zip results on {os_name} for {mode} (Status {status}):\n{err}")
            ssh.exec_command(f"rmdir /s /q {folder_name}")
            continue
            
        try:
            sftp = ssh.open_sftp()
            local_zip_path = output_paths[mode] / f"{os_name}_results.zip"
            sftp.get(zip_file, str(local_zip_path))
            sftp.close()
            print(f"[INFO] Successfully brought data back to local for {mode} ({os_name.upper()}): {local_zip_path}")
        except Exception as sftp_err:
            print(f"[ERROR] SFTP transfer failed for {mode} ({os_name.upper()}): {sftp_err}")
            
        run_remote_cmd(f"rmdir /s /q {folder_name} && del {zip_file}")


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

        if os_name == "windows":
            run_windows_profiler(ssh, module_key, os_name, output_paths, duration, interval, tag)
        else:
            run_linux_profiler(ssh, module_key, os_name, output_paths, duration, interval, tag)

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