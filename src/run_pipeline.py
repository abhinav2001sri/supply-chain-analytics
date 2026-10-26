"""Run the full pipeline end to end: generate, clean, load, analyse, export and build the weekly report."""
import argparse
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
STEPS = ["generate_data.py", "clean_data.py", "load_to_sql.py", "analysis.py", "export_powerbi.py", "weekly_report.py"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generate", action="store_true",
                        help="reuse existing data/raw files (e.g. when real extracts are dropped in)")
    args = parser.parse_args()
    for step in STEPS:
        if args.skip_generate and step == "generate_data.py":
            continue
        print(f"\n>>> {step}")
        subprocess.run([sys.executable, str(SRC / step)], check=True)


if __name__ == "__main__":
    main()
