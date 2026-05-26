"""Setup helpers for external LOGOS tools."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import LOGOS_ROOT, is_paper_navigator_dir


EVOSKILLS_REPO = "https://github.com/EvoScientist/EvoSkills.git"


@dataclass
class SetupResult:
    success: bool
    destination: Path
    message: str


def install_paper_navigator(
    destination: str = "global",
    force: bool = False,
    repo_url: str = EVOSKILLS_REPO,
) -> SetupResult:
    """Install EvoSkills paper-navigator without entering EvoScientist CLI.

    Args:
        destination: ``global`` for ``~/.evoscientist/skills`` or ``local`` for
            ``LOGOS/skills``. A custom path is also accepted.
        force: Replace an existing installation.
        repo_url: EvoSkills git URL.
    """
    dest_root = _destination_root(destination)
    dest_dir = dest_root / "paper-navigator"

    if dest_dir.exists() and not force:
        if is_paper_navigator_dir(dest_dir):
            return SetupResult(
                success=True,
                destination=dest_dir,
                message=f"paper-navigator already installed at {dest_dir}",
            )
        return SetupResult(
            success=False,
            destination=dest_dir,
            message=f"Destination exists but is not a valid paper-navigator skill: {dest_dir}",
        )

    with tempfile.TemporaryDirectory(prefix="logos-evoskills-") as tmp:
        clone_dir = Path(tmp) / "EvoSkills"
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        source_dir = clone_dir / "skills" / "paper-navigator"
        if not is_paper_navigator_dir(source_dir):
            return SetupResult(
                success=False,
                destination=dest_dir,
                message=f"EvoSkills clone does not contain a valid paper-navigator: {source_dir}",
            )

        dest_root.mkdir(parents=True, exist_ok=True)
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(source_dir, dest_dir)

    if not is_paper_navigator_dir(dest_dir):
        return SetupResult(
            success=False,
            destination=dest_dir,
            message=f"Installed directory failed validation: {dest_dir}",
        )

    return SetupResult(
        success=True,
        destination=dest_dir,
        message=f"Installed paper-navigator at {dest_dir}",
    )


def _destination_root(destination: str) -> Path:
    if destination == "global":
        return Path.home() / ".evoscientist" / "skills"
    if destination == "local":
        return LOGOS_ROOT / "skills"
    return Path(destination).expanduser().resolve()
