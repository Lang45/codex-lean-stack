"""Process ownership and recovery checks for the shared maintenance lock."""
import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import unittest


LOCK_MODULE = Path(__file__).resolve().parents[1] / "skills/lean-stack/scripts/_maintenance_lock.py"
spec = importlib.util.spec_from_file_location("lock_repair_test_subject", LOCK_MODULE)
locks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locks)


@unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork and flock")
class ForkedMaintenanceLockTests(unittest.TestCase):
    def setUp(self):
        self.anchor = Path(tempfile.mkdtemp(prefix="lean-maintenance-lock-")) / "anchor"

    def guard(self):
        return locks.exclusive_lock(self.anchor, error_type=RuntimeError, busy_message="busy")

    def test_child_leaving_inherited_context_cannot_unlock_owner(self):
        child = None
        child_status = 1
        try:
            with self.guard():
                child = os.fork()
                if child:
                    self.assertEqual(os.waitpid(child, 0)[1], 0)
                    with self.assertRaisesRegex(RuntimeError, "^busy$"):
                        with self.guard():
                            self.fail("a second acquisition entered the active owner's section")
                else:
                    # Reuse the two slots freed by the child fork hook.
                    new_descriptors = [os.open(os.devnull, os.O_RDONLY) for _ in range(2)]
            if child == 0:
                for descriptor in new_descriptors:
                    os.fstat(descriptor)
                child_status = 0
        finally:
            if child == 0:
                os._exit(child_status)
        with self.guard():
            pass

    def test_abrupt_owner_exit_releases_lock_while_its_child_is_alive(self):
        observer, survivor = socket.socketpair()
        observer.settimeout(10)
        survivor.settimeout(10)
        owner = os.fork()
        if owner == 0:
            try:
                observer.close()
                with self.guard():
                    if os.fork():
                        os._exit(71)
                    survivor.sendall(b"r")
                    if survivor.recv(1) == b"x":
                        survivor.sendall(b"y")
                        os._exit(0)
            finally:
                os._exit(72)
        survivor.close()
        with observer:
            self.assertEqual(os.waitpid(owner, 0)[1], 71 << 8)
            self.assertEqual(observer.recv(1), b"r")
            try:
                with self.guard():
                    pass
            finally:
                observer.sendall(b"x")
                self.assertEqual(observer.recv(1), b"y")
