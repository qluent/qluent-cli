"""Helpers for building standalone Qluent CLI binaries with PyInstaller."""

from __future__ import annotations

import base64
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def normalize_platform(value: str | None = None) -> str:
    raw = (value or sys.platform).lower()
    if raw.startswith("darwin"):
        return "darwin"
    if raw.startswith("linux"):
        return "linux"
    if raw.startswith("win"):
        return "windows"
    raise ValueError(f"Unsupported platform: {raw}")


def normalize_arch(value: str | None = None) -> str:
    raw = (value or platform.machine()).lower()
    if raw in {"x86_64", "amd64", "x64"}:
        return "x64"
    if raw in {"arm64", "aarch64"}:
        return "arm64"
    raise ValueError(f"Unsupported architecture: {raw}")


def executable_name(platform_name: str) -> str:
    return "qluent.exe" if platform_name == "windows" else "qluent"


def artifact_name(platform_name: str, arch_name: str) -> str:
    suffix = ".exe" if platform_name == "windows" else ""
    return f"qluent-{platform_name}-{arch_name}{suffix}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_file(path: Path) -> Path:
    checksum_path = path.with_name(f"{path.name}.sha256")
    checksum_path.write_text(f"{sha256_file(path)}  {path.name}\n")
    return checksum_path


def sign_checksum_file(checksum_path: Path, private_key_pem: str) -> Path:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    checksum_content = checksum_path.read_bytes()
    signature = private_key.sign(checksum_content)
    sig_path = checksum_path.with_name(f"{checksum_path.name}.sig")
    sig_path.write_text(base64.b64encode(signature).decode() + "\n")
    return sig_path


def build_pyinstaller_args(
    *,
    entrypoint: Path,
    work_dir: Path,
    dist_dir: Path,
    spec_dir: Path,
) -> list[str]:
    from qluent_cli.main import INSTRUCTIONS_FILENAME

    instructions_file = entrypoint.parent / INSTRUCTIONS_FILENAME
    if not instructions_file.exists():
        raise FileNotFoundError(f"Required data file not found: {instructions_file}")
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "qluent",
        "--paths",
        str(entrypoint.parent.parent),
        "--add-data",
        f"{instructions_file}{os.pathsep}.",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        str(entrypoint),
    ]


def build_binary(
    *,
    project_root: Path,
    output_dir: Path,
) -> Path:
    platform_name = normalize_platform()
    arch_name = normalize_arch()

    entrypoint = project_root / "src" / "qluent_cli" / "main.py"
    if not entrypoint.exists():
        raise FileNotFoundError(f"CLI entrypoint not found: {entrypoint}")

    build_root = project_root / "build"
    pyinstaller_dist = build_root / "pyinstaller-dist"
    pyinstaller_work = build_root / "pyinstaller-work"
    pyinstaller_spec = build_root / "pyinstaller-spec"

    if pyinstaller_dist.exists():
        shutil.rmtree(pyinstaller_dist)
    if pyinstaller_work.exists():
        shutil.rmtree(pyinstaller_work)
    if pyinstaller_spec.exists():
        shutil.rmtree(pyinstaller_spec)

    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        build_pyinstaller_args(
            entrypoint=entrypoint,
            work_dir=pyinstaller_work,
            dist_dir=pyinstaller_dist,
            spec_dir=pyinstaller_spec,
        ),
        cwd=project_root,
        check=True,
    )

    built_binary = pyinstaller_dist / executable_name(platform_name)
    if not built_binary.exists():
        raise FileNotFoundError(f"PyInstaller did not create {built_binary}")

    final_path = output_dir / artifact_name(platform_name, arch_name)
    shutil.copy2(built_binary, final_path)
    final_path.chmod(0o755)
    checksum_path = write_sha256_file(final_path)

    signing_key = os.environ.get("QLUENT_SIGNING_PRIVATE_KEY")
    if signing_key:
        sig_path = sign_checksum_file(checksum_path, signing_key)
        print(f"Signed {sig_path}")
    else:
        print("QLUENT_SIGNING_PRIVATE_KEY not set, skipping signature")

    return final_path


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    project_root = Path(__file__).resolve().parents[2]
    output_dir = (
        Path(args[0]).expanduser().resolve()
        if args
        else (project_root / "dist" / "binaries").resolve()
    )
    artifact = build_binary(project_root=project_root, output_dir=output_dir)
    print(f"Built {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
