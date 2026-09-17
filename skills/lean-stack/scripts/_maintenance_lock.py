"""Process-lifetime locks shared by the three standalone maintenance helpers.

On POSIX the verified containing directory is locked as well as the anchor.
Replacing only an anchor cannot split updated writers across different locks.
The containing directory must remain stable; arbitrary directory replacement,
network filesystems and concurrent old-protocol writers are outside this contract.
"""
from __future__ import annotations

import contextlib
import errno
import os
from pathlib import Path
import stat
from typing import Iterator


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _plain(metadata: os.stat_result, *, directory: bool, error_type: type[RuntimeError]) -> None:
    linked = stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )
    expected_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if linked or not expected_type or (not directory and metadata.st_nlink != 1):
        expected = "directory" if directory else "single-link regular file"
        raise error_type(f"maintenance lock requires a plain {expected}")


def _same_path(path: Path, opened: os.stat_result, *, directory: bool, error_type: type[RuntimeError]) -> None:
    current = os.lstat(path)
    _plain(current, directory=directory, error_type=error_type)
    if not os.path.samestat(opened, current):
        raise error_type("maintenance lock path changed during acquisition")


def _acquire(descriptor: int, *, error_type: type[RuntimeError], busy_message: str) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise error_type(busy_message) from exc
        raise


def _release(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextlib.contextmanager
def exclusive_lock(
    anchor: Path, *, error_type: type[RuntimeError], busy_message: str,
    reject_legacy_marker: bool = False,
) -> Iterator[None]:
    """Take non-blocking locks, retaining the empty anchor after release.

    Pre-existing nonempty install/release markers require explicit inspection;
    an old marker's PID or age is not proof that stealing its lock is safe.
    """
    anchor = anchor.expanduser().absolute()
    parent_before = os.lstat(anchor.parent)
    _plain(parent_before, directory=True, error_type=error_type)
    with contextlib.ExitStack() as cleanup:
        if os.name != "nt":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            parent_fd = os.open(anchor.parent, flags)
            cleanup.callback(os.close, parent_fd)
            parent_opened = os.fstat(parent_fd)
            _plain(parent_opened, directory=True, error_type=error_type)
            if not os.path.samestat(parent_before, parent_opened):
                raise error_type("maintenance lock directory changed while opening")
            _acquire(parent_fd, error_type=error_type, busy_message=busy_message)
            cleanup.callback(_release, parent_fd)
            _same_path(anchor.parent, parent_opened, directory=True, error_type=error_type)

        before = os.lstat(anchor) if os.path.lexists(anchor) else None
        if before is not None:
            _plain(before, directory=False, error_type=error_type)
            if reject_legacy_marker and before.st_size:
                raise error_type("legacy lock already exists; inspect it before migration")
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if before is None:
            try:
                descriptor = os.open(anchor, flags | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                descriptor = os.open(anchor, flags)
        else:
            # Never create through a path changed to a dangling link, including
            # on platforms without O_NOFOLLOW. Opening an existing anchor only
            # needs read/write access, not permission to create a new target.
            descriptor = os.open(anchor, flags)
        cleanup.callback(os.close, descriptor)
        opened = os.fstat(descriptor)
        _plain(opened, directory=False, error_type=error_type)
        if before is not None and not os.path.samestat(before, opened):
            raise error_type("maintenance lock changed while opening")
        if reject_legacy_marker and opened.st_size:
            raise error_type("legacy lock already exists; inspect it before migration")
        _same_path(anchor, opened, directory=False, error_type=error_type)
        _acquire(descriptor, error_type=error_type, busy_message=busy_message)
        cleanup.callback(_release, descriptor)
        _same_path(anchor, opened, directory=False, error_type=error_type)
        # No code here or in the callers unlinks the anchor on normal release.
        yield
