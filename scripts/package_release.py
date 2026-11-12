import argparse
import io
from pathlib import Path
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description="Package committed sources and built frontend, excluding local data")
    parser.add_argument("--output", default="dist/math-comp-workspace.zip")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    assets = root / "frontend/dist"
    if not (assets / "index.html").is_file():
        parser.error("Build frontend first: npm --prefix frontend ci && npm --prefix frontend run build")
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, capture_output=True, text=True, check=True).stdout
    if dirty.strip():
        parser.error("Commit source changes and rebuild before packaging; the working tree has tracked changes")
    committed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.splitlines()
    if "launcher/web_api.py" not in committed:
        parser.error("Commit the web workspace source before packaging")
    source = subprocess.run(["git", "archive", "--format=zip", "HEAD"], cwd=root, capture_output=True, check=True).stdout
    destination = (root / args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    excluded = {".math", "output", "local_textbook", "local_problems", "local_practice", "node_modules", ".venv"}
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in original.namelist():
            parts = Path(name).parts
            if any(part in excluded for part in parts) and not name.endswith(".gitkeep"):
                continue
            archive.writestr(name, original.read(name))
        for path in sorted(assets.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    print(destination)


if __name__ == "__main__":
    main()
