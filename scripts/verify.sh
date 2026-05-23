#!/usr/bin/env bash
# Automated verification for yt-grabber (PLAN.md checklist).
set -euo pipefail

UI_URL="${UI_URL:-http://localhost:8080}"
API_URL="${API_URL:-http://localhost:8001}"
COMPOSE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$COMPOSE_DIR"

pass=0
fail=0

ok() { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1"; fail=$((fail + 1)); }

echo "=== yt-grabber verification ==="
echo "UI:  $UI_URL"
echo "API: $API_URL"
echo

echo "[1] Containers running"
if docker compose ps --status running | grep -q backend && docker compose ps --status running | grep -q frontend; then
  ok "backend + frontend are up"
else
  bad "containers not running — run: docker compose up -d"
  docker compose ps -a
  exit 1
fi

echo "[2] UI loads (Download + Transcribe sections)"
html=$(curl -fsS "$UI_URL/")
if echo "$html" | grep -q 'id="download-section"' && echo "$html" | grep -q 'id="transcribe-section"'; then
  ok "index.html served with both sections"
else
  bad "UI missing expected sections"
fi

echo "[3] API proxy via nginx"
code=$(curl -s -o /dev/null -w "%{http_code}" "$UI_URL/api/files")
if [ "$code" = "200" ]; then
  ok "GET /api/files via UI proxy → $code"
else
  bad "GET /api/files via UI proxy → $code"
fi

echo "[4] API docs (direct backend)"
code=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/docs")
if [ "$code" = "200" ]; then
  ok "GET /docs → $code"
else
  bad "GET /docs → $code"
fi

echo "[5] POST /api/info (YouTube metadata)"
INFO_BODY='{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw"}'
info=$(curl -fsS -X POST "$API_URL/api/info" -H "Content-Type: application/json" -d "$INFO_BODY") || info=""
if echo "$info" | grep -q '"title"' && echo "$info" | grep -q 'available_qualities'; then
  ok "video info returned"
else
  bad "POST /api/info failed (network or yt-dlp?)"
  echo "    response: ${info:0:200}"
fi

echo "[6] Audio download job"
DL_BODY='{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw","type":"audio"}'
dl=$(curl -fsS -X POST "$API_URL/api/download" -H "Content-Type: application/json" -d "$DL_BODY") || dl=""
job_id=$(echo "$dl" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || true)
if [ -z "$job_id" ]; then
  bad "POST /api/download did not return job_id"
else
  ok "download job started: $job_id"
  echo "    waiting for download (up to 120s)..."
  done=0
  for _ in $(seq 1 120); do
    sleep 1
    job=$(curl -fsS "$API_URL/api/jobs/$job_id" 2>/dev/null || echo '{}')
    status=$(echo "$job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
  if [ "$status" = "done" ]; then
      filename=$(echo "$job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || true)
      ok "download finished: $filename"
      done=1
      break
    fi
    if [ "$status" = "error" ]; then
      err=$(echo "$job" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))" 2>/dev/null || true)
      bad "download error: $err"
      done=1
      break
    fi
  done
  if [ "$done" = "0" ]; then
    bad "download timed out"
    filename=""
  fi
fi

if [ -n "${filename:-}" ]; then
  echo "[7] Transcribe (model base)"
  tr=$(curl -fsS -X POST "$API_URL/api/transcribe" \
    -H "Content-Type: application/json" \
    -d "{\"filename\":\"$filename\",\"model\":\"base\"}") || tr=""
  tr_id=$(echo "$tr" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || true)
  if [ -z "$tr_id" ]; then
    bad "POST /api/transcribe failed"
  else
    ok "transcribe job started: $tr_id"
    echo "    waiting for transcription (up to 300s)..."
    tdone=0
    for _ in $(seq 1 300); do
      sleep 1
      tjob=$(curl -fsS "$API_URL/api/transcribe/$tr_id" 2>/dev/null || echo '{}')
      tstatus=$(echo "$tjob" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
      if [ "$tstatus" = "done" ]; then
        ok "transcription finished"
        tdone=1
        break
      fi
      if [ "$tstatus" = "error" ]; then
        terr=$(echo "$tjob" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))" 2>/dev/null || true)
        bad "transcribe error: $terr"
        tdone=1
        break
      fi
    done
    if [ "$tdone" = "0" ]; then
      bad "transcription timed out"
      tr_id=""
    fi
  fi

  if [ -n "${tr_id:-}" ]; then
    echo "[8] Export TXT / PDF / JSON"
    for fmt in txt pdf json; do
      out="/tmp/yt-grabber-verify.$fmt"
      code=$(curl -s -o "$out" -w "%{http_code}" -X POST "$API_URL/api/export" \
        -H "Content-Type: application/json" \
        -d "{\"job_id\":\"$tr_id\",\"format\":\"$fmt\",\"title\":\"Verify\"}")
      if [ "$code" = "200" ] && [ -s "$out" ]; then
        ok "export $fmt ($(wc -c <"$out" | tr -d ' ') bytes)"
      else
        bad "export $fmt → HTTP $code"
      fi
    done
  fi
else
  echo "[7–8] Skipped (no downloaded file)"
fi

echo
echo "=== Results: $pass passed, $fail failed ==="
[ "$fail" -eq 0 ]
