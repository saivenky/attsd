# 01 — The wire carries markdown for a native client

**What to build:** `GET /api/board?fmt=md` returns each **Turn** of the
**Focus**'s **Scrollback** as its markdown source (`md`) instead of
server-rendered HTML (`html`). Without the parameter the payload is byte-for-byte
what it is today, so the web **Board** is untouched.

A native client cannot consume the `html` ADR 0006 renders — Compose has no HTML
sink — so the renderer has to move client-side for that client only. The
parameter is how one server feeds two clients without either constraining the
other.

**Blocked by:** None — can start immediately.

**Status:** landed

- [ ] `GET /api/board` with no `fmt` is unchanged: Turns carry `html`, no `md` key.
- [ ] `GET /api/board?fmt=md` gives prose Turns `md` (the clipped markdown source) and no `html`.
- [ ] A **work run** entry (`role: "work"`) and a `command` entry are identical under both formats — neither was ever HTML.
- [ ] The clip at `_TURN_MAX` applies to both, so the two formats window the same text.
- [ ] The ETag differs between the two formats, and `If-None-Match` still 304s within one format.
- [ ] An unknown `fmt` value is rejected rather than silently serving HTML.
- [ ] An ADR records the decision and what it does not decide (retiring `web/`).
