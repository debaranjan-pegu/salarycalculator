"""Sanity-check a built Windows bundle before it is published.

The embedded interpreter takes ``sys.path`` solely from the ``._pth`` file
beside ``python.exe`` and, being isolated, never prepends the script's own
folder (CPython sets ``safe_path = 1``). If that file does not also expose the
bundle root, ``python app.py`` dies on its first ``import db`` — and only on
Windows, where nobody is looking. So the path is recomputed here exactly the
way CPython computes it: ``joinpath(dirname(._pth), line)``, in file order.

    python3 verify_bundle.py [bundle-dir]
    EXPECTED_VERSION=1.6.2 python3 verify_bundle.py dist/SalaryCalculator-Windows
"""
from __future__ import annotations

import os
import sys

# Modules app.py imports from its own folder — the ones the ._pth must reach.
MODULES = ("app.py", "auth.py", "calc.py", "certgen.py", "db.py", "report.py", "xlsx.py")

# Files the app reads at runtime, relative to the bundle root.
REQUIRED = (
    "VERSION",
    "seed/masters_india.json",
    "seed/countries_world.json",
    "static/index.html",
    "static/app.js",
    "static/styles.css",
    "Salary Calculator.cmd",
    "Share with team.cmd",
    "Update.cmd",
    "README-WINDOWS.txt",
)


def search_paths(bundle: str) -> list[str]:
    """The sys.path CPython will build for this bundle, in order."""
    python_dir = os.path.join(bundle, "python")
    pth_files = sorted(f for f in os.listdir(python_dir) if f.endswith("._pth"))
    if len(pth_files) != 1:
        raise SystemExit(f"expected one ._pth beside python.exe, found {pth_files}")

    entries: list[str] = []
    with open(os.path.join(python_dir, pth_files[0]), encoding="utf-8") as fh:
        for line in fh:
            line = line.partition("#")[0].strip()
            if line and not line.startswith("import "):
                entries.append(os.path.normpath(os.path.join(python_dir, line)))
    return entries


def main(argv: list[str]) -> int:
    bundle = argv[1] if len(argv) > 1 else "dist/SalaryCalculator-Windows"
    if not os.path.isdir(bundle):
        raise SystemExit(f"no bundle at {bundle} — run build_windows_bundle.sh first")

    paths = search_paths(bundle)
    print("sys.path the embedded interpreter will use:")
    for path in paths:
        print(f"  {path}  (dir={os.path.isdir(path)})")

    problems: list[str] = []
    for name in MODULES:
        if not any(os.path.isfile(os.path.join(path, name)) for path in paths):
            problems.append(f"{name} is not importable — no sys.path entry holds it")
    for rel in REQUIRED:
        if not os.path.isfile(os.path.join(bundle, rel)):
            problems.append(f"{rel} is missing")

    # cmd.exe wants CRLF; a lone LF makes Notepad show one enormous line and
    # can trip up label parsing.
    for entry in sorted(os.listdir(bundle)):
        if entry.endswith(".cmd"):
            with open(os.path.join(bundle, entry), "rb") as fh:
                if b"\r\n" not in fh.read():
                    problems.append(f"{entry} has no CRLF line endings")

    version = open(os.path.join(bundle, "VERSION"), encoding="utf-8").read().strip()
    print(f"bundle version: {version}")
    expected = os.environ.get("EXPECTED_VERSION")
    if expected and version != expected:
        problems.append(f"bundle says {version}, the tag says {expected}")

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nbundle OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
