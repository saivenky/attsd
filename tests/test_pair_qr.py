"""tools/pair-qr.py's URI shape is a contract with the Android app, not ours to
drift -- see the payload format nailed down in the module docstring. This
covers the encoding, not the QR rendering (which is `qrcode`'s job, not ours
to re-test), or the `tailscale ip -4` call (no daemon in CI).

It also covers the live-server discovery helpers (_find_server_pid,
_listening_port, _process_env, and main()'s no-server / no-token exits) by
faking their one dependency, `subprocess.run`, rather than requiring a real
attsd server in CI.
"""

import importlib.util
import os
import unittest
from unittest.mock import patch

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools", "pair-qr.py")

try:
    import qrcode  # noqa: F401
    _HAVE_QRCODE = True
except ImportError:
    _HAVE_QRCODE = False


def _load():
    spec = importlib.util.spec_from_file_location("pair_qr", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(_HAVE_QRCODE, "qrcode not installed — see requirements.txt")
class BuildUriTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_required_fields_only(self):
        uri = self.mod.build_uri("http://100.1.2.3:8765", "tok en/=", None)
        self.assertEqual(uri, "attsd://profile?host=http%3A%2F%2F100.1.2.3%3A8765&token=tok%20en%2F%3D")

    def test_name_comes_first_when_present(self):
        uri = self.mod.build_uri("http://100.1.2.3:8765", "abc", "Home Mac")
        self.assertEqual(
            uri,
            "attsd://profile?name=Home%20Mac&host=http%3A%2F%2F100.1.2.3%3A8765&token=abc",
        )

    def test_empty_name_is_treated_as_absent(self):
        uri = self.mod.build_uri("http://h:1", "t", "")
        self.assertNotIn("name=", uri)


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


@unittest.skipUnless(_HAVE_QRCODE, "qrcode not installed — see requirements.txt")
class FindServerPidTests(unittest.TestCase):
    """No real `ps` in CI -- fake its output instead."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_matches_this_repo_server_py(self):
        ps_out = (
            f"111 /usr/bin/python3 /some/other/repo/server.py\n"
            f"222 /usr/bin/python3 {self.mod.SERVER_PY}\n"
        )
        with patch.object(self.mod.subprocess, "run", return_value=_FakeCompletedProcess(ps_out)):
            self.assertEqual(self.mod._find_server_pid(), 222)

    def test_no_match_returns_none(self):
        ps_out = "111 /usr/bin/python3 /some/other/repo/server.py\n"
        with patch.object(self.mod.subprocess, "run", return_value=_FakeCompletedProcess(ps_out)):
            self.assertIsNone(self.mod._find_server_pid())


@unittest.skipUnless(_HAVE_QRCODE, "qrcode not installed — see requirements.txt")
class ListeningPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_reads_bound_port_from_lsof(self):
        lsof_out = (
            "COMMAND   PID      USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
            "Python  25526 skandallu    3u  IPv4 0x1        0t0  TCP *:8765 (LISTEN)\n"
        )
        with patch.object(self.mod.subprocess, "run", return_value=_FakeCompletedProcess(lsof_out)):
            self.assertEqual(self.mod._listening_port(25526), "8765")

    def test_no_listening_socket_returns_none(self):
        with patch.object(self.mod.subprocess, "run", return_value=_FakeCompletedProcess("")):
            self.assertIsNone(self.mod._listening_port(1))


@unittest.skipUnless(_HAVE_QRCODE, "qrcode not installed — see requirements.txt")
class ProcessEnvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_parses_key_value_pairs_from_ps_dash_e(self):
        command = (
            "/usr/bin/python3 /repo/server.py OSLogRateLimit=64 "
            "ATTSD_DEFAULT_DIR=/Users/x/obsidian ATTSD_TOKEN=abc123XYZ "
            "PATH=/usr/bin:/bin LOGNAME=x"
        )
        with patch.object(self.mod.subprocess, "run", return_value=_FakeCompletedProcess(command)):
            env = self.mod._process_env(12345)
        self.assertEqual(env["ATTSD_TOKEN"], "abc123XYZ")
        self.assertEqual(env["ATTSD_DEFAULT_DIR"], "/Users/x/obsidian")
        self.assertEqual(env["PATH"], "/usr/bin:/bin")

    def test_missing_token_key_is_absent(self):
        command = "/usr/bin/python3 /repo/server.py PATH=/usr/bin:/bin"
        with patch.object(self.mod.subprocess, "run", return_value=_FakeCompletedProcess(command)):
            env = self.mod._process_env(1)
        self.assertNotIn("ATTSD_TOKEN", env)


@unittest.skipUnless(_HAVE_QRCODE, "qrcode not installed — see requirements.txt")
class MainDiscoveryExitTests(unittest.TestCase):
    """main()'s two honest-failure paths: no server found, and a server with
    Respond disabled (no ATTSD_TOKEN). Neither should silently fall back to a
    guessed host/port/token."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_no_running_server_exits_nonzero_with_hint(self):
        with patch.object(self.mod, "_find_server_pid", return_value=None), \
             patch("sys.argv", ["pair-qr.py"]), self.assertRaises(SystemExit) as ctx:
            self.mod.main()
        self.assertIn("no running attsd server found", str(ctx.exception))

    def test_server_without_token_exits_nonzero(self):
        with patch.object(self.mod, "_find_server_pid", return_value=999), \
             patch.object(self.mod, "_process_env", return_value={}), \
             patch("sys.argv", ["pair-qr.py"]), self.assertRaises(SystemExit) as ctx:
            self.mod.main()
        self.assertIn("ATTSD_TOKEN", str(ctx.exception))

    def test_host_override_still_requires_discovered_token(self):
        """--host is an escape hatch for the host, not a way to skip token
        discovery -- the token still comes from the live process."""
        with patch.object(self.mod, "_find_server_pid", return_value=999), \
             patch.object(self.mod, "_process_env", return_value={"ATTSD_TOKEN": "tok"}), \
             patch.object(self.mod, "_listening_port", return_value="9999"), \
             patch("sys.argv", ["pair-qr.py", "--host", "http://192.168.1.5:9999"]):
            # Should not raise -- discovery succeeded and --host bypassed
            # only the Tailscale lookup.
            self.mod.main()
