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

if os.name != "nt":
    from _thread import allocate_lock

    _fork_gate = allocate_lock()
    _lock_descriptors: set[int] = set()

    def _close_inherited_descriptors() -> None:
        # flock belongs to the open file description shared across fork.
        # Drop the child's references without unlocking the parent's copies.
        try:
            for descriptor in _lock_descriptors:
                os.close(descriptor)
            _lock_descriptors.clear()
        finally:
            _fork_gate.release()

    os.register_at_fork(before=_fork_gate.acquire, after_in_parent=_fork_gate.release,
                        after_in_child=_close_inherited_descriptors)


@contextlib.contextmanager
def _open_descriptor(path: Path, flags: int, mode: int = 0o600) -> Iterator[int]:
    if os.name == "nt":
        descriptor = os.open(path, flags, mode)
        try:
            yield descriptor
        finally:
            os.close(descriptor)
        return

    owner = os.getpid()
    with _fork_gate:
        descriptor = os.open(path, flags, mode)
        _lock_descriptors.add(descriptor)
    try:
        yield descriptor
    finally:
        # The fork hook already closed this descriptor in the child. Its
        # numeric slot may now belong to an unrelated file.
        if os.getpid() == owner:
            with _fork_gate:
                _lock_descriptors.remove(descriptor)
                os.close(descriptor)


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
            parent_fd = cleanup.enter_context(_open_descriptor(anchor.parent, flags))
            parent_opened = os.fstat(parent_fd)
            _plain(parent_opened, directory=True, error_type=error_type)
            if not os.path.samestat(parent_before, parent_opened):
                raise error_type("maintenance lock directory changed while opening")
            _acquire(parent_fd, error_type=error_type, busy_message=busy_message)
            _same_path(anchor.parent, parent_opened, directory=True, error_type=error_type)

        before = os.lstat(anchor) if os.path.lexists(anchor) else None
        if before is not None:
            _plain(before, directory=False, error_type=error_type)
            if reject_legacy_marker and before.st_size:
                raise error_type("legacy lock already exists; inspect it before migration")
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if before is None:
            try:
                descriptor = cleanup.enter_context(_open_descriptor(anchor, flags | os.O_CREAT | os.O_EXCL))
            except FileExistsError:
                descriptor = cleanup.enter_context(_open_descriptor(anchor, flags))
        else:
            # Never create through a path changed to a dangling link, including
            # on platforms without O_NOFOLLOW. Opening an existing anchor only
            # needs read/write access, not permission to create a new target.
            descriptor = cleanup.enter_context(_open_descriptor(anchor, flags))
        opened = os.fstat(descriptor)
        _plain(opened, directory=False, error_type=error_type)
        if before is not None and not os.path.samestat(before, opened):
            raise error_type("maintenance lock changed while opening")
        if reject_legacy_marker and opened.st_size:
            raise error_type("legacy lock already exists; inspect it before migration")
        _same_path(anchor, opened, directory=False, error_type=error_type)
        _acquire(descriptor, error_type=error_type, busy_message=busy_message)
        _same_path(anchor, opened, directory=False, error_type=error_type)
        # No code here or in the callers unlinks the anchor on normal release.
        yield
