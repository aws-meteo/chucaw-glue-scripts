"""Pytest local compatibility helpers.

This keeps assertion behavior intact while hardening Windows teardown for
known PermissionError flakes in tmpdir symlink cleanup.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import uuid

import _pytest.pathlib as pytest_pathlib
import _pytest.tmpdir as pytest_tmpdir
import pytest


def _safe_cleanup_dead_symlinks(root: Path) -> None:
    try:
        pytest_pathlib.cleanup_dead_symlinks(root)
    except PermissionError:
        # Do not mask test assertion failures; only swallow teardown cleanup flake.
        return


pytest_tmpdir.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks


@pytest.fixture
def tmp_path() -> Path:
    """Workspace-local tmp path fixture to avoid Windows ACL issues in system temp."""
    base = Path.cwd() / "tmp" / "pytest_custom_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"case_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
