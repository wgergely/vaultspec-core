from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_PYTEST_TEMP_ROOT = Path(tempfile.gettempdir()) / "vaultspec-pytest"


def install_windows_temp_compat() -> None:
    """Avoid Windows 0o700 temp-dir ACL breakage on Python 3.13+."""
    if sys.platform != "win32" or sys.version_info < (3, 13):
        return

    from _pytest import pathlib as pytest_pathlib
    from _pytest import tmpdir as pytest_tmpdir

    orig_make_numbered_dir = pytest_pathlib.make_numbered_dir
    orig_make_numbered_dir_with_cleanup = pytest_pathlib.make_numbered_dir_with_cleanup

    def _mkdtemp_755(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
    ) -> str:
        base_dir = os.path.abspath(dir or _PYTEST_TEMP_ROOT)
        os.makedirs(base_dir, mode=0o755, exist_ok=True)
        file_prefix = prefix if prefix is not None else tempfile.template
        file_suffix = suffix or ""
        names = tempfile._get_candidate_names()
        for _ in range(tempfile.TMP_MAX):
            candidate = os.path.join(
                base_dir, f"{file_prefix}{next(names)}{file_suffix}"
            )
            try:
                os.mkdir(candidate, 0o755)
            except FileExistsError:
                continue
            return candidate
        raise FileExistsError("No usable temporary directory name found")

    def _make_numbered_dir_755(root, prefix: str, mode: int = 0o700):
        return orig_make_numbered_dir(root=root, prefix=prefix, mode=0o755)

    def _getbasetemp_755(self):
        if self._basetemp is not None:
            return self._basetemp

        if self._given_basetemp is not None:
            basetemp = self._given_basetemp
            if basetemp.exists():
                pytest_pathlib.rm_rf(basetemp)
            basetemp.mkdir(mode=0o755)
            basetemp = basetemp.resolve()
        else:
            from_env = os.environ.get("PYTEST_DEBUG_TEMPROOT")
            default_temproot = _PYTEST_TEMP_ROOT
            default_temproot.mkdir(mode=0o755, exist_ok=True)
            temproot = pytest_tmpdir.Path(from_env or default_temproot).resolve()
            user = pytest_tmpdir.get_user() or "unknown"
            rootdir = temproot.joinpath(f"pytest-of-{user}")
            try:
                rootdir.mkdir(mode=0o755, exist_ok=True)
            except OSError:
                rootdir = temproot.joinpath("pytest-of-unknown")
                rootdir.mkdir(mode=0o755, exist_ok=True)
            uid = pytest_tmpdir.get_user_id()
            if uid is not None:
                rootdir_stat = rootdir.stat()
                if rootdir_stat.st_uid != uid:
                    raise OSError(
                        f"The temporary directory {rootdir} is not owned by "
                        "the current user. "
                        "Fix this and try again."
                    )
            keep = self._retention_count
            if self._retention_policy == "none":
                keep = 0
            basetemp = orig_make_numbered_dir_with_cleanup(
                prefix="pytest-",
                root=rootdir,
                keep=keep,
                lock_timeout=pytest_tmpdir.LOCK_TIMEOUT,
                mode=0o755,
            )

        self._basetemp = basetemp
        self._trace("new basetemp", basetemp)
        return basetemp

    def _mktemp_755(self, basename: str, numbered: bool = True):
        basename = self._ensure_relative_to_basetemp(basename)
        if not numbered:
            p = self.getbasetemp().joinpath(basename)
            p.mkdir(mode=0o755)
        else:
            p = _make_numbered_dir_755(
                root=self.getbasetemp(), prefix=basename, mode=0o755
            )
            self._trace("mktemp", p)
        return p

    tempfile.mkdtemp = _mkdtemp_755
    pytest_pathlib.make_numbered_dir = _make_numbered_dir_755
    pytest_tmpdir.make_numbered_dir = _make_numbered_dir_755
    pytest_tmpdir.TempPathFactory.getbasetemp = _getbasetemp_755
    pytest_tmpdir.TempPathFactory.mktemp = _mktemp_755
