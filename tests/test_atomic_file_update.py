from __future__ import annotations

import hashlib
import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "skills/lean-stack/scripts/_atomic_file_update.py"
SPEC = importlib.util.spec_from_file_location("atomic_update_probe", SCRIPT)
assert SPEC and SPEC.loader
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


@unittest.skipUnless(sys.platform in ("win32", "linux"), "requires a supported native exchange")
class RecoveryExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "document"
        self.old = b"the input that was read"
        self.new = b"complete proposed file"
        self.target.write_bytes(self.old)

    def publish(self):
        return update.replace_existing(self.target, expected=self.old, replacement=self.new)

    def paths_from_record(self):
        work, = self.root.glob(".document.recovery-*")
        record = json.loads((work / "operation.json").read_bytes())
        self.assertEqual(record["expected_sha256"], hashlib.sha256(self.old).hexdigest())
        self.assertEqual(record["proposed_sha256"], hashlib.sha256(self.new).hexdigest())
        return work / record["candidate"], work / record["displaced"]

    def test_verified_publication_returns_the_displaced_file_itself(self):
        old_id = self.target.stat()
        receipt = self.publish()
        _, previous = self.paths_from_record()
        self.assertEqual(str(previous), receipt["previous_path"])
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(previous.read_bytes(), self.old)
        self.assertTrue(os.path.samestat(old_id, previous.stat()))

    def test_prior_edit_is_refused_before_staging(self):
        self.target.write_bytes(b"already edited")
        with self.assertRaisesRegex(OSError, "changed after"):
            self.publish()
        self.assertEqual(self.target.read_bytes(), b"already edited")
        self.assertEqual(list(self.root.glob(".document.recovery-*")), [])

    def test_separate_same_volume_recovery_parent_is_synced_and_identifies_target(self):
        parent = self.root / "private recoveries"
        parent.mkdir()
        with mock.patch.object(update, "_sync_dir", wraps=update._sync_dir) as sync:
            receipt = update.replace_existing(
                self.target, expected=self.old, replacement=self.new, recovery_parent=parent,
            )
        previous = Path(receipt["previous_path"])
        self.assertEqual(previous.parent.parent, parent)
        self.assertEqual(previous.read_bytes(), self.old)
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(json.loads((previous.parent / "operation.json").read_bytes())["target"],
                         str(self.target))
        self.assertEqual([call.args[0] for call in sync.call_args_list],
                         [previous.parent, parent, previous.parent, self.target.parent])
        self.assertEqual(list(self.root.glob(".document.recovery-*")), [])

    def test_non_directory_recovery_parent_is_refused_before_staging(self):
        with self.assertRaisesRegex(OSError, "not a plain directory"):
            update.replace_existing(self.target, expected=self.old, replacement=self.new,
                                    recovery_parent=self.target)
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob(".document.recovery-*")), [])

    def test_different_device_metadata_is_refused_before_creating_recovery(self):
        parent = self.root / "other volume"
        parent.mkdir()
        local = parent.lstat()
        fake = SimpleNamespace(st_mode=local.st_mode, st_dev=local.st_dev + 1, st_nlink=local.st_nlink)
        lstat = Path.lstat
        with mock.patch.object(Path, "lstat", lambda path: fake if path == parent else lstat(path)):
            with self.assertRaisesRegex(update.AtomicUpdateUnsupported, "same volume"):
                update.replace_existing(self.target, expected=self.old, replacement=self.new,
                                        recovery_parent=parent)
        self.assertEqual(list(parent.iterdir()), [])
        self.assertEqual(self.target.read_bytes(), self.old)

    def test_hard_link_is_refused_before_staging(self):
        alias = self.root / "another name"
        os.link(self.target, alias)
        with self.assertRaisesRegex(OSError, "single-link"):
            self.publish()
        self.assertEqual(alias.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob(".document.recovery-*")), [])

    def test_public_preflight_reads_plain_input_and_rejects_alias_without_writing(self):
        checked = update.preflight_existing(self.target, expected=self.old)
        self.assertTrue(os.path.samestat(checked, self.target.stat()))
        self.assertEqual(list(self.root.iterdir()), [self.target])
        linked = self.root / "alias"
        os.link(self.target, linked)
        with self.assertRaisesRegex(OSError, "single-link"):
            update.preflight_existing(self.target, expected=self.old)
        self.assertEqual(set(self.root.iterdir()), {self.target, linked})

    @unittest.skipUnless(sys.platform == "linux", "POSIX set-group-ID inheritance")
    def test_sgid_target_group_survives_staging_in_different_parent(self):
        gid = next((g for g in os.getgroups() if g != self.root.stat().st_gid), None)
        if gid is None:
            self.skipTest("requires a supplementary group different from the staging group")
        meta = self.root / "metadata"
        meta.mkdir()
        os.chown(meta, -1, gid)
        meta.chmod(0o2750)
        target = meta / "manifest"
        target.write_bytes(self.old)
        target.chmod(0o640)
        original = target.stat()
        self.assertEqual(original.st_gid, gid)
        receipt = update.replace_existing(target, expected=self.old, replacement=self.new,
                                          recovery_parent=self.root)
        def permissions(path):
            info = path.stat()
            return info.st_uid, info.st_gid, info.st_mode & 0o7777
        expected = (original.st_uid, gid, 0o640)
        self.assertEqual(permissions(target), expected)
        self.assertEqual(permissions(Path(receipt["previous_path"])), expected)

    @unittest.skipUnless(sys.platform == "linux", "POSIX owner changes")
    def test_candidate_owner_failure_cannot_publish_and_noop_chown_is_omitted(self):
        with mock.patch.object(os, "fchown", side_effect=AssertionError("unexpected chown")):
            self.publish()
        self.target.write_bytes(self.old)
        owner = self.target.stat()
        other_owner = SimpleNamespace(st_uid=owner.st_uid + 1, st_gid=owner.st_gid,
                                      st_mode=owner.st_mode)
        with mock.patch.object(update, "_checked_source", return_value=(other_owner, (True, None))), \
             mock.patch.object(os, "fchown", side_effect=PermissionError("ownership denied")), \
             mock.patch.object(update, "_exchange") as exchange:
            with self.assertRaisesRegex(OSError, "could not prepare.*ownership denied"):
                self.publish()
        exchange.assert_not_called()
        self.assertEqual(self.target.read_bytes(), self.old)

    def named_reader_acl(self, uid, *, directory=False):
        # linux/posix_acl_xattr.h v2: owner, named user, group, mask, other.
        entries = [(1, 7 if directory else 6, 0xffffffff), (2, 4, uid), (4, 0, 0xffffffff),
                   (16, 4, 0xffffffff), (32, 0, 0xffffffff)]
        return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *e) for e in entries)

    def set_acl(self, path, name, acl):
        try:
            os.setxattr(path, name, acl)
        except OSError as exc:
            if exc.errno in (errno.EOPNOTSUPP, errno.ENOSYS):
                self.skipTest("filesystem has no POSIX ACL support")
            raise

    @unittest.skipUnless(sys.platform == "linux", "Linux named access ACLs")
    def test_inherited_acl_cannot_grant_reads_and_explicit_target_acl_survives(self):
        parent = self.root / "with-default-acl"
        parent.mkdir()
        self.set_acl(parent, "system.posix_acl_default", self.named_reader_acl(65534, directory=True))
        self.target.chmod(0o640)
        update.replace_existing(self.target, expected=self.old, replacement=self.new,
                                recovery_parent=parent)
        self.assertNotIn(update._ACCESS_ACL, os.listxattr(self.target))
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)

        custom = self.named_reader_acl(65533)
        self.set_acl(self.target, update._ACCESS_ACL, custom)
        receipt = update.replace_existing(self.target, expected=self.new, replacement=self.old,
                                          recovery_parent=parent)
        self.assertEqual(os.getxattr(self.target, update._ACCESS_ACL), custom)
        self.assertEqual(os.getxattr(receipt["previous_path"], update._ACCESS_ACL), custom)

    @unittest.skipUnless(sys.platform == "linux", "Linux permission edits")
    def test_late_access_acl_or_permission_change_is_reported_as_a_conflict(self):
        custom = self.named_reader_acl(65534)
        native = update._exchange
        for edit in ("mode", "acl"):
            with self.subTest(edit=edit):
                target = self.root / edit
                target.write_bytes(self.old)
                target.chmod(0o640)
                def edit_then_publish(path, candidate, displaced):
                    if edit == "mode":
                        path.chmod(0o000)
                    else:
                        self.set_acl(path, update._ACCESS_ACL, custom)
                    native(path, candidate, displaced)
                with mock.patch.object(update, "_exchange", side_effect=edit_then_publish):
                    with self.assertRaises(update.PublishedConflict) as conflict:
                        update.replace_existing(target, expected=self.old, replacement=self.new)
                previous = conflict.exception.recovery_path
                self.assertEqual(target.read_bytes(), self.new)
                if edit == "mode":
                    self.assertEqual(previous.stat().st_mode & 0o777, 0o000)
                    previous.chmod(0o600)
                else:
                    self.assertEqual(os.getxattr(previous, update._ACCESS_ACL), custom)
                self.assertEqual(previous.read_bytes(), self.old)

    @unittest.skipUnless(sys.platform == "linux", "Linux ACL read failures")
    def test_acl_permission_error_is_not_treated_as_absent_acl(self):
        with mock.patch.object(os, "getxattr", side_effect=PermissionError("access denied")):
            with self.assertRaisesRegex(PermissionError, "access denied"):
                update.preflight_existing(self.target, expected=self.old)
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_last_instant_save_by_another_process_is_captured_and_reported(self):
        native = update._exchange
        edited = b"the independent editor's replacement"
        incoming = self.root / "editor-proposed"
        incoming.write_bytes(edited)
        external_id = incoming.stat()

        def editor_then_publish(path, candidate, displaced):
            subprocess.run([sys.executable, "-B", "-c",
                            "import os,sys; os.replace(sys.argv[1],sys.argv[2])",
                            str(incoming), str(path)], check=True, timeout=10)
            native(path, candidate, displaced)

        with mock.patch.object(update, "_exchange", side_effect=editor_then_publish):
            with self.assertRaises(update.PublishedConflict) as conflict:
                self.publish()
        _, previous = self.paths_from_record()
        self.assertIn(str(previous), str(conflict.exception))
        self.assertEqual(conflict.exception.recovery_path, previous)
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(previous.read_bytes(), edited)
        self.assertTrue(os.path.samestat(external_id, previous.stat()))

    def test_same_inode_external_write_survives_the_final_exchange(self):
        native = update._exchange
        def edit_and_exchange(path, candidate, displaced):
            path.write_bytes(b"late in-place edit")
            native(path, candidate, displaced)
        with mock.patch.object(update, "_exchange", side_effect=edit_and_exchange):
            with self.assertRaises(update.PublishedConflict):
                self.publish()
        _, previous = self.paths_from_record()
        self.assertEqual(previous.read_bytes(), b"late in-place edit")

    def test_conflict_never_rolls_back_over_a_later_save(self):
        native = update._exchange
        def save_around_exchange(path, candidate, displaced):
            path.write_bytes(b"before publication")
            native(path, candidate, displaced)
            path.write_bytes(b"after publication")
        with mock.patch.object(update, "_exchange", side_effect=save_around_exchange):
            with self.assertRaises(update.PublishedConflict):
                self.publish()
        _, previous = self.paths_from_record()
        self.assertEqual(previous.read_bytes(), b"before publication")
        self.assertEqual(self.target.read_bytes(), b"after publication")

    @unittest.skipUnless(sys.platform == "win32", "documented Windows 1177 outcome")
    def test_partial_native_error_retains_both_names_for_recovery(self):
        def incomplete(path, candidate, displaced):
            os.rename(path, displaced)
            raise OSError(1177, "injected partial native replacement")
        with mock.patch.object(update, "_exchange", side_effect=incomplete):
            with self.assertRaisesRegex(OSError, "inspect target and retained work"):
                self.publish()
        candidate, previous = self.paths_from_record()
        self.assertFalse(self.target.exists())
        self.assertEqual(candidate.read_bytes(), self.new)
        self.assertEqual(previous.read_bytes(), self.old)

    def test_unsupported_volume_preserves_active_and_staged_bytes(self):
        with mock.patch.object(update, "_exchange", side_effect=update.AtomicUpdateUnsupported("unsupported")):
            with self.assertRaisesRegex(update.AtomicUpdateUnsupported, "not performed"):
                self.publish()
        candidate, _ = self.paths_from_record()
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertEqual(candidate.read_bytes(), self.new)

    def check_abrupt_exit(self, at):
        code = """
import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('worker', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
native = module._exchange
def stop(path, candidate, previous):
    if sys.argv[3] == 'after':
        native(path, candidate, previous)
    os._exit(91)
module._exchange = stop
module.replace_existing(Path(sys.argv[2]), expected=bytes.fromhex(sys.argv[4]),
                        replacement=bytes.fromhex(sys.argv[5]))
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(SCRIPT),
                                 str(self.target), at, self.old.hex(), self.new.hex()],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 91, result.stderr)
        return self.paths_from_record()

    def test_abrupt_exit_before_native_publication(self):
        candidate, _ = self.check_abrupt_exit("before")
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertEqual(candidate.read_bytes(), self.new)

    def test_abrupt_exit_after_native_publication(self):
        _, previous = self.check_abrupt_exit("after")
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(previous.read_bytes(), self.old)


if __name__ == "__main__":
    unittest.main()
