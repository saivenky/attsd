#!/usr/bin/env python3
"""Render this Mac's pairing URI as a QR code the Android app can scan.

Pairing today means reading a 20-30 character base64 `ATTSD_TOKEN` off the
Mac's screen and typing it into the phone by hand. This prints the same
information as a terminal QR code instead, plus the raw URI beneath it as a
copy-paste fallback for a phone camera that cannot reach the terminal.

The payload is the Android app's fixed deep-link format -- not this repo's to
change:

    attsd://profile?name=<urlencoded>&host=<urlencoded>&token=<urlencoded>

`host` is the URL the phone must actually reach this server at, so it is the
Tailscale IPv4 (`tailscale ip -4`), never `localhost` -- meaningless off the
Mac, and ADR 0001 already settled Tailscale as the transport. Override with
--host if you're on a plain LAN instead, or `tailscale` is not the transport
you're using.

The token is read from `ATTSD_TOKEN`, the same variable `server.py` reads it
from (see ADR 0007) -- never taken as an argument, so it never lands in shell
history or `ps`. It is never logged or written to disk here; it only ever
reaches the terminal inside the QR code and the one printed fallback line,
both already private to whoever is sitting at this Mac.

    tools/pair-qr.py
    tools/pair-qr.py --name Home
    tools/pair-qr.py --host http://192.168.1.20:8765
"""

import argparse
import os
import subprocess
import sys
from urllib.parse import quote

try:
    import qrcode
except ImportError:
    sys.exit(
        "pair-qr: requires the 'qrcode' package -- pip install -r requirements.txt"
    )

PORT = os.environ.get("ATTSD_PORT", "8765")
TOKEN = os.environ.get("ATTSD_TOKEN", "")


def _tailscale_ip() -> str | None:
    """This Mac's Tailscale IPv4 -- the address ADR 0001 makes reachable from
    a phone on cellular, unlike `localhost` or a LAN-only address."""
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    ip = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
    return ip or None


def default_host() -> str:
    ip = _tailscale_ip()
    if not ip:
        sys.exit(
            "pair-qr: could not read a Tailscale IPv4 (`tailscale ip -4` failed -- "
            "is Tailscale installed and running?). Pass --host explicitly, e.g. "
            "--host http://192.168.1.20:8765"
        )
    return f"http://{ip}:{PORT}"


def build_uri(host: str, token: str, name: str | None) -> str:
    """The attsd:// pairing URI, in the Android app's fixed field order."""
    pairs = []
    if name:
        pairs.append(("name", name))
    pairs.append(("host", host))
    pairs.append(("token", token))
    query = "&".join(f"{k}={quote(v, safe='')}" for k, v in pairs)
    return f"attsd://profile?{query}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", help="human label shown on the phone, e.g. Home")
    parser.add_argument(
        "--host",
        help="override the auto-detected Tailscale URL, e.g. http://192.168.1.20:8765",
    )
    args = parser.parse_args()

    if not TOKEN:
        sys.exit(
            "pair-qr: ATTSD_TOKEN is not set -- Respond is disabled without it "
            "(ADR 0007). Set it before pairing."
        )

    host = args.host or default_host()
    uri = build_uri(host, TOKEN, args.name)

    qr = qrcode.QRCode(border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stdout, tty=sys.stdout.isatty())
    print(uri)


if __name__ == "__main__":
    main()
