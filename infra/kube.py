"""Small kubectl helpers shared by infra/ scripts (smoke.py, status.py).

Everything goes through kubectl: the API server's service proxy for HTTP APIs, and
`kubectl exec/logs` for the rest, so no port-forwards are needed.
"""
import json
import subprocess
import time
import urllib.parse

_ctx = []
FLAG_FILE = "/app/data/demo.flagd.json"  # flagd's runtime copy; the ConfigMap is only read at pod start


def use_context(context):
    _ctx[:] = ["--context", context] if context else []


def kubectl(*args, stdin=None, timeout=60):
    r = subprocess.run(["kubectl", *_ctx, *args], input=stdin, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().removeprefix("error: ").removeprefix("Error from server ")[:300] or f"kubectl exited {r.returncode}")
    return r.stdout


def kubectl_json(*args):
    return json.loads(kubectl(*args, "-o", "json"))


def proxy(ns, svc, path, **params):
    """GET through the API server's service proxy and decode JSON."""
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    return json.loads(kubectl("get", "--raw", f"/api/v1/namespaces/{ns}/services/{svc}/proxy{path}{query}"))


def prom_query(q):
    return proxy("otel-demo", "prometheus:9090", "/api/v1/query", query=q)["data"]["result"]


def read_flags():
    return json.loads(kubectl("-n", "otel-demo", "exec", "deploy/flagd", "-c", "flagd-ui", "--", "cat", FLAG_FILE))


def write_flags(cfg):
    kubectl("-n", "otel-demo", "exec", "-i", "deploy/flagd", "-c", "flagd-ui", "--",
            "sh", "-c", f"cat > {FLAG_FILE}", stdin=json.dumps(cfg, indent=2))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def clip(s, n=140):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"
