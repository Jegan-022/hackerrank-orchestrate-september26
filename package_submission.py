"""
package_submission.py — Creates code.zip according to HackerRank submission contract.
Includes:
- code/ (all production modules)
- evaluation/usage_report.md
- README.md
- requirements.txt
"""
import os
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent
OUTPUT_ZIP = REPO_ROOT / "code.zip"

INCLUDE_EXTENSIONS = {".py", ".md", ".txt", ".json"}
EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "scratch", ".tempmediaStorage"}
EXCLUDE_FILES = {"code.zip", "output.csv", "output_sample.csv", "log.txt"}

def main():
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add code/ directory
        code_dir = REPO_ROOT / "code"
        for root, dirs, files in os.walk(code_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in sorted(files):
                if any(file.endswith(ext) for ext in INCLUDE_EXTENSIONS):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(REPO_ROOT)
                    zf.write(full_path, rel_path)
                    print(f"Added: {rel_path}")

        # Add evaluation/usage_report.md
        eval_report = REPO_ROOT / "evaluation" / "usage_report.md"
        if eval_report.exists():
            zf.write(eval_report, "evaluation/usage_report.md")
            print("Added: evaluation/usage_report.md")

        # Add README.md and requirements.txt
        for fname in ["README.md", "requirements.txt"]:
            fpath = REPO_ROOT / fname
            if fpath.exists():
                zf.write(fpath, fname)
                print(f"Added: {fname}")

    print(f"\n[SUCCESS] Packaged {OUTPUT_ZIP.name} ({OUTPUT_ZIP.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    main()
