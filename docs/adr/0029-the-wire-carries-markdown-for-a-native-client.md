# The wire carries markdown for a native client

`GET /api/board?fmt=md` gives each prose **Turn** of the **Scrollback** its
markdown source (`md`) in place of the HTML [ADR 0006](0006-board-context-rendered-server-side.md)
renders (`html`). Without the parameter the payload is unchanged, so the **Board**
is untouched. The markdown renderer moves client-side for the client that asks.

## Context

The Board is being replaced by a native Android client (Kotlin + Compose) in a
separate repo, `attsd-native`. The reason is not technical: the browser is the
thing being escaped. A home-screen icon and no browser chrome was the goal; a PWA
was the first candidate and lost to a native app, which needs no HTTPS (secure
context is a browser rule, not a network one — one `network_security_config.xml`
permits cleartext to the MagicDNS name) and no push service to notify later.
[ADR 0001](0001-tailscale-as-launcher-transport.md)'s posture is untouched: still
a pure tailnet client, still no public ingress.

That client cannot consume `html`. ADR 0006 renders a Turn server-side to
escape-first HTML precisely so the Board can `innerHTML` it through one audited
sink, and [ADR 0014](0014-the-focus-is-a-scrollback.md) widened that from one
field to N. **Compose has no HTML sink at all.** The escaping guarantee that made
server-side rendering correct is a guarantee about a browser, and there is no
browser here.

Two facts bound the change:

- **The two clients live in two repos.** A payload change in `attsd` and its
  consumer in `attsd-native` cannot land in one commit, so a format the app
  cannot parse is a Gradle build and an `adb install` away from being fixed.
- **The Board is not retired by this decision.** Whether `web/` survives is a
  live question, and this ADR deliberately does not answer it. Anything that
  forced the answer now would be deciding it by accident.

## Considered options

- **Parse the HTML in Kotlin.** Rejected: it reconstructs markdown from a lossy
  rendering of it, and every future change to `_md_to_html` silently breaks a
  client in another repo.
- **Add `md` beside `html` on every Turn, always.** Rejected: every Turn crosses
  the wire twice, forever, so that a client can ignore one of them. The
  scrollback is up to 14 turns of clipped prose per poll.
- **Content negotiation on `Accept`.** Rejected: the format is not a media type
  — the response is `application/json` either way — and an `Accept` header is
  invisible in a URL you paste into `curl` while debugging from a phone.
- **Retire `html` outright; every client renders markdown.** Rejected *for now*,
  not on merit: it is the right end state if `web/` is retired, and the wrong one
  if it isn't. The parameter costs little enough to wait.

## Decision

One query parameter, `fmt`, valid values `html` (default) and `md`.

**The clip is outside the format branch.** `_clip(text, _TURN_MAX)` happens once
and both formats window the same text. Clipping per-format would let the app and
the Board disagree about where a long turn ends — the same Session read two ways.

**An unknown `fmt` is a 400, never a default.** A typo that silently served HTML
would break the app somewhere far from the cause, on a phone, with no console to
read it in. The failure has to name itself at the door. This is the same
reasoning as [ADR 0021](0021-the-renderer-is-unversioned-so-every-parse-fails-loudly.md).

**A `work` entry and a `command` entry are byte-identical across formats.**
Neither was ever HTML, so neither has a format. This is asserted, not assumed.

**The ETag needs no help.** It is a hash of the body and the two bodies differ,
so revalidation keeps working per-format with no cache-key change.

## Consequences

`_md_to_html` stops being the only renderer of a Turn. Its escaping guarantee
still covers every Board pixel, but it no longer covers everything a human reads
— the Compose renderer is now a second implementation of the same markdown, and
the two can drift. The mitigation is that they are testable against the same
source string, not that they share code; they cannot share code across a process
and a language boundary.

The app is a cross-repo consumer of a payload that no longer changes atomically
with it. The app therefore pins what it expects and says "server too new —
rebuild the app" rather than rendering a blank screen.

## Escape hatch

If `web/` is retired, delete the `html` branch and the parameter with it: `md`
becomes the only format and `_md_to_html` goes with the Board. That is a
deletion, not a migration, which is the point of having added a parameter rather
than a second field.
