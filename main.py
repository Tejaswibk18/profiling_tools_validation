import argparse
import configparser
import concurrent.futures
from services.ssh_service import connect_to_server


MODULES = {
    "-pp": "Platform Profiler",
    "-wp": "Workload Profiler",
    "-all": "Complete Execution"
}


def get_parser():
    parser = argparse.ArgumentParser(
        description="Infrastructure Profiling Framework"
    )

    parser.add_argument(
        "-pp", "--platformProfiler",
        action="store_true",
        dest="pp",
        help="Run Platform Profiler"
    )

    parser.add_argument(
        "-wp", "--workloadProfiler",
        action="store_true",
        dest="wp",
        help="Run Workload Profiler"
    )

    parser.add_argument(
        "-all", "--allModules",
        action="store_true",
        dest="all",
        help="Run All Modules"
    )

    return parser


def get_selected_modules(args):
    if getattr(args, "all"):
        return [(flag.lstrip("-"), name) for flag, name in MODULES.items() if flag != "-all"]
    
    return [
        (flag.lstrip("-"), name) for flag, name in MODULES.items()
        if flag != "-all" and getattr(args, flag.lstrip("-").replace("-", "_"))
    ]


def print_short_help():
    print("""usage: main.py [-h] [-pp] [-wp] [-all]

Infrastructure Profiling Framework

options:
  -h          show this help message and exit
  -pp         Run Platform Profiler
  -wp         Run Workload Profiler
  -all        Run All Modules""")

def print_long_help():
    print("""usage: main.py [--help] [--platformProfiler] [--workloadProfiler] [--allModules]

Infrastructure Profiling Framework

options:
  --help                show this help message and exit
  --platformProfiler    Run Platform Profiler
  --workloadProfiler    Run Workload Profiler
  --allModules          Run All Modules""")

def main():
    import sys
    if "-h" in sys.argv:
        print_short_help()
        return
    elif "--help" in sys.argv:
        print_long_help()
        return
        
    try:
        parser = get_parser()
        args = parser.parse_args()

        modules_to_run = get_selected_modules(args)

        if not modules_to_run:
            parser.print_help()
            return

        module_names = ", ".join([name for _, name in modules_to_run])
        print(f"\n[INFO] Running : {module_names}")

        keys = []

        config = configparser.ConfigParser()
        config.read("server_details.ini")
        configured_oses = config.sections()

        if not configured_oses:
            print("\n[ERROR] No valid OS configured in server_details.ini")
            return

        for module_key, module_name in modules_to_run:
            print(f"\n[INFO] Starting concurrent execution for {module_name} on target OSes...")
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(connect_to_server, keys, module_key, os_name): os_name
                    for os_name in configured_oses
                }
                
                for future in concurrent.futures.as_completed(futures):
                    os_name = futures[future]
                    try:
                        future.result()
                        print(f"\n[INFO] Completed {module_name} for OS: {os_name.upper()}")
                    except Exception as exc:
                        print(f"\n[ERROR] {module_name} for {os_name.upper()} failed: {exc}")

            # Post-execution cleanup: Unzip files and delete redundant archives
            import os
            import zipfile
            import json
            import shutil
            
            for os_name in configured_oses:
                for mode in ["without_sudo", "with_sudo"]:
                    local_dir = f"outputs/{module_key}/{os_name}/{mode}"
                    zip_path = os.path.join(local_dir, f"{os_name}_results.zip")
                    
                    if os.path.exists(zip_path):
                        extract_dir = os.path.join(local_dir, f"{os_name}_extracted")
                        try:
                            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                                zip_ref.extractall(extract_dir)
                            
                            # Move all files directly to local_dir
                            for root, dirs, files in os.walk(extract_dir):
                                for f in files:
                                    src_path = os.path.join(root, f)
                                    dst_path = os.path.join(local_dir, f)
                                    # Overwrite if exists, or just move
                                    if os.path.exists(dst_path):
                                        os.remove(dst_path)
                                    shutil.move(src_path, dst_path)
                            
                            # Clean up zip and temp extract dir
                            shutil.rmtree(extract_dir)
                            os.remove(zip_path)
                            print(f"[INFO] Extracted results to {local_dir} and cleaned up archive.")
                            
                            # Parse results.txt or details text into nested JSON
                            results_txt_path = os.path.join(local_dir, "results.txt")
                            details_txt_path = os.path.join(local_dir, f"{os_name}_details.txt")
                            src_text_file = results_txt_path if os.path.exists(results_txt_path) else (details_txt_path if os.path.exists(details_txt_path) else None)
                            
                            if src_text_file:
                                try:
                                    with open(src_text_file, "r", encoding="utf-8") as rf:
                                        content = rf.read().strip()
                                        
                                    parsed_data = {}
                                    for line in content.splitlines():
                                        line = line.strip()
                                        if not line or line.startswith('#') or line.startswith('//'):
                                            continue
                                            
                                        sep = '=' if '=' in line else (':' if ':' in line else None)
                                        if sep:
                                            k_part, v_part = line.split(sep, 1)
                                            k_part = k_part.strip().strip('[]')
                                            v_part = v_part.strip().strip('"\'')
                                            
                                            parts = k_part.split('.')
                                            curr = parsed_data
                                            for part in parts[:-1]:
                                                part = part.strip()
                                                if part not in curr or not isinstance(curr[part], dict):
                                                    curr[part] = {}
                                                curr = curr[part]
                                                
                                            val_lower = v_part.lower()
                                            if val_lower == "true":
                                                val = True
                                            elif val_lower == "false":
                                                val = False
                                            elif val_lower in ("null", "none"):
                                                val = None
                                            else:
                                                try:
                                                    val = float(v_part) if '.' in v_part else int(v_part)
                                                except ValueError:
                                                    val = v_part
                                                    
                                            curr[parts[-1].strip()] = val
                                            
                                    json_out_path = os.path.join(local_dir, "results.json")
                                    pp_json_out_path = os.path.join(local_dir, "platformprofiler.json")
                                    with open(json_out_path, "w", encoding="utf-8") as jf:
                                        json.dump(parsed_data, jf, indent=4)
                                    with open(pp_json_out_path, "w", encoding="utf-8") as jf:
                                        json.dump(parsed_data, jf, indent=4)
                                    print(f"[INFO] Successfully converted output text to JSON: {pp_json_out_path}")
                                except Exception as json_err:
                                    print(f"[ERROR] Failed to convert results to JSON: {json_err}")
                        except Exception as e:
                            print(f"[ERROR] Failed to extract archive for {os_name.upper()} ({mode}): {e}")

            # New Step: Ask for keys and Validate (Only for Platform Profiler)
            if module_key == "pp":
                from services.ssh_service import validate_keys
                
                keys_input = input("\nEnter key(s) to check in JSON (comma separated if multiple): ")
                keys_to_check = [k.strip() for k in keys_input.split(",") if k.strip()]
                
                if keys_to_check:
                    for os_name in configured_oses:
                        for mode in ["without_sudo", "with_sudo"]:
                            local_dir = f"outputs/{module_key}/{os_name}/{mode}"
                            
                            # Find the JSON file directly in local_dir
                            json_file = None
                            if os.path.exists(local_dir):
                                for f in os.listdir(local_dir):
                                    if f.endswith('.json'):
                                        json_file = os.path.join(local_dir, f)
                                        break
                                        
                            if json_file:
                                try:
                                    with open(json_file, 'r') as jf:
                                        data = json.load(jf)
                                    
                                    validation_output = validate_keys(data, keys_to_check)
                                    print(f"\n[INFO] Validation results for {os_name.upper()} ({mode}):")
                                    print(validation_output)
                                    
                                    # Save validation results
                                    val_out_path = os.path.join(local_dir, "validation_results.txt")
                                    with open(val_out_path, "w") as f:
                                        f.write(validation_output)
                                    print(f"[INFO] Saved validation results to {val_out_path}")
                                except Exception as e:
                                    print(f"[ERROR] Failed to validate keys for {os_name.upper()} ({mode}): {e}")
                            else:
                                print(f"[WARN] No JSON file found in {local_dir} to validate keys.")

            from services.report_service import generate_html_report
            generate_html_report(module_key)

    except KeyboardInterrupt:
        print("\n[INFO] Execution interrupted by user")

    except Exception as error:
        print(f"\n[ERROR] {error}")


if __name__ == "__main__":
    main()