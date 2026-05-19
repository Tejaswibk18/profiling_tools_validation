import unittest

class TestPlatformProfilerJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Sample data simulating platformprofiler.json
        cls.sample_data = {
            "Summary": {
                "Server": {
                    "Model": "ProLiant DL380 Gen10",
                    "SKU": "868703-B21",
                    "Manufacturer": "HPE",
                    "Health": "OK",
                    "CPUModel": "Intel(R) Xeon(R) Gold 6130 CPU @ 2.10GHz",
                    "Region": "US-East"
                },
                "BIOS": {
                    "BIOSVersion": "U30 v1.42",
                    "Microcode": "0x200004d",
                    "SMTControl": "Enabled"
                },
                "CPU": {
                    "Architecture": "x86_64",
                    "Socket(s)": 2,
                    "CPU(s)": 64,
                    "Threads(s)PerCore": 2,
                    "Core(s)PerSocket": 16
                },
                "OS": {
                    "SystemType": "64-bit",
                    "HypervisorVendor": "VMware",
                    "OperatingSystem": "Red Hat Enterprise Linux 7.6",
                    "Kernel": "3.10.0-957.el7.x86_64",
                    "NUMAnode(s)": 2
                }
            }
        }
        cls.summary = cls.sample_data.get("Summary", {})

    # === SERVER SECTION TESTS ===
    def test_server_model(self):
        server = self.summary.get("Server", {})
        self.assertIn("Model", server, "Mandatory key 'Model' missing in Summary.Server")
        self.assertTrue(server["Model"], "Value for 'Model' cannot be empty")

    def test_server_sku(self):
        server = self.summary.get("Server", {})
        self.assertIn("SKU", server, "Mandatory key 'SKU' missing in Summary.Server")
        self.assertTrue(server["SKU"], "Value for 'SKU' cannot be empty")

    def test_server_manufacturer(self):
        server = self.summary.get("Server", {})
        self.assertIn("Manufacturer", server, "Mandatory key 'Manufacturer' missing in Summary.Server")
        self.assertTrue(server["Manufacturer"], "Value for 'Manufacturer' cannot be empty")

    def test_server_health(self):
        server = self.summary.get("Server", {})
        self.assertIn("Health", server, "Mandatory key 'Health' missing in Summary.Server")
        self.assertTrue(server["Health"], "Value for 'Health' cannot be empty")

    def test_server_cpumodel(self):
        server = self.summary.get("Server", {})
        self.assertIn("CPUModel", server, "Mandatory key 'CPUModel' missing in Summary.Server")
        self.assertTrue(server["CPUModel"], "Value for 'CPUModel' cannot be empty")


    # === BIOS SECTION TESTS ===
    def test_bios_version(self):
        bios = self.summary.get("BIOS", {})
        self.assertIn("BIOSVersion", bios, "Mandatory key 'BIOSVersion' missing in Summary.BIOS")
        self.assertTrue(bios["BIOSVersion"], "Value for 'BIOSVersion' cannot be empty")

    def test_bios_microcode(self):
        bios = self.summary.get("BIOS", {})
        self.assertIn("Microcode", bios, "Mandatory key 'Microcode' missing in Summary.BIOS")
        self.assertTrue(bios["Microcode"], "Value for 'Microcode' cannot be empty")

    def test_bios_smt_control(self):
        bios = self.summary.get("BIOS", {})
        self.assertIn("SMTControl", bios, "Mandatory key 'SMTControl' missing in Summary.BIOS")
        self.assertTrue(bios["SMTControl"], "Value for 'SMTControl' cannot be empty")


    # === CPU SECTION TESTS ===
    def test_cpu_architecture(self):
        cpu = self.summary.get("CPU", {})
        self.assertIn("Architecture", cpu, "Mandatory key 'Architecture' missing in Summary.CPU")
        self.assertTrue(cpu["Architecture"], "Value for 'Architecture' cannot be empty")

    def test_cpu_sockets(self):
        cpu = self.summary.get("CPU", {})
        self.assertIn("Socket(s)", cpu, "Mandatory key 'Socket(s)' missing in Summary.CPU")
        self.assertTrue(cpu["Socket(s)"], "Value for 'Socket(s)' cannot be empty")

    def test_cpu_cpus(self):
        cpu = self.summary.get("CPU", {})
        self.assertIn("CPU(s)", cpu, "Mandatory key 'CPU(s)' missing in Summary.CPU")
        self.assertTrue(cpu["CPU(s)"], "Value for 'CPU(s)' cannot be empty")

    def test_cpu_threads_per_core(self):
        cpu = self.summary.get("CPU", {})
        self.assertIn("Threads(s)PerCore", cpu, "Mandatory key 'Threads(s)PerCore' missing in Summary.CPU")
        self.assertTrue(cpu["Threads(s)PerCore"], "Value for 'Threads(s)PerCore' cannot be empty")

    def test_cpu_cores_per_socket(self):
        cpu = self.summary.get("CPU", {})
        self.assertIn("Core(s)PerSocket", cpu, "Mandatory key 'Core(s)PerSocket' missing in Summary.CPU")
        self.assertTrue(cpu["Core(s)PerSocket"], "Value for 'Core(s)PerSocket' cannot be empty")


    # === OS SECTION TESTS ===
    def test_os_system_type(self):
        os_data = self.summary.get("OS", {})
        self.assertIn("SystemType", os_data, "Mandatory key 'SystemType' missing in Summary.OS")
        self.assertTrue(os_data["SystemType"], "Value for 'SystemType' cannot be empty")

    def test_os_operating_system(self):
        os_data = self.summary.get("OS", {})
        self.assertIn("OperatingSystem", os_data, "Mandatory key 'OperatingSystem' missing in Summary.OS")
        self.assertTrue(os_data["OperatingSystem"], "Value for 'OperatingSystem' cannot be empty")

    def test_os_kernel(self):
        os_data = self.summary.get("OS", {})
        self.assertIn("Kernel", os_data, "Mandatory key 'Kernel' missing in Summary.OS")
        self.assertTrue(os_data["Kernel"], "Value for 'Kernel' cannot be empty")

    def test_os_numa_nodes(self):
        os_data = self.summary.get("OS", {})
        self.assertIn("NUMAnode(s)", os_data, "Mandatory key 'NUMAnode(s)' missing in Summary.OS")
        self.assertTrue(os_data["NUMAnode(s)"], "Value for 'NUMAnode(s)' cannot be empty")

if __name__ == '__main__':
    unittest.main()
