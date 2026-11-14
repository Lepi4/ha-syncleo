"""Build and verify the Marketplace ZIP from tracked integration files."""

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/syncleo"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Release tag, e.g. 0.7.1")
    args = parser.parse_args()
    version = args.version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise SystemExit(f"Invalid release version: {args.version}")

    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if manifest["domain"] != "syncleo":
        raise SystemExit("Unexpected integration domain")
    if manifest["version"] != version or project["project"]["version"] != version:
        raise SystemExit("Release tag, manifest.json and pyproject.toml must agree")
    if hacs.get("zip_release") is not True or hacs.get("filename") != "syncleo.zip":
        raise SystemExit("hacs.json must select the syncleo.zip release asset")

    tracked = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--", "custom_components/syncleo"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    files = {}
    for name in filter(None, tracked):
        path = Path(name)
        relative = path.relative_to("custom_components/syncleo").as_posix()
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo", ".zip"}:
            raise SystemExit(f"Unexpected tracked build artifact: {name}")
        data = (ROOT / path).read_bytes()
        if path.suffix in {".py", ".json", ".md", ".txt"}:
            data = data.replace(b"\r\n", b"\n")
        files[relative] = data
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    required = {
        "__init__.py",
        "manifest.json",
        "config_flow.py",
        "transport.py",
        "translations/en.json",
        "brand/icon.png",
        "LICENSE",
        "PYSYNCLEO-LICENSE.txt",
    }
    if missing := required - files.keys():
        raise SystemExit(f"Missing release files: {sorted(missing)}")
    for name, data in files.items():
        if name.endswith(".json"):
            json.loads(data)
        elif name.endswith(".py"):
            compile(data, name, "exec")

    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / "syncleo.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, data)
    with ZipFile(archive) as package:
        if package.testzip() is not None or set(package.namelist()) != files.keys():
            raise SystemExit("ZIP integrity or file list validation failed")
        for name in package.namelist():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit(f"Unsafe archive path: {name}")
            if package.read(name) != files[name]:
                raise SystemExit(f"Archive differs from source: {name}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  syncleo.zip\n", encoding="utf-8")
    print(
        f"Built {archive.name}: {len(files)} files, version {version}, SHA256 {digest}"
    )


if __name__ == "__main__":
    main()
