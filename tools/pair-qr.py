#!/usr/bin/env python3
"""Render the *running* server's pairing URI as a QR code the Android app can
scan.

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

The port and the token are never taken from *this shell's* environment --
`ATTSD_TOKEN` exported here could be stale, unset, or simply not what the
server actually running right now was started with, and a QR built from the
wrong one fails on the phone as a 401 far from its cause. Instead this finds
the live `server.py` process with `ps`, reads the TCP port it is actually
bound to with `lsof`, and reads `ATTSD_TOKEN` out of *that process's own*
environment with `ps -E` -- the same variable `server.py` reads at startup
(see ADR 0007). All of that is local process inspection, same machine, same
user; nothing here talks to the server over the network, writes the token to
a file, or serves it from an endpoint. The token is never logged or written
to disk; it only ever reaches the terminal inside the QR code and the one
printed fallback line, both already private to whoever is sitting at this
Mac.

    tools/pair-qr.py
    tools/pair-qr.py --name Home
    tools/pair-qr.py --host http://192.168.1.20:8765
"""

import argparse
import os
import re
import subprocess
import sys
from urllib.parse import quote

try:
    import qrcode
except ImportError:
    sys.exit(
        "pair-qr: requires the 'qrcode' package -- pip install -r requirements.txt"
    )

# Last-resort fallback only -- real answers come from the live process (see
# _listening_port and _process_env below), never from a guess baked in here.
DEFAULT_PORT = "8765"

SERVER_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py"
)

NO_SERVER_HINT = (
    "pair-qr: no running attsd server found -- start one first, e.g. "
    "`launchctl kickstart -k gui/$UID/com.saivenky.attsd` or `python3 server.py`"
)


def _find_server_pid() -> int | None:
    """Pid of the running server.py for *this* repo, however it was started
    -- launchd (see launchd/com.saivenky.attsd.plist) or a bare `python3
    server.py`. `ps` is the one place both show up the same way, so it is
    the discovery mechanism rather than a pidfile this repo does not keep."""
    out = subprocess.run(
        ["ps", "-Ao", "pid=,command="], capture_output=True, text=True, check=False
    )
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_s, _, command = line.partition(" ")
        if SERVER_PY in command:
            try:
                return int(pid_s)
            except ValueError:
                continue
    return None


def _listening_port(pid: int) -> str | None:
    """The TCP port server.py is actually bound to right now, read off its
    live socket with `lsof` -- not trusted from ATTSD_PORT or a default,
    since either could be stale relative to what is really listening."""
    out = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-Pn"],
        capture_output=True,
        text=True,
        check=False,
    )
    m = re.search(r":(\d+)\s*\(LISTEN\)", out.stdout)
    return m.group(1) if m else None


def _process_env(pid: int) -> dict[str, str]:
    """Env vars of the running server process itself -- `ps -E` on macOS
    prints a process's own environment appended to its command line. This is
    the only honest source for ATTSD_TOKEN: the invoking shell's environment
    is not necessarily what the server was started with."""
    out = subprocess.run(
        ["ps", "-E", "-ww", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    command = out.stdout.strip()
    env: dict[str, str] = {}
    matches = list(re.finditer(r"(?:^|\s)([A-Z_][A-Za-z0-9_]*)=", command))
    for i, m in enumerate(matches):
        start, key = m.end(), m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(command)
        env[key] = command[start:end].strip()
    return env


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


def default_host(port: str) -> str:
    ip = _tailscale_ip()
    if not ip:
        sys.exit(
            "pair-qr: could not read a Tailscale IPv4 (`tailscale ip -4` failed -- "
            "is Tailscale installed and running?). Pass --host explicitly, e.g. "
            "--host http://192.168.1.20:8765"
        )
    return f"http://{ip}:{port}"


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

    pid = _find_server_pid()
    if pid is None:
        sys.exit(NO_SERVER_HINT)

    env = _process_env(pid)
    token = env.get("ATTSD_TOKEN", "")
    if not token:
        sys.exit(
            f"pair-qr: the running attsd server (pid {pid}) has no ATTSD_TOKEN "
            "set -- Respond is disabled without it (ADR 0007). Set it before "
            "pairing."
        )

    port = _listening_port(pid) or env.get("ATTSD_PORT", DEFAULT_PORT)
    host = args.host or default_host(port)
    uri = build_uri(host, token, args.name)

    qr = qrcode.QRCode(border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stdout, tty=sys.stdout.isatty())
    print(uri)


if __name__ == "__main__":
    main()
