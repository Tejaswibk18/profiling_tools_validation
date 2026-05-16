import argparse
from services.ssh_service import connect_linux_server


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
        "-pp",
        action="store_true",
        help="Run Platform Profiler"
    )

    parser.add_argument(
        "-wp",
        action="store_true",
        help="Run Workload Profiler"
    )

    parser.add_argument(
        "-all",
        action="store_true",
        help="Run All Modules"
    )

    return parser


def get_selected_module(args):
    return next(
        (
            name for flag, name in MODULES.items()
            if getattr(args, flag.lstrip("-").replace("-", "_"))
        ),
        None
    )


def main():
    try:
        parser = get_parser()
        args = parser.parse_args()

        selected_module = get_selected_module(args)

        if not selected_module:
            parser.print_help()
            return

        print(f"\n[INFO] Running : {selected_module}")

        keys = input(
            "\nEnter key(s) "
            "(comma separated if multiple):\n"
        ).split(",")

        keys = [key.strip() for key in keys if key.strip()]

        connect_linux_server(keys)

    except KeyboardInterrupt:
        print("\n[INFO] Execution interrupted by user")

    except Exception as error:
        print(f"\n[ERROR] {error}")


if __name__ == "__main__":
    main()