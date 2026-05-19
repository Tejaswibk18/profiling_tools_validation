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

            # New Step: Unzip and Validate Keys (Only for Platform Profiler)
            if module_key == "pp":
                import os
                import zipfile
                import json
                from services.ssh_service import validate_keys
                
                keys_input = input("\nEnter key(s) to check in JSON (comma separated if multiple): ")
                keys_to_check = [k.strip() for k in keys_input.split(",") if k.strip()]
                
                if keys_to_check:
                    for os_name in configured_oses:
                        for mode in ["without_sudo", "with_sudo"]:
                            local_dir = f"outputs/{module_key}/{os_name}/{mode}"
                            zip_path = os.path.join(local_dir, f"{os_name}_results.zip")
                            
                            if os.path.exists(zip_path):
                                extract_dir = os.path.join(local_dir, f"{os_name}_extracted")
                                try:
                                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                                        zip_ref.extractall(extract_dir)
                                    
                                    # Find the JSON file
                                    json_file = None
                                    for root, dirs, files in os.walk(extract_dir):
                                        for f in files:
                                            if f.endswith('.json'):
                                                json_file = os.path.join(root, f)
                                                break
                                        if json_file:
                                            break
                                            
                                    if json_file:
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
                                    else:
                                        print(f"[WARN] No JSON file found in zip for {os_name.upper()} ({mode})")
                                except Exception as e:
                                    print(f"[ERROR] Failed to process zip for {os_name.upper()} ({mode}): {e}")
                            else:
                                print(f"[WARN] Zip file not found for {os_name.upper()} ({mode}): {zip_path}")

            from services.report_service import generate_html_report
            generate_html_report(module_key)

            from services.zip_service import archive_outputs
            archive_outputs(module_key)

    except KeyboardInterrupt:
        print("\n[INFO] Execution interrupted by user")

    except Exception as error:
        print(f"\n[ERROR] {error}")


if __name__ == "__main__":
    main()