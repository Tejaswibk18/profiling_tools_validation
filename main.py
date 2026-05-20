import argparse
import configparser
import concurrent.futures
import datetime
from pathlib import Path
import os
import sys
import zipfile
import shutil
import json
import unittest

from services.ssh_service import connect_to_server, get_os_type, load_server_details, validate_keys
from services.config_service import load_config
from services.report_service import generate_html_report

MODULES = {
    "-pp": "Platform Profiler",
    "-wp": "Workload Profiler",
    "-a": "Complete Execution"
}


class ProfilerTestResult(unittest.TestResult):
    """
    Custom test result collector that stores passes and failures/errors
    so we can compile them into the final environment logs and HTML reports.
    """
    def __init__(self):
        super().__init__()
        self.passed_tests = []
        self.failed_tests = []
        
    def addSuccess(self, test):
        super().addSuccess(test)
        test_name = test.id().split('.')[-1]
        self.passed_tests.append(test_name)
        
    def addFailure(self, test, err):
        super().addFailure(test, err)
        test_name = test.id().split('.')[-1]
        msg = str(err[1]).strip()
        self.failed_tests.append((test_name, msg))
        
    def addError(self, test, err):
        super().addError(test, err)
        test_name = test.id().split('.')[-1]
        msg = str(err[1]).strip()
        self.failed_tests.append((test_name, msg))


def get_parser():
    parser = argparse.ArgumentParser(
        description="Infrastructure Profiling Framework",
        add_help=False
    )

    parser.add_argument(
        "-h",
        action="store_true",
        dest="short_help",
        help="Show short help message"
    )

    parser.add_argument(
        "--help",
        action="store_true",
        dest="long_help",
        help="Show long help message"
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
        "-a", "--all",
        action="store_true",
        dest="all",
        help="Run All Modules"
    )

    return parser


def print_short_help():
    print("""usage: main.py [-h] [-pp] [-wp] [-a]

Infrastructure Profiling Framework

options:
  -h          show this help message and exit
  -pp         Run Platform Profiler
  -wp         Run Workload Profiler
  -a          Run All Modules""")


def print_long_help():
    print("""usage: main.py [--help] [--platformProfiler] [--workloadProfiler] [--all]

Infrastructure Profiling Framework

options:
  --help                show this help message and exit
  --platformProfiler    Run Platform Profiler
  --workloadProfiler    Run Workload Profiler
  --all                 Run All Modules""")


def get_configured_oses(module_key):
    """
    Reads config.ini to check which target OSes have active tool URLs configured.
    """
    config = load_config()
    section_map = {
        "pp": "platform_profiler",
        "wp": "workload_profiler"
    }
    section = section_map.get(module_key, "platform_profiler")
    if not config.has_section(section):
        return []
    
    oses = []
    for option in config.options(section):
        val = config.get(section, option, fallback="").strip()
        if val:
            oses.append(option.lower())
    return oses


def parse_txt_to_json(txt_file_path, json_file_path):
    """
    Parses flat key-value results.txt or details.txt into standard nested JSON format.
    """
    try:
        with open(txt_file_path, "r", encoding="utf-8") as rf:
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
                
        with open(json_file_path, "w", encoding="utf-8") as jf:
            json.dump(parsed_data, jf, indent=4)
        print(f"[INFO] Successfully converted output text to JSON: {json_file_path}")
        return parsed_data
    except Exception as json_err:
        print(f"[ERROR] Failed to convert results to JSON for {txt_file_path}: {json_err}")
        return None


def main():
    # Handle help custom formatting
    if "-h" in sys.argv:
        print_short_help()
        return
    elif "--help" in sys.argv:
        print_long_help()
        return
        
    try:
        parser = get_parser()
        args = parser.parse_args()

        # Determine which modules to execute
        modules_to_run = []
        if args.all:
            modules_to_run = [("pp", "Platform Profiler"), ("wp", "Workload Profiler")]
        else:
            if args.pp:
                modules_to_run.append(("pp", "Platform Profiler"))
            if args.wp:
                modules_to_run.append(("wp", "Workload Profiler"))

        if not modules_to_run:
            print_short_help()
            return

        # 1. Prompts for keys if PP is involved (pp or all modules)
        keys_to_check = []
        if args.pp or args.all:
            keys_input = input("\nEnter key(s) to check in JSON (e.g. [Summary.Server.Model], comma separated if multiple): ")
            keys_to_check = [k.strip() for k in keys_input.split(",") if k.strip()]

        # 2. Prompts for duration/interval if WP is involved (wp or all modules)
        duration = None
        interval = None
        if args.wp or args.all:
            dur_input = input("\nEnter duration to run Workload Profiler (seconds) [default: 60]: ").strip()
            int_input = input("Enter interval to run Workload Profiler (seconds) [default: 5]: ").strip()
            duration = dur_input if dur_input else "60"
            interval = int_input if int_input else "5"

        # Load server details ini configuration
        server_details_config = configparser.ConfigParser()
        server_details_config.read("server_details.ini")
        all_server_sections = server_details_config.sections()

        if not all_server_sections:
            print("\n[ERROR] No valid servers configured in server_details.ini")
            return

        # Connect and run profiling concurrently
        print(f"\n[INFO] Initializing concurrent connections for: {', '.join([name for _, name in modules_to_run])}")
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {}
            for module_key, module_name in modules_to_run:
                configured_oses = get_configured_oses(module_key)
                
                for section_name in all_server_sections:
                    server_details = load_server_details(section_name)
                    os_type = get_os_type(section_name, server_details)
                    
                    if os_type in configured_oses:
                        print(f"[INFO] Queueing profiling task for {module_name} on target server: {section_name.upper()} ({os_type.upper()})")
                        future = executor.submit(
                            connect_to_server,
                            keys_to_check,
                            module_key,
                            section_name,
                            duration,
                            interval
                        )
                        futures[future] = (module_key, module_name, section_name)
                    else:
                        print(f"[INFO] Skipping {module_name} on {section_name.upper()} because {os_type.upper()} is not enabled in config.ini")
            
            for future in concurrent.futures.as_completed(futures):
                module_key, module_name, section_name = futures[future]
                try:
                    future.result()
                    print(f"[SUCCESS] Completed concurrent profiling execution for {module_name} on {section_name.upper()}")
                except Exception as exc:
                    print(f"[ERROR] Concurrent task failed for {module_name} on {section_name.upper()}: {exc}")

        # Post-execution cleanup: recursively find downloaded archives, extract them, and organize
        print("\n[INFO] Starting local post-processing of downloaded archives...")
        outputs_dir = Path("outputs")
        if outputs_dir.exists():
            for zip_path in list(outputs_dir.glob("**/*.zip")):
                local_dir = zip_path.parent
                print(f"[INFO] Extracting results archive: {zip_path.name} to {local_dir}")
                
                temp_extract_dir = local_dir / "temp_extract"
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_extract_dir)
                    
                    # Flatten the extraction: move files from temp_extract_dir directly to local_dir
                    for root, dirs, files in os.walk(temp_extract_dir):
                        for f in files:
                            src_file = Path(root) / f
                            dst_file = local_dir / f
                            if dst_file.exists():
                                dst_file.unlink()
                            shutil.move(str(src_file), str(dst_file))
                    
                    # Clean up temporary files
                    shutil.rmtree(temp_extract_dir)
                    zip_path.unlink()
                    print(f"[INFO] Finished extraction and cleaned up {zip_path.name}")
                    
                except Exception as e:
                    print(f"[ERROR] Failed to extract archive {zip_path}: {e}")
                    if temp_extract_dir.exists():
                        shutil.rmtree(temp_extract_dir)
                    continue

        # Parse text output to JSON for PP modules and run automated unittest suite
        pp_outputs_dir = Path("outputs/pp")
        if pp_outputs_dir.exists():
            from test_cases.pp.test_pp_json import TestPlatformProfilerJson

            for root, dirs, files in os.walk(pp_outputs_dir):
                if not files:
                    continue
                    
                local_dir = Path(root)
                parts = local_dir.relative_to(pp_outputs_dir).parts
                if len(parts) < 3: # Ensure we are inside os/mode/server folder
                    continue
                
                json_file = None
                for f in files:
                    if f in ["platformprofile.json", "platformprofiler.json", "results.json"]:
                        json_file = local_dir / f
                        break
                
                if not json_file:
                    txt_file = None
                    for f in files:
                        if f.endswith(".txt") and f != "validation_results.txt":
                            txt_file = local_dir / f
                            break
                    
                    if txt_file:
                        parsed_data = parse_txt_to_json(txt_file, local_dir / "platformprofile.json")
                        if parsed_data:
                            json_file = local_dir / "platformprofile.json"
                            # Write both platformprofile.json and platformprofiler.json to support all services
                            with open(local_dir / "platformprofiler.json", "w", encoding="utf-8") as jf:
                                json.dump(parsed_data, jf, indent=4)
                            with open(local_dir / "results.json", "w", encoding="utf-8") as jf:
                                json.dump(parsed_data, jf, indent=4)

                if json_file:
                    try:
                        with open(json_file, 'r', encoding='utf-8') as jf:
                            data = json.load(jf)
                        
                        print(f"[INFO] Running PP automated test cases on: {local_dir}")
                        
                        # Configure test cases with injected server profile data
                        TestPlatformProfilerJson._use_real_data = True
                        TestPlatformProfilerJson.sample_data = data
                        
                        # Load and execute unittest suite
                        loader = unittest.TestLoader()
                        suite = loader.loadTestsFromTestCase(TestPlatformProfilerJson)
                        
                        test_result = ProfilerTestResult()
                        suite.run(test_result)
                        
                        validation_lines = []
                        for test_name in test_result.passed_tests:
                            validation_lines.append(f"[PASS] {test_name}")
                        for test_name, error_msg in test_result.failed_tests:
                            validation_lines.append(f"[FAIL] {test_name} : {error_msg}")
                            
                        # If custom validation keys are requested, execute them too
                        if keys_to_check:
                            custom_res = validate_keys(data, keys_to_check)
                            if custom_res:
                                validation_lines.append(custom_res)
                                
                        validation_output = "\n".join(validation_lines)
                        
                        val_out_path = local_dir / "validation_results.txt"
                        with open(val_out_path, "w", encoding="utf-8") as f:
                            f.write(validation_output)
                        print(f"[INFO] Saved test validations to {val_out_path}")
                    except Exception as e:
                        print(f"[ERROR] Failed to run test cases in {local_dir}: {e}")

        # Run automated unittest suite for Workload Profiler (WP)
        wp_outputs_dir = Path("outputs/wp")
        if wp_outputs_dir.exists():
            from test_cases.wp.test_wp_output import TestWorkloadProfilerOutput

            for root, dirs, files in os.walk(wp_outputs_dir):
                if not files:
                    continue
                    
                local_dir = Path(root)
                parts = local_dir.relative_to(wp_outputs_dir).parts
                if len(parts) < 3: # Ensure we are inside os/mode/server folder
                    continue
                
                print(f"[INFO] Running WP output validations on: {local_dir}")
                
                # Configure Test class with dynamic directory path
                TestWorkloadProfilerOutput._use_real_dir = True
                TestWorkloadProfilerOutput.real_dir_path = str(local_dir)
                
                # Load and execute unittest suite
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromTestCase(TestWorkloadProfilerOutput)
                
                test_result = ProfilerTestResult()
                suite.run(test_result)
                
                validation_lines = []
                for test_name in test_result.passed_tests:
                    validation_lines.append(f"[PASS] {test_name}")
                for test_name, error_msg in test_result.failed_tests:
                    validation_lines.append(f"[FAIL] {test_name} : {error_msg}")
                    
                validation_output = "\n".join(validation_lines)
                
                val_out_path = local_dir / "validation_results.txt"
                with open(val_out_path, "w", encoding="utf-8") as f:
                    f.write(validation_output)
                print(f"[INFO] Saved test validations to {val_out_path}")

        # HTML report generation
        print("\n[INFO] Generating final execution HTML reports...")
        for module_key, _ in modules_to_run:
            generate_html_report(module_key)

    except KeyboardInterrupt:
        print("\n[INFO] Execution interrupted by user")
    except Exception as error:
        print(f"\n[ERROR] {error}")


if __name__ == "__main__":
    main()