# demo-runs/code-template/

Stable snapshot of the target files AgentMES's pipeline rewrites during
a demo run. Every Stage 7 Deploy PR branches off `main`, reads these
files as the "before" state, and commits the fixed versions into
`demo-runs/runs/<run_id>/` alongside a unified diff and the stage
receipts.

**Do not edit this directory manually.** It's the golden reference the
demo runs compute their diffs against. If you change the template, the
diffs in every subsequent PR will shift.

## Contents

- `auth/middleware.py` — the race-condition version of
  `OAuthTokenMiddleware` that `test_oauth_token_refresh` flakes
  against. TKT-001's Build stage rewrites this with a single-flight
  refresh lock pattern.
