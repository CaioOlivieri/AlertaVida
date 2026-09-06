status: implemented
sources: `scripts/weathernext_surge_watch.py`, `scripts/weathernext_cemaden_capture.py`, `deploy/weathernext-*.{service,timer}`, issue #70, [[decisions/weathernext-anticipation-not-datasource]], [[raw/analise-weathernext-skill-2026-08-24]]
updated: 2026-09-05

# WeatherNext surge watch — design (issue #70)

Phase B of the WeatherNext track. #69's qualified PASS
([[decisions/weathernext-anticipation-not-datasource]]) cleared the track to
proceed; this page records the four design decisions #70 required before any
code, each resolved with the maintainer during the session rather than
assumed.

## Why this exists

The Round 2 centroide-vs-ponto-de-risco discriminator
([[projects/layer-5-correlation]]) needs several CEMADEN alerts inside the
SAME municipality — identical coordinates across them ⇒ centroid semantics,
varying ⇒ risk-point semantics. As of the 2026-09-04 audit, CEMADEN in the
database held 7 alerts across 15 days, 7 distinct municipalities, zero with
more than one alert: the discriminator has literally nothing to run against
today. A rain surge is the only realistic way that changes, and it also
happens to be exactly when `correlacao_observacoes` (#60) accumulates the
candidate pairs dormant #63 needs to calibrate. Waiting on luck to notice a
surge risks missing it entirely; this issue makes watching for one automatic.

## Decision 1 — deterministic mean-threshold indicator, not ensemble probability

The original issue text asked for "probability of extreme precipitation per
region" derived from the 64-member ensemble. Ruled out on cost alone: the
ensemble table (`weathernext_2.weathernext_2_0_0`) costs 189–191 GB per
daily partition/variable (measured in #69's analysis) — run once a day for
30 days, that is 5.7–5.9 TB/month, several times over the entire 1 TiB free
tier. The mean table (`weathernext_2_mean.weathernext_2_0_0_mean`) costs
4.19 GB per partition/variable — 30 days is 126 GB/month, 12.6% of the free
tier, actually affordable.

Consequence, not a workaround: without the ensemble, there is no
per-member spread to compute a probability from. The artifact carries a
**deterministic indicator** instead — summed `total_precipitation_6hr`
(the mean table's only precipitation field) over the next 48h, per 0.25°
grid cell, checked against a threshold. This is not a forecast published to
end users; it is an internal trigger deciding whether to turn on
high-frequency CEMADEN capture. For that purpose a deterministic threshold
crossing is exactly as actionable as a probability would have been — #69's
own verdict already reads the 78% real-event hit rate as "catches roughly 4
surge events out of 5, against catching zero today," which is the same
framing this indicator inherits.

**`SURGE_WATCH_THRESHOLD_MM_48H = 50.0`, provisional** — labelled as such in
code (`scripts/weathernext_surge_watch.py`), same discipline as
`domain/correlacao.py`'s scoring constants. A round, deliberately inclusive
starting value (a false-positive here just means an extra day of raw
capture; a false negative means missing the season), **not** derived from
any external classification or from this project's own data — no surge has
been observed yet to calibrate against, and calibration is explicitly out of
scope for #70, same posture as #63 for the correlation weights. Revisit once
real surge data exists to check against.

## Decision 2 — the `bq` CLI via `subprocess`, not the Python client library

Presented as a 3-way choice (bq CLI / `uv run --with google-cloud-bigquery` /
new optional dependency-group). The maintainer picked the `bq` CLI, for a
reason not obvious from the transport question alone:
**`--maximum_bytes_billed` is a command-line flag, not a `QueryJobConfig`
field** — far harder to silently drop in a future refactor than a
constructor argument buried in a client object. It is also literally the
tool the whole #69 measurement was performed with
([[raw/analise-weathernext-skill-2026-08-24]]), zero new dependency tree,
zero `uv.lock` churn, and CI stays untouched (no dependency-group was
authorized or needed).

**Failure-mode discipline, decided explicitly:** the cost guard tripping
(`--maximum_bytes_billed` exceeded) is the guard *working*, not a bug — it
is logged and the run is skipped, previous artifact left untouched. Any
other `bq` failure (authentication, network, malformed SQL) is a real
defect and propagates, giving the systemd unit a failed status. Verified
empirically against the real project on 2026-09-05, not inferred (wiki
rule 1) — a live query run with a deliberately tiny
`--maximum_bytes_billed=100` produced:

```
BigQuery error in query operation: Error processing job
'weathernexttest-506315:bqjob_...': Query exceeded limit for bytes billed:
100. 33554432 or higher required.
```

with `totalBytesBilled: null` and `errorResult.reason:
"bytesBilledLimitExceeded"` on the job record — confirming the same
"aborts, bills 0" behavior already noted for this project. `"exceeded limit
for bytes billed"` (case-insensitive substring of that real message) is
what `executar_query_bq` matches on to raise `OrcamentoExcedidoError`
instead of `subprocess.CalledProcessError`.

## Decision 3 — runs as the maintainer, not `alertavida`

Corrects an assumption made earlier in the same session (a delta note that
assumed the capture would run under the `alertavida` systemd service user
and therefore need its own directory under `/var/lib/alertavida`, mirroring
the database's group-permission treatment). That premise was wrong, caught
by the maintainer before any code was written: `bq` needs Application
Default Credentials, measured on this host at
`~/.config/gcloud/application_default_credentials.json`, mode `-rw-------`
(owner-only, personal OAuth refresh token, not a service-account key). The
maintainer's home directory is `drwxr-x---` — `alertavida` cannot traverse
into it regardless of any other permission — so a systemd unit with
`User=alertavida` (the pattern every existing unit in `deploy/` uses) would
fail on every single run for lack of credentials, independent of which
BigQuery client was chosen.

**Decided: the WeatherNext track runs as the maintainer.**

- It never reads or writes the production database — only produces a local
  JSON artifact and raw CEMADEN capture files. No reason to share the
  collector's service identity.
- The alternative (copy the maintainer's personal OAuth token into a
  location `alertavida` can read) spreads a personal credential to another
  account on a host that is already a stopgap
  ([[decisions/systemd-vps-deployment]]) — not justified by the gain.
- A dedicated service account with a key on disk is a real option, but is
  its own GCP decision, not worth opening for an experimental track on a
  temporary host. Deferred to Phase 2 if the surge watch survives that far.

**Consequence:** the artifact and raw captures live in this checkout's own
`data/` (gitignored), exactly as the original issue text specified — no
`/var/lib/alertavida` involvement, no `deploy/install.sh` change needed.

## Decision 4 — user systemd units (`systemctl --user`), not system units

Scheduling is the maintainer's own action (this issue only delivers files
and instructions — see `deploy/README.md`), but the *shape* of the unit was
a design question resolved here: system units under `/etc/systemd/system`
with `User=<maintainer>` (root-installed, matching every existing pattern)
versus user units under `~/.config/systemd/user/` (no root to install or
enable).

**Decided: user units.** Hard constraint driving the choice, not a style
preference: **no username or `/home/<x>` path may appear in a versioned
file** — the Phase 2 host will have a different user, so a hardcoded name
would be a portability bug, not just a leak. A system unit needs an explicit
`User=` line naming that account; a user unit has none — it runs as whoever
installs it, and its `WorkingDirectory=`/`ExecStart=` use systemd's `%h`
specifier (resolved to the invoking user's home at *activation* time) in
place of any literal path. `grep -rn "/home/" deploy/` is empty by
construction, not by post-hoc scrubbing.

Cost of this choice, documented in `deploy/README.md`: a user unit only
survives logout if `loginctl enable-linger <user>` has been run once
(itself a root action, one time only). On this WSL host that still does not
survive a Windows reboot or `wsl --shutdown` — the same caveat already
recorded for the whole Phase 1 deployment
([[decisions/systemd-vps-deployment]]); nothing new introduced by this
issue.

Two independent timers, deliberately different cadence philosophy:

- `weathernext-surge-watch.timer` — `OnCalendar=daily`, `Persistent=true`
  (a missed day during a WSL outage still runs on next wake — every day of
  season missed is data that does not come back, per the 2026-09-04 audit).
- `weathernext-cemaden-capture.timer` — `OnCalendar=*:0/5`, `Persistent=false`
  (matches the production ingestion poll's own 5-minute cadence — "high
  frequency" is relative to the once-a-day forecast check, not to what the
  collector already does against the same CEMADEN endpoint; a missed tick
  is not worth catching up, the next one is 5 minutes away). Each tick is a
  no-op with zero network calls unless `watch_mode` is on
  (`scripts/weathernext_cemaden_capture.py::em_modo_vigilancia`), so running
  it always-on costs nothing outside an actual surge.

## Why raw capture, given production ingestion already persists every alert

`ingestion/orquestrador.py` already polls CEMADEN every 5 minutes and
persists every alert it sees. But `database.py`'s `UNIQUE (fonte,
cod_alerta)` means a re-issued alert **updates in place** — if CEMADEN
republishes the same `cod_alerta` with different coordinates over time (the
exact signal the discriminator needs — does a "same" alert's point move, or
stay fixed?), the production DB overwrites the earlier value and the history
is gone. Raw capture keeps every timestamped snapshot untouched, independent
of what the domain layer later decides to do with it — deliberately outside
`ingestion/orquestrador.py` and `domain/correlacao.py`, reusing only
`fetch_com_retry`/`parse_json` (transport + JSON decode, no
`_montar_alerta`) so the existing retry/backoff invariants apply unchanged.

## Cost — real measured, not just the dry-run bound

Dry-run bound used for `--maximum_bytes_billed` (4,200,000,000, a rounded-up
margin over the measured 4,186,183,680-byte partition/variable cost from
[[raw/analise-weathernext-skill-2026-08-24]]) is a **safety cap**, not a cost
prediction — same pattern already established there: the dry-run figure is
pessimistic, real execution is pruned much harder by clustering. Measured
against the real project on 2026-09-05, running the actual production query
shape (Brazil bbox via `ST_INTERSECTSBOX`, current 48h window, latest
available `init_time`):

```
billed:    176,160,768 bytes  (~176 MB)
processed: 175,346,640 bytes
cacheHit:  false (genuine execution, not a repeat)
```

176 MB/day × 30 ≈ 5.28 GB/month ≈ **0.5% of the 1 TiB free tier** — well
below the 12.6% conservative budget the cost decision above is based on.
25,758 grid cells evaluated inside the Brazil bbox, 0 above threshold on
this date (early September, outside the Oct–Mar rainy season — expected).

## Open items carried forward, not re-decided here

- Threshold calibration — explicitly out of scope for #70, same as #63.
- Service-account credential for Phase 2 — deferred, noted under Decision 3.
- Whether 50mm/48h is the right band for the *capture* trigger (as opposed
  to a user-facing alert) will only be answerable once a real surge is
  observed against it.
