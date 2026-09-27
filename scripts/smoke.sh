#!/usr/bin/env bash
# ToolGate end-to-end smoke test.
# Creates an isolated state dir, registers a CLI tool and an endpoint tool
# (backed by a local mock upstream), starts the gateway and calls both tools
# over HTTP.  Exits non-zero if any step fails.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
export TOOLGATE_HOME="$WORK"
PORT=18923
UP_PORT=18924
cleanup() {
  [[ -n "${GW_PID:-}" ]] && kill "$GW_PID" 2>/dev/null || true
  [[ -n "${UP_PID:-}" ]] && kill "$UP_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

echo ">> workspace: $WORK"

# mock upstream
cat > "$WORK/up.py" <<'PY'
import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    def _send(self):
        body = json.dumps({"ok": True, "path": self.path,
                           "key": self.headers.get("X-Api-Key")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    do_GET = _Send = _send
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(__import__("os").environ["UP_PORT"])), H).serve_forever()
PY
UP_PORT=$UP_PORT python3 "$WORK/up.py" &
UP_PID=$!

cd "$ROOT"
TG="python3 -m toolgate"

echo ">> keygen"; $TG keygen >/dev/null

echo ">> create admin token"
ADMIN=$($TG tokens create myadmin --scope admin | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

echo ">> store credential"
$TG creds set mysecret "s3cr3t" --description "demo" >/dev/null

echo ">> register CLI tool"
$TG tools add-cli echocli \
  --argv "python3 -c \"import os,sys,json; print(json.dumps({'token':os.environ.get('MY_TOKEN'),'argv':sys.argv[1:]}))\"" \
  --env-bind "mysecret:MY_TOKEN" \
  --named "mode:--mode" --free-args >/dev/null

echo ">> register endpoint tool"
$TG tools add-endpoint myapi --base-url "http://127.0.0.1:$UP_PORT" \
  --header-bind "mysecret:X-Api-Key" >/dev/null

echo ">> start gateway"
$TG serve --port "$PORT" >/dev/null &
GW_PID=$!
sleep 1.5

echo ">> create call token"
CALL=$($TG tokens create mycall --scope call | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

echo ">> list tools (call token)"
curl -s -H "Authorization: Bearer $CALL" "http://127.0.0.1:$PORT/v1/tools" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);assert d['count']==2,d;print('   tools:',[t['name'] for t in d['tools']])"

echo ">> call CLI tool over HTTP"
curl -s -X POST -H "Authorization: Bearer $CALL" -H "Content-Type: application/json" \
  -d '{"params":{"mode":"json"},"args":["alpha","beta"]}' \
  "http://127.0.0.1:$PORT/v1/call/echocli" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);assert d['exit_code']==0,d;out=json.loads(d['stdout']);assert out['token']=='s3cr3t',out;assert out['argv']==['--mode','json','alpha','beta'],out;print('   cli ok:',out)"

echo ">> call endpoint via transparent proxy"
curl -s -H "Authorization: Bearer $CALL" "http://127.0.0.1:$PORT/v1/tool/myapi/ping?x=1" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);assert d['key']=='s3cr3t',d;assert d['path']=='/ping?x=1',d;print('   endpoint ok:',d)"

echo ">> local call (no HTTP)"
$TG call echocli --params '{"mode":"yaml"}' --arguments one \
  | python3 -c "import sys,json;d=json.load(sys.stdin);assert d['exit_code']==0,d;print('   local ok')"

echo ">> auth rejection check"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/v1/tools")
[[ "$code" == "401" ]] && echo "   no-token -> 401"

echo
echo "SMOKE TEST PASSED ✅"
