#!/usr/bin/env python3
"""Health check for the running stack (`make status`).

Run after `make up`, before `make smoke`, and before every fault-injection run. Exits 0 only if
every check is OK, so callers can gate on it. `--json` prints the results for programs.

    cluster   all nodes Ready
    pods      every pod in every namespace Running with all containers ready
    frontend  the shop answers through its Service, from inside the cluster
    loadgen   the load generator is running with users
    metrics   frontend span metrics are fresh in Prometheus
    logs      Loki received log lines in the last 60s
    traces    Jaeger has frontend traces from the last 60s
    alerts    nothing firing in Prometheus
    flags     every demo fault flag is off (a fault run must start from baseline)
    host      inotify limits raised and IP forwarding on (run on the kind host)
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import kube


class Fail(Exception):
    pass


def check_cluster():
    nodes = kube.kubectl_json("get", "nodes")["items"]
    ready = [n for n in nodes
             if any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"]["conditions"])]
    if not nodes or len(ready) != len(nodes):
        raise Fail(f"{len(ready)}/{len(nodes)} nodes ready")
    return f"{len(ready)}/{len(nodes)} nodes ready"


def check_pods():
    pods = [p for p in kube.kubectl_json("get", "pods", "-A")["items"]
            if p["status"].get("phase") != "Succeeded"]  # finished Job pods aren't failures
    bad = []
    for p in pods:
        statuses = p["status"].get("containerStatuses") or []
        if p["status"].get("phase") != "Running" or not statuses or not all(c["ready"] for c in statuses):
            reason = next((c["state"]["waiting"]["reason"] for c in statuses if "waiting" in c["state"]),
                          p["status"].get("phase"))
            bad.append(f"{p['metadata']['namespace']}/{p['metadata']['name']} ({reason})")
    ok = len(pods) - len(bad)
    if bad:
        raise Fail(f"{ok}/{len(pods)} running; not ready: {', '.join(bad[:3])}{' …' if len(bad) > 3 else ''}")
    return f"{ok}/{len(pods)} running"


def check_frontend():
    # From inside the cluster through the Service, like real traffic: this exercises DNS and
    # kube-proxy, which the API-server proxy would bypass. Runs in our own webhook pod (it has
    # Python) so the result doesn't depend on any demo pod being up.
    code = kube.kubectl("-n", "observability", "exec", "deploy/alert-webhook", "--", "python", "-c",
                        "import urllib.request as u, urllib.error as e\n"
                        "try: print(u.urlopen('http://frontend-proxy.otel-demo:8080/', timeout=10).status)\n"
                        "except e.HTTPError as x: print(x.code)\n"
                        "except Exception as x: print(type(x).__name__)").strip()
    if code != "200":
        raise Fail(f"HTTP {code}")
    return "HTTP 200"


def check_loadgen():
    d = kube.proxy("otel-demo", "load-generator:8089", "/stats/requests")
    if d.get("state") != "running" or not d.get("user_count"):
        raise Fail(f"{d.get('state')}, {d.get('user_count', 0)} users")
    return "running"


def check_metrics():
    r = kube.prom_query('sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER"}[2m]))')
    rate = float(r[0]["value"][1]) if r else 0.0
    if rate <= 0:
        raise Fail("no frontend span metrics in the last 2m")
    return f"frontend req rate {rate:.1f}/s"


def check_logs():
    r = kube.proxy("observability", "loki:3100", "/loki/api/v1/query",
                   query='sum(count_over_time({service_name=~".+"}[60s]))', time=str(time.time_ns()))
    res = r["data"]["result"]
    n = int(float(res[0]["value"][1])) if res else 0
    if n == 0:
        raise Fail("no log lines in last 60s")
    return f"{n:,} lines in last 60s"


def check_traces():
    now_us = int(time.time() * 1e6)
    r = kube.proxy("otel-demo", "jaeger:16686", "/jaeger/ui/api/traces", service="frontend",
                   start=str(now_us - 60_000_000), end=str(now_us), limit="1")
    if not r.get("data"):
        raise Fail("no frontend traces in last 60s")
    return "frontend traces in last 60s"


def check_alerts():
    alerts = kube.proxy("otel-demo", "prometheus:9090", "/api/v1/alerts")["data"]["alerts"]
    firing = [a["labels"] for a in alerts if a["state"] == "firing"]
    pending = sum(a["state"] == "pending" for a in alerts)
    note = f" ({pending} pending)" if pending else ""
    if firing:
        names = ", ".join(f"{l['alertname']}{{{l.get('service_name') or l.get('pod', '')}}}" for l in firing[:3])
        raise Fail(f"{len(firing)} firing: {names}{note}")
    return f"0 firing{note}"


def check_flags():
    flags = kube.read_flags()["flags"]
    on = [f"{k}={v['defaultVariant']}" for k, v in sorted(flags.items()) if v["defaultVariant"] != "off"]
    if on:
        raise Fail(f"{len(on)} on: {', '.join(on[:3])}{' …' if len(on) > 3 else ''}")
    return f"all {len(flags)} off"


def check_host():
    # The two host settings that broke the cluster on 2026-10-06 (docs/dev-environment.md §3).
    def sysctl(key):
        with open(f"/proc/sys/{key.replace('.', '/')}") as f:
            return int(f.read().split()[0])
    problems = []
    if sysctl("fs.inotify.max_user_instances") < 512:
        problems.append("inotify max_user_instances < 512 (kube-proxy may crash-loop)")
    if sysctl("net.ipv4.ip_forward") != 1:
        problems.append("ip_forward=0 (kind nodes have no internet)")
    if problems:
        raise Fail("; ".join(problems) + " — run infra/bootstrap.sh")
    return "inotify limits ok, ip_forward on"


CHECKS = [("cluster", check_cluster), ("pods", check_pods), ("frontend", check_frontend),
          ("loadgen", check_loadgen), ("metrics", check_metrics), ("logs", check_logs),
          ("traces", check_traces), ("alerts", check_alerts),
          ("flags", check_flags), ("host", check_host)]


def run(fn):
    try:
        return "OK", fn()
    except Fail as e:
        return "FAIL", str(e)
    except RuntimeError as e:  # kubectl failed: unreachable API, missing service, ...
        return "FAIL", kube.clip(e, 120)
    except Exception as e:  # timeout, unexpected response
        return "FAIL", kube.clip(f"{type(e).__name__}: {e}", 120)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--context", help="kubectl context")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    args = ap.parse_args()
    kube.use_context(args.context)

    with ThreadPoolExecutor(len(CHECKS)) as pool:
        results = list(pool.map(run, [fn for _, fn in CHECKS]))
    rows = [(name, status, detail) for (name, _), (status, detail) in zip(CHECKS, results)]

    if args.json:
        print(json.dumps({"ok": all(s == "OK" for _, s, _ in rows),
                          "checks": [{"name": n, "status": s, "detail": d} for n, s, d in rows]}, indent=2))
    else:
        tty = sys.stdout.isatty()
        for name, status, detail in rows:
            label = f"{status:<4}"
            if tty:
                label = f"\033[{32 if status == 'OK' else 31}m{label}\033[0m"
            print(f"{name:<14} {label}  {detail}")
    sys.exit(0 if all(s == "OK" for _, s, _ in rows) else 1)


if __name__ == "__main__":
    main()
