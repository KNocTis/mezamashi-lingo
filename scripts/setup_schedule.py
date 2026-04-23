import os
import subprocess
import sys
from pathlib import Path

# Configuration
LABEL = "com.noahchang.mezamashilingo"
PLIST_FILENAME = f"{LABEL}.plist"
TEMPLATE_PATH = Path(__file__).parent / "templates" / f"{PLIST_FILENAME}.template"
TARGET_PATH = Path.home() / "Library" / "LaunchAgents" / PLIST_FILENAME

def setup():
    # 1. Get project root
    project_root = Path(__file__).parent.parent.absolute()
    print(f"Project root: {project_root}")

    # 2. Define paths
    python_path = project_root / "venv" / "bin" / "python"
    script_path = project_root / "main.py"
    working_dir = project_root
    log_dir = project_root / "logs"
    log_stdout = log_dir / "daily_run.log"
    log_stderr = log_dir / "daily_run_error.log"

    # Ensure logs directory exists
    log_dir.mkdir(exist_ok=True)

    # 3. Read and fill template
    if not TEMPLATE_PATH.exists():
        print(f"Error: Template not found at {TEMPLATE_PATH}")
        sys.exit(1)

    with open(TEMPLATE_PATH, "r") as f:
        template = f.read()

    config = template.format(
        PYTHON_PATH=python_path,
        SCRIPT_PATH=script_path,
        WORKING_DIR=working_dir,
        LOG_STDOUT=log_stdout,
        LOG_STDERR=log_stderr
    )

    # 4. Write to LaunchAgents
    print(f"Writing configuration to {TARGET_PATH}")
    with open(TARGET_PATH, "w") as f:
        f.write(config)

    # 5. Load the agent
    print("Unloading existing agent (if any)...")
    subprocess.run(["launchctl", "unload", str(TARGET_PATH)], capture_output=True)
    
    print("Loading new agent...")
    result = subprocess.run(["launchctl", "load", str(TARGET_PATH)], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("Successfully scheduled! The script will run every morning at 8:30 AM.")
        print(f"Logs will be available at: {log_stdout}")
    else:
        print(f"Failed to load agent: {result.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    setup()
