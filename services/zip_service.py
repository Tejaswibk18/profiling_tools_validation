import shutil
from pathlib import Path
from services.logger_service import log_error


def archive_outputs(module_key):
    """
    Compresses the outputs folder for the specific module into a ZIP file
    and stores it in the reports folder.
    """
    try:
        source_dir = Path(f"outputs/{module_key}")
        
        if not source_dir.exists():
            print(f"\n[WARNING] Output directory {source_dir} does not exist. Skipping ZIP creation.")
            return

        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = reports_dir / f"{module_key}_results"
        
        # shutil.make_archive adds the .zip extension automatically
        shutil.make_archive(
            base_name=str(zip_path),
            format="zip",
            root_dir=str(source_dir)
        )
        
        print(f"[INFO] Successfully created ZIP archive: {zip_path}.zip")
        
    except Exception as error:
        message = f"Failed to create ZIP archive : {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)

def extract_archive(zip_path, extract_to):
    """
    Extracts a ZIP archive to a target directory.
    """
    try:
        shutil.unpack_archive(
            filename=zip_path,
            extract_dir=extract_to
        )
        print(f"[INFO] Successfully extracted {zip_path} to {extract_to}")
    except Exception as error:
        message = f"Failed to extract ZIP archive : {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)
