"""Publish a complete file and retain the object actually displaced by the OS.

The caller holds its normal maintenance lock and supplies a stable parent
directory. This is an exchange plus a verified recovery copy, not a filesystem
compare-and-swap. Nothing here unlinks or automatically restores user data.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


class AtomicUpdateUnsupported(OSError):
    """This platform or volume has no supported exchange with recovery."""


class PublishedConflict(OSError):
    """Publication occurred but the recovered object did not match preflight."""

    def __init__(self, target: Path, recovery_path: Path):
        self.target = target
        self.recovery_path = recovery_path
        super().__init__(f"{target} was published; a concurrent edit or replacement was captured "
                         f"at {recovery_path}; inspect it before retrying")


def _plain(metadata: os.stat_result, *, directory: bool = False) -> bool:
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    return (expected_type(metadata.st_mode)
            and not (getattr(metadata, "st_file_attributes", 0) & 0x400)
            and (directory or metadata.st_nlink == 1))


def _matches(path: Path, data: bytes) -> os.stat_result | None:
    before = path.lstat()
    if not _plain(before) or before.st_size != len(data):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags | getattr(os, "O_NONBLOCK", 0)), "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not _plain(opened) or not os.path.samestat(before, opened):
            return None
        if handle.read(len(data) + 1) != data:
            return None
        return opened if os.path.samestat(opened, path.lstat()) else None


_ACCESS_ACL = "system.posix_acl_access"


def _read_acl(fd: int) -> tuple[bool, bytes | None]:
    try:
        return True, os.getxattr(fd, _ACCESS_ACL)
    except OSError as exc:
        if exc.errno == errno.ENODATA:
            return True, None
        if exc.errno in (errno.ENOSYS, errno.EOPNOTSUPP):
            return False, None
        raise


def _permissions(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)


def _file_acl(path: Path, checked: os.stat_result) -> tuple[bool, bytes | None]:
    if sys.platform != "linux":
        return False, None
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (not _plain(opened) or not os.path.samestat(checked, opened)
                or _permissions(checked) != _permissions(opened)):
            raise OSError(f"file or permissions changed while reading access ACL: {path}")
        return _read_acl(fd)
    finally:
        os.close(fd)


def _preserve_acl(fd: int, expected: tuple[bool, bytes | None]) -> None:
    current = _read_acl(fd)
    if current == expected:
        return
    supported, data = expected
    if supported != current[0]:
        raise OSError("could not establish matching POSIX access ACL support")
    if data is None:
        os.removexattr(fd, _ACCESS_ACL)
    else:
        os.setxattr(fd, _ACCESS_ACL, data)
    if _read_acl(fd) != expected:
        raise OSError("could not preserve original POSIX access ACL")


def _write_file(path: Path, data: bytes, mode: int, owner: os.stat_result | None = None,
                access_acl: tuple[bool, bytes | None] = (False, None)) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        if os.name != "nt":
            fd = stream.fileno()
            staged = os.fstat(fd)
            if owner is not None and (staged.st_uid, staged.st_gid) != (owner.st_uid, owner.st_gid):
                # Keep a field unchanged with -1. An owner can change a file's
                # group to another group they belong to without changing its UID.
                os.fchown(fd, owner.st_uid if owner.st_uid != staged.st_uid else -1,
                          owner.st_gid if owner.st_gid != staged.st_gid else -1)
                staged = os.fstat(fd)
            # Writes and chown can clear set-ID bits; restore mode last.
            if stat.S_IMODE(staged.st_mode) != mode:
                os.fchmod(fd, mode)
            if owner is not None:
                _preserve_acl(fd, access_acl)
            staged = os.fstat(fd)
            if (stat.S_IMODE(staged.st_mode) != mode or
                    (owner is not None and (staged.st_uid, staged.st_gid) != (owner.st_uid, owner.st_gid))):
                raise OSError("could not preserve original POSIX ownership and permission bits")
        os.fsync(stream.fileno())


def _sync_dir(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _exchange(path: Path, candidate: Path, displaced: Path) -> None:
    if sys.platform == "win32":
        from ctypes import wintypes
        replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
        replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        replace.restype = wintypes.BOOL
        if not replace(str(path), str(candidate), str(displaced), 0, None, None):
            code = ctypes.get_last_error()
            if code in (1, 50, 120):  # invalid function / unsupported / unimplemented
                raise AtomicUpdateUnsupported(f"Windows recovery replacement unavailable ({code})")
            raise ctypes.WinError(code)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        exchange = libc.renameat2
    except AttributeError as exc:
        raise AtomicUpdateUnsupported("libc does not provide renameat2") from exc
    exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                         ctypes.c_uint]
    exchange.restype = ctypes.c_int
    if exchange(-100, os.fsencode(candidate), -100, os.fsencode(path), 2) != 0:
        code = ctypes.get_errno()
        if code in (errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL):
            raise AtomicUpdateUnsupported(f"volume does not support RENAME_EXCHANGE: {os.strerror(code)}")
        raise OSError(code, os.strerror(code), str(path))


def _checked_source(path: Path, expected: bytes,
                    recovery_parent: Path | None) -> tuple[os.stat_result, tuple[bool, bytes | None]]:
    path = path.absolute()
    if sys.platform not in ("win32", "linux"):
        raise AtomicUpdateUnsupported(f"recoverable file replacement is unavailable on {sys.platform}")
    parent_metadata = path.parent.lstat()
    if not _plain(parent_metadata, directory=True):
        raise OSError(f"recovery replacement requires a plain parent directory: {path.parent}")
    recovery_parent = path.parent if recovery_parent is None else recovery_parent.absolute()
    recovery_metadata = recovery_parent.lstat()
    if not _plain(recovery_metadata, directory=True):
        raise OSError(f"recovery parent is not a plain directory: {recovery_parent}")
    if recovery_metadata.st_dev != parent_metadata.st_dev:
        raise AtomicUpdateUnsupported(f"recovery parent must be on the same volume as {path}: {recovery_parent}")
    original = _matches(path, expected)
    if original is None:
        raise OSError(f"{path.name} changed after it was read or is not a plain single-link file")
    return original, _file_acl(path, original)


def preflight_existing(path: Path, *, expected: bytes,
                       recovery_parent: Path | None = None) -> os.stat_result:
    """Check known prerequisites without creating files or claiming volume support."""
    original, _ = _checked_source(path, expected, recovery_parent)
    return original


def replace_existing(path: Path, *, expected: bytes, replacement: bytes,
                     recovery_parent: Path | None = None) -> dict[str, str]:
    """Return the retained previous file's location after a verified publication."""
    path = path.absolute()
    recovery_parent = path.parent if recovery_parent is None else recovery_parent.absolute()
    original, access_acl = _checked_source(path, expected, recovery_parent)

    work = Path(tempfile.mkdtemp(prefix=f".{path.name}.recovery-", dir=recovery_parent))
    candidate = work / ("proposed" if sys.platform == "win32" else "exchange")
    previous = work / "previous" if sys.platform == "win32" else candidate
    record = {"target": str(path), "expected_sha256": hashlib.sha256(expected).hexdigest(),
              "proposed_sha256": hashlib.sha256(replacement).hexdigest(),
              "candidate": candidate.name, "displaced": previous.name}
    try:
        _write_file(work / "operation.json", json.dumps(record).encode("ascii"), 0o600)
        _write_file(candidate, replacement, stat.S_IMODE(original.st_mode),
                    owner=original, access_acl=access_acl)
        _sync_dir(work)
        _sync_dir(recovery_parent)
    except OSError as exc:
        raise OSError(f"could not prepare replacement for {path}; retained work at {work}: {exc}") from exc

    try:
        _exchange(path, candidate, previous)
    except AtomicUpdateUnsupported as exc:
        raise AtomicUpdateUnsupported(f"{exc}; publication was not performed; retained work: {work}") from exc
    except OSError as exc:
        # On Windows error 1177 the old object may already have the backup
        # name and the proposed file may still have its staging name.
        raise OSError(f"replacement failed for {path}; inspect target and retained work at {work}: {exc}") from exc

    try:
        _sync_dir(work)
        _sync_dir(path.parent)
        captured = previous.lstat()
        matches = _plain(captured) and os.path.samestat(original, captured)
        if matches and sys.platform == "linux":
            # A late chmod can revoke our read access. Recognize that conflict
            # from metadata before attempting to open the recovered object.
            matches = _permissions(original) == _permissions(captured)
        if matches:
            displaced = _matches(previous, expected)
            matches = displaced is not None and os.path.samestat(original, displaced)
            if matches and sys.platform == "linux":
                matches = (_permissions(original) == _permissions(displaced)
                           and _file_acl(previous, displaced) == access_acl)
    except OSError as exc:
        raise OSError(f"{path} was published; recovery verification or durability failed; "
                      f"inspect the displaced object at {previous}: {exc}") from exc
    if not matches:
        raise PublishedConflict(path, previous)
    return {"previous_path": str(previous)}
