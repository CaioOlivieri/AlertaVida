#!/usr/bin/env bash
# deploy/validate-drain.sh — E2 test: proves systemctl restart drains an
# in-flight ingestion round instead of killing it mid-write (the #78 design
# point: KillSignal=SIGINT + a real SIGTERM handler + shutdown(wait=True)).
#
# A real round can finish in well under a second, so a single restart can
# easily land AFTER the round already ended — the drain message logs
# unconditionally in that case too, so its mere presence proves nothing.
# This script only accepts a PASS when it observes, in strict order, all
# after the moment the restart was issued: "Iniciando rodada" already
# in flight -> "aguardando rodada em andamento encerrar..." -> "Rodada
# concluída" -> a fresh "Scheduler iniciado." Anything else (round already
# finished before the restart, no drain message, no restart afterward) is
# treated as an inconclusive race and retried, up to MAX_ATTEMPTS.
#
# Runtime: normally seconds — a healthy round is caught mid-flight on the
# first or second attempt. Worst case, if the service hangs and never logs
# a restart, it waits MAX_ATTEMPTS x DRAIN_TIMEOUT (5 x 370s ≈ 31 min)
# before reporting FAILED. That is the script working, not hanging — don't
# kill it.
#
# Requires deploy/seed-test-db.sh to have already put a disposable copy at
# /var/lib/alertavida/alertavida.db. Leaves the service running afterward.
# Run with:
#
#   sudo bash deploy/validate-drain.sh [output-file]
#
set -euo pipefail

OUT_FILE="${1:-/tmp/alertavida-drain-validation.log}"
MAX_ATTEMPTS=5

echo "== Ensuring the service is enabled =="
systemctl daemon-reload
systemctl enable alertavida.service >/dev/null

JOURNAL_TAIL="$(mktemp)"
trap 'rm -f "$JOURNAL_TAIL"' EXIT

echo "== Following the journal =="
journalctl -u alertavida.service -f --no-pager -o short-iso > "$JOURNAL_TAIL" &
FOLLOW_PID=$!
sleep 0.3

echo "== Initial restart (each restart schedules an immediate round via next_run_time=now) =="
systemctl restart alertavida.service

SUCCESS=false
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    SEARCH_FROM=$(wc -l < "$JOURNAL_TAIL")
    FOUND_START=""
    for _ in $(seq 1 300); do
        REL="$(tail -n +"$((SEARCH_FROM + 1))" "$JOURNAL_TAIL" | grep -n "Iniciando rodada" | head -n1 | cut -d: -f1 || true)"
        if [ -n "$REL" ]; then
            FOUND_START=$((SEARCH_FROM + REL))
            break
        fi
        sleep 0.02
    done

    if [ -z "$FOUND_START" ]; then
        echo "Attempt $attempt/$MAX_ATTEMPTS: round never started within 6s — service may have failed to start." >&2
        break
    fi

    LINE_BEFORE=$(wc -l < "$JOURNAL_TAIL")
    echo "Attempt $attempt/$MAX_ATTEMPTS: round in flight (started at line $FOUND_START) — restarting now"
    systemctl restart alertavida.service

    # Poll for the restarted process's own startup line instead of a fixed
    # sleep — a genuine drain can legitimately take up to the worst-case
    # round duration (~268s, see TimeoutStopSec's comment in
    # alertavida.service). A fixed short sleep would misreport a real,
    # still-draining round as a failure.
    DRAIN_TIMEOUT=370
    DEADLINE=$(( $(date +%s) + DRAIN_TIMEOUT ))
    RESTARTED_LINE=""
    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        RESTARTED_LINE="$(tail -n +"$((LINE_BEFORE + 1))" "$JOURNAL_TAIL" | grep -n "Scheduler iniciado" | head -n1 | cut -d: -f1 || true)"
        if [ -n "$RESTARTED_LINE" ]; then
            break
        fi
        sleep 0.2
    done

    AFTER="$(tail -n +"$((LINE_BEFORE + 1))" "$JOURNAL_TAIL")"
    DRAIN_LINE="$(echo "$AFTER" | grep -n "aguardando rodada em andamento encerrar" | head -n1 | cut -d: -f1 || true)"
    CONCLUDED_LINE="$(echo "$AFTER" | grep -n "Rodada concluída" | head -n1 | cut -d: -f1 || true)"

    if [ -z "$RESTARTED_LINE" ]; then
        echo "Attempt $attempt/$MAX_ATTEMPTS: no fresh 'Scheduler iniciado.' within ${DRAIN_TIMEOUT}s of the restart — service may be stuck or was SIGKILLed. Retrying." >&2
        continue
    fi
    if [ -z "$CONCLUDED_LINE" ]; then
        echo "Attempt $attempt/$MAX_ATTEMPTS: no 'Rodada concluída' observed before the restart completed — retrying." >&2
        continue
    fi
    if [ -z "$DRAIN_LINE" ] || [ "$DRAIN_LINE" -ge "$CONCLUDED_LINE" ]; then
        echo "Attempt $attempt/$MAX_ATTEMPTS: round had already finished before (or without) a drain message — too fast to catch mid-round, retrying." >&2
        continue
    fi
    if [ "$RESTARTED_LINE" -le "$CONCLUDED_LINE" ]; then
        echo "Attempt $attempt/$MAX_ATTEMPTS: fresh 'Scheduler iniciado.' logged before the drained round completed (out of order) — retrying." >&2
        continue
    fi

    echo "Attempt $attempt/$MAX_ATTEMPTS: PASS — Iniciando rodada -> aguardando rodada em andamento encerrar -> Rodada concluída -> Scheduler iniciado, strictly in that order, all after the restart was issued."
    SUCCESS=true
    break
done

kill "$FOLLOW_PID" 2>/dev/null || true
wait "$FOLLOW_PID" 2>/dev/null || true

{
    echo "### systemctl status alertavida.service"
    systemctl status alertavida.service --no-pager
    echo
    echo "### journalctl -u alertavida.service (full capture across all attempts)"
    cat "$JOURNAL_TAIL"
} | tee "$OUT_FILE"

echo
echo "Saved to $OUT_FILE"

if [ "$SUCCESS" != true ]; then
    echo "FAILED: could not observe a genuine mid-round drain in $MAX_ATTEMPTS attempts." >&2
    exit 1
fi
