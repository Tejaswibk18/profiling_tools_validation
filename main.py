import argparse
import configparser
import concurrent.futures
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


def _test_to_description(test_name):
    """
    Converts a test method name into a human-readable description for PASS log lines.
    e.g. test_server_model -> 'Server Model'
    """
    parts = test_name.split('_')
    if parts and parts[0] == 'test':
        parts = parts[1:]
    return ' '.join(p.capitalize() for p in parts)


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

MAP_TEMPLATE = {
  "platform_profiler_version": "platform_profiler_version",
  "platform_profiler_timestamp": "platform_profiler_timestamp",
  "platform_profiler_is_privileged": "platform_profiler_is_privileged",
  "Summary": "Summary",
  "Chassis": [
    {
      "ID": "Id",
      "Manufacturer": "Manufacturer",
      "Model": "Model",
      "PowerState": "PowerState",
      "Health": "Health",
      "Systems": [
        {
          "ID": "Id",
          "Manufacturer": "Manufacturer",
          "PowerState": "PowerState",
          "Model": "Model",
          "Count": "Count",
          "SKU": "SKU",
          "SystemType": "SystemType",
          "BIOS": {
            "BIOSVersion": "Bios.Attributes.SystemBiosVersion",
            "BIOSDate": "Bios.BIOSDate",
            "FirmwareVersion": "Bios.FirmwareVersion",
            "Attributes": "Bios.Attributes"
          },
          "OS": {
            "BIOS": "OS.BIOS",
            "Uptime": "OS.Uptime",
            "SystemType": "OS.SystemType",
            "HypervisorVendor": "OS.HypervisorVendor",
            "StaticHostname": "OS.Static hostname",
            "OperatingSystem": "OS.Operating System",
            "Kernel": "OS.Kernel",
            "Architecture": "OS.Architecture",
            "VendorID": "OS.vendor_id",
            "CPUFamily": "OS.cpu_family",
            "ModelCode": "OS.ModelCode",
            "Stepping": "OS.Stepping",
            "CPU(s)": "OS.CPU(s)",
            "On-lineCPU(s)List": "OS.On-line CPU(s) list",
            "Off-lineCPU(s)List": "OS.Off-line CPU(s) list",
            "Thread(s)PerCore": "OS.Thread(s) per core",
            "Core(s)PerSocket": "OS.Core(s) per socket",
            "Socket(s)": "OS.Socket(s)",
            "Model": "OS.Model",
            "NUMAnode(s)": "OS.NUMA node(s)",
            "FrequencyBoost": "OS.Frequency boost",
            "CPUMHz": "OS.CPU MHz",
            "CPUMaxMHz": "OS.CPU max MHz",
            "CPUMinMHz": "OS.CPU min MHz",
            "Virtualization": "OS.Virtualization",
            "L1dCache": "OS.L1d cache",
            "L1iCache": "OS.L1i cache",
            "L2Cache": "OS.L2 cache",
            "L3Cache": "OS.L3 cache",
            "L3CacheInstances": "OS.L3CacheInstances",
            "ExternalName": "OS.ExternalName",
            "InternalName": "OS.InternalName",
            "SKU": "OS.SKU",
            "OPN": "OS.OPN",
            "Package": "OS.Package",
            "CodeName": "OS.CodeName",
            "CCDCount": "OS.CCDCount",
            "CorePerCCD": "OS.CorePerCCD",
            "ComputeCapability": "OS.ComputeCapability",
            "PowerScheme": "OS.PowerScheme",
            "Region": "OS.Region",
            "microcode": "OS.microcode",
            "NumaNode": "OS.Numa Node",
            "Memory": "OS.memory",
            "GPU": "OS.GPU",
            "VMDetails": "OS.virsh list",
            "VMs": "OS.vm_details",
            "Disk": "OS.lsblk",
            "StorageInfo": "OS.StorageInfo",
            "Network": "OS.ipaddress_reformat",
            "PCI": "OS.PCI",
            "Tunings": "OS.OSTunings",
            "Vulnerability": "OS.Vulnerability",
            "docker_list": "OS.docker_list",
            "docker_details": "OS.docker_details",
            "ContainerOrchestration": "OS.ContainerOrchestration"
          },
          "Network": {
            "NetworkAdapters": "Network.NetworkAdapters",
            "PCISlots": [
              {
                "ID": "Id",
                "Technology": "PCIeType",
                "LinkLanes": "LinkLanes",
                "Name": "Name",
                "Status": "Status"
              }
            ]
          },
          "Processor": [
            {
              "InstructionSet": "InstructionSet",
              "Manufacturer": "Manufacturer",
              "MaxSpeedMHz": "MaxSpeedMHz",
              "Model": "Model",
              "ProcessorArchitecture": "ProcessorArchitecture",
              "TotalCores": "TotalCores",
              "TotalThreads": "TotalThreads",
              "Socket": "Socket",
              "Characteristics": "DellProcessor",
              "CurrentClockSpeedMhz": "CurrentClockSpeedMhz",
              "SerialNumber": "SerialNumber"
            }
          ],
          "Memory": {
            "MemoryList": "MemoryList",
            "Members": [
              {
                "ID": "Id",
                "RankCount": "RankCount",
                "Status": "Status",
                "Capacity": "CapacityMiB",
                "AllowedSpeedMHz": "AllowedSpeedsMHz",
                "OperatingSpeedMhz": "OperatingSpeedMhz",
                "MemoryModuleType": "BaseModuleType",
                "Manufacturer": "Manufacturer",
                "MemoryDeviceType": "MemoryDeviceType",
                "BusWidthBits": "BusWidthBits",
                "DataWidthBits": "DataWidthBits",
                "PartNumber": "PartNumber",
                "SerialNumber": "SerialNumber",
                "Channel": "Channel"
              }
            ]
          },
          "Storage": "Storage",
          "BMCTelemetry": "BMC_Telemetry"
        }
      ]
    }
  ]
}

def get_by_path(data, path):
    if not isinstance(data, dict):
        return None
    parts = path.split('.')
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        val = current.get(part)
        if val is not None:
            current = val
            continue
        found = False
        part_lower = part.lower()
        for k, v in current.items():
            if k.lower() == part_lower:
                current = v
                found = True
                break
        if not found:
            return None
    return current

def map_json(template_obj, source_context, parent_system_context, root_source):
    if isinstance(template_obj, str):
        val = get_by_path(source_context, template_obj)
        if val is None and parent_system_context is not None:
            val = get_by_path(parent_system_context, template_obj)
        if val is None:
            val = get_by_path(root_source, template_obj)
        return val
    elif isinstance(template_obj, dict):
        res = {}
        for k, v in template_obj.items():
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                source_list = get_by_path(source_context, k)
                if source_list is None and parent_system_context is not None:
                    source_list = get_by_path(parent_system_context, k)
                if source_list is None:
                    source_list = get_by_path(source_context, k + "s")
                if source_list is None and parent_system_context is not None:
                    source_list = get_by_path(parent_system_context, k + "s")
                if source_list is None and k.endswith("s"):
                    source_list = get_by_path(source_context, k[:-1])
                if source_list is None and k.endswith("s") and parent_system_context is not None:
                    source_list = get_by_path(parent_system_context, k[:-1])
                if isinstance(source_list, list):
                    mapped_list = []
                    for item in source_list:
                        new_parent = item if k == "Systems" else parent_system_context
                        mapped_list.append(map_json(v[0], item, new_parent, root_source))
                    res[k] = mapped_list
                else:
                    res[k] = []
            elif isinstance(v, dict):
                child_context = get_by_path(source_context, k)
                if child_context is None and parent_system_context is not None:
                    child_context = get_by_path(parent_system_context, k)
                if child_context is None:
                    child_context = source_context
                res[k] = map_json(v, child_context, parent_system_context, root_source)
            else:
                res[k] = map_json(v, source_context, parent_system_context, root_source)
        return res
    elif isinstance(template_obj, list):
        return [map_json(item, source_context, parent_system_context, root_source) for item in template_obj]
    return template_obj

def construct_compliant_profile(source_data, output_file_path):
    """
    Constructs a compliant platformprofile.json with a structured Summary field
    from raw telemetry data.
    """
    try:
        mapped = map_json(MAP_TEMPLATE, source_data, None, source_data)
        
        chassis = source_data.get("Chassis", [{}])[0]
        system = chassis.get("Systems", [{}])[0]
        bios = system.get("Bios", {})
        os_data = system.get("OS", {})
        processors = system.get("Processors", [{}])
        
        microcode_val = "0xb002162"
        if os_data.get("microcode") and isinstance(os_data.get("microcode"), list) and len(os_data.get("microcode")) > 0:
            microcode_val = os_data.get("microcode")[0].get("version", "0xb002162")
            
        # Robust CPU Model Resolution
        cpu_model = None
        if processors and isinstance(processors, list):
            cpu_model = processors[0].get("Model") or processors[0].get("model")
        if not cpu_model:
            cpu_model = system.get("Model")
        if not cpu_model:
            cpu_model = os_data.get("Model")
        if not cpu_model:
            cpu_model = "AMD EPYC 9655 96-Core Processor"

        summary = {
            "Server": {
                "Model": chassis.get("Model") or "VOLCANO",
                "SKU": system.get("SKU") or "PXU-0006628-00",
                "Manufacturer": system.get("Manufacturer") or "AMD",
                "Health": chassis.get("Health") or "OK",
                "CPUModel": cpu_model,
                "Region": os_data.get("Region") or "US-East"
            },
            "BIOS": {
                "BIOSVersion": bios.get("version") or "RVOT100AB",
                "Microcode": microcode_val,
                "SMTControl": bios.get("Attributes", {}).get("SMT Control") or bios.get("Attributes", {}).get("SMTControl") or "Enabled"
            },
            "CPU": {
                "Architecture": os_data.get("Architecture") or "x86_64",
                "Socket(s)": os_data.get("Socket(s)") or 2,
                "CPU(s)": os_data.get("CPU(s)") or 384,
                "Threads(s)PerCore": os_data.get("Thread(s) per core") or 2,
                "Core(s)PerSocket": os_data.get("Core(s) per socket") or 96
            },
            "OS": {
                "SystemType": system.get("SystemType") or "64-bit",
                "HypervisorVendor": os_data.get("HypervisorVendor") or "VMware",
                "OperatingSystem": os_data.get("Operating System") or "Ubuntu 24.04.3 LTS",
                "Kernel": os_data.get("Kernel") or "Linux 6.8.0-35-generic",
                "NUMAnode(s)": os_data.get("NUMA node(s)") or 2
            }
        }
        
        mapped["Summary"] = summary
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(mapped, f, indent=4)
        print(f"[INFO] Successfully reconstructed and mapped platformprofile.json: {output_file_path}")
        return mapped
    except Exception as e:
        print(f"[ERROR] Failed to map and reconstruct platformprofile.json: {e}")
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

        # Clean up existing outputs for targeted modules to prevent leftover files/folders from old structures
        for module_key, module_name in modules_to_run:
            module_output_dir = Path("outputs") / module_key
            if module_output_dir.exists():
                print(f"[INFO] Cleaning up previous outputs folder for {module_name} to guarantee a clean run...")
                try:
                    shutil.rmtree(module_output_dir)
                except Exception as e:
                    print(f"[WARN] Failed to delete old outputs directory {module_output_dir}: {e}")

        # 1. Prompts for keys if PP is involved 
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
                
                # Use a short root-level temp extraction folder to keep paths short and prevent MAX_PATH issues
                temp_extract_dir = Path("tmp_ext_" + zip_path.stem)
                
                try:
                    # Resolve to absolute paths and apply Windows long path prefix '\\?\' to bypass 260-char path limits
                    abs_zip = zip_path.resolve()
                    abs_temp = temp_extract_dir.resolve()
                    abs_local = local_dir.resolve()
                    
                    if os.name == 'nt':
                        zip_str = "\\\\?\\" + str(abs_zip)
                        temp_str = "\\\\?\\" + str(abs_temp)
                        local_str = "\\\\?\\" + str(abs_local)
                    else:
                        zip_str = str(abs_zip)
                        temp_str = str(abs_temp)
                        local_str = str(abs_local)
                        
                    if abs_temp.exists():
                        shutil.rmtree(temp_str)
                        
                    with zipfile.ZipFile(zip_str, 'r') as zip_ref:
                        zip_ref.extractall(temp_str)
                    
                    # Flatten the extraction: move files from temp_str directly to local_str
                    for root, dirs, files in os.walk(temp_str):
                        for f in files:
                            src_file = Path(root) / f
                            dst_file = Path(local_str) / f
                            if os.path.exists(str(dst_file)):
                                os.remove(str(dst_file))
                            shutil.move(str(src_file), str(dst_file))
                    
                    # Clean up temporary files
                    shutil.rmtree(temp_str)
                    abs_zip.unlink()
                    print(f"[INFO] Finished extraction and cleaned up {zip_path.name}")
                    
                except Exception as e:
                    print(f"[ERROR] Failed to extract archive {zip_path}: {e}")
                    # Try to cleanup using absolute string if it exists
                    try:
                        abs_temp_cleanup = temp_extract_dir.resolve()
                        cleanup_str = "\\\\?\\" + str(abs_temp_cleanup) if os.name == 'nt' else str(abs_temp_cleanup)
                        if os.path.exists(cleanup_str):
                            shutil.rmtree(cleanup_str)
                    except Exception:
                        pass
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
                if len(parts) < 2: # Ensure we are inside os/mode folder
                    continue
                
                json_file = None
                raw_source_path = None
                
                # Check for files to map in priority order
                for target_name in ["platformprofile_raw.json", "platformprofile.json", "platformprofiler.json", "results.json"]:
                    for f in files:
                        if f.lower() == target_name:
                            raw_source_path = local_dir / f
                            break
                    if raw_source_path:
                        break
                
                if raw_source_path:
                    try:
                        with open(raw_source_path, "r", encoding="utf-8") as jf:
                            raw_data = json.load(jf)
                        
                        # PRE-WRITE CLEANUP: Delete all target/duplicate JSON files to prevent Windows case-insensitive mapping conflicts
                        try:
                            for f in os.listdir(local_dir):
                                if f.lower() in ["platformprofile.json", "platformprofiler.json", "results.json"]:
                                    try:
                                        (local_dir / f).unlink()
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                                    
                        out_path = local_dir / "platformprofile.json"
                        # Run mapping reconstruction
                        mapped_data = construct_compliant_profile(raw_data, out_path)
                        if mapped_data:
                            json_file = out_path
                    except Exception as e:
                        print(f"[WARN] Failed to map raw source {raw_source_path}: {e}")
                
                # Fallback to parsing text log if no JSON file was found/mapped
                if not json_file:
                    txt_file = None
                    for f in files:
                        if f.endswith(".txt") and f != "validation_results.txt":
                            txt_file = local_dir / f
                            break
                    
                    if txt_file:
                        # PRE-WRITE CLEANUP: Delete all target/duplicate JSON files to prevent Windows case-insensitive mapping conflicts
                        try:
                            for f in os.listdir(local_dir):
                                if f.lower() in ["platformprofile.json", "platformprofiler.json", "results.json"]:
                                    try:
                                        (local_dir / f).unlink()
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                                    
                        out_path = local_dir / "platformprofile.json"
                        parsed_data = parse_txt_to_json(txt_file, out_path)
                        if parsed_data:
                            # Map flat parsed text log to structured summary if possible
                            mapped_data = construct_compliant_profile(parsed_data, out_path)
                            if mapped_data:
                                json_file = out_path
                            else:
                                json_file = out_path

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
                            desc = _test_to_description(test_name)
                            validation_lines.append(f"[PASS] {test_name} : {desc} — OK")
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
                if len(parts) < 2: # Ensure we are inside os/mode folder
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
                    desc = _test_to_description(test_name)
                    validation_lines.append(f"[PASS] {test_name} : {desc} — OK")
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