"""tools/pair-qr.py's URI shape is a contract with the Android app, not ours to
drift -- see the payload format nailed down in the module docstring. This
covers the encoding, not the QR rendering (which is `qrcode`'s job, not ours
to re-test), or the `tailscale ip -4` call (no daemon in CI).
"""

import importlib.util
import os
import unittest

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
