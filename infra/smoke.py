#!/usr/bin/env python3
"""End-to-end smoke test with a real fault (`make smoke`).

1. Turn on a demo failure flag (paymentFailure=100%).
2. Wait for ServiceHighErrorRate{service_name="payment"} to reach the webhook receiver.
3. Confirm the fault is visible in Loki (error logs) and Jaeger (error spans), and that a
   trace_id from a Loki line resolves in Jaeger.
4. Turn the flag off and wait for the resolved notification.

The flag is always restored, even on failure, Ctrl-C or SIGTERM. Talks to the cluster only through
kubectl (see kube.py), so no port-forwards are needed. `make smoke` runs `make status` first.
Log and span contents are untrusted: they're printed truncated, never interpreted.
"""
import argparse
import json
import signal
import sys
import time

from kube import clip, kubectl, log, proxy, read_flags, use_context, write_flags

FLAG, FAULT_VARIANT = "paymentFailure", "100%"
SERVICE = "payment"
ALERT = "ServiceHighErrorRate"
FIRE_TIMEOUT = 12 * 60     # 5m rate window + for: 2m + group_wait, with margin
RESOLVE_TIMEOUT = 15 * 60  # errors must leave the 5m window, then up to group_interval (5m)
POLL = 15


# --- flag ---------------------------------------------------------------------------------

def set_flag(variant):
    cfg = read_flags()  # re-read so concurrent edits to other flags survive
    if variant not in cfg["flags"][FLAG]["variants"]:
        raise RuntimeError(f"{FLAG} has no variant {variant!r}")
    cfg["flags"][FLAG]["defaultVariant"] = variant
    write_flags(cfg)
    log(f"flag {FLAG} -> {variant}")


# --- alerting -----------------------------------------------------------------------------

def webhook_events(skip):
    """Alert events logged by the webhook receiver after the first `skip` lines."""
    lines = kubectl("-n", "observability", "logs", "deploy/alert-webhook").splitlines()
    out = []
    for line in lines[skip:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out, len(lines)


def ours(e, status):
    lb = e.get("labels") or {}
    return e.get("status") == status and lb.get("alertname") == ALERT and lb.get("service_name") == SERVICE


def prom_state():
    alerts = proxy("otel-demo", "prometheus:9090", "/api/v1/alerts")["data"]["alerts"]
    for a in alerts:
        if a["labels"].get("alertname") == ALERT and a["labels"].get("service_name") == SERVICE:
            return a["state"]
    return "inactive"


def error_ratio():
    q = (f'sum(rate(traces_span_metrics_calls_total{{service_name="{SERVICE}",span_kind="SPAN_KIND_SERVER",'
         f'status_code="STATUS_CODE_ERROR"}}[5m])) / sum(rate(traces_span_metrics_calls_total'
         f'{{service_name="{SERVICE}",span_kind="SPAN_KIND_SERVER"}}[5m]))')
    r = proxy("otel-demo", "prometheus:9090", "/api/v1/query", query=q)["data"]["result"]
    return float(r[0]["value"][1]) if r else 0.0


def wait_for(status, skip, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        events, _ = webhook_events(skip)
        hit = next((e for e in events if ours(e, status)), None)
        if hit:
            return hit
        log(f"  waiting for '{status}': prometheus={prom_state()}, error ratio={error_ratio():.0%}")
        time.sleep(POLL)
    raise TimeoutError(f"{ALERT}{{service_name={SERVICE}}} not '{status}' at the webhook within {timeout // 60}m")


# --- evidence -----------------------------------------------------------------------------

def loki_errors(start_ns):
    q = f'{{service_name="{SERVICE}"}} |~ "(?i)(error|fail)"'
    res = proxy("observability", "loki:3100", "/loki/api/v1/query_range",
                query=q, start=str(start_ns), end=str(time.time_ns()), limit="50", direction="backward")
    lines = [(s["stream"], v[1]) for s in res["data"]["result"] for v in s["values"]]
    if not lines:
        raise AssertionError(f"Loki: no error log lines for {SERVICE} since the fault started")
    with_trace = [(st, ln) for st, ln in lines if st.get("trace_id")]
    log(f"Loki: {len(lines)} error lines for {SERVICE} ({len(with_trace)} with trace_id)")
    log(f"  e.g. {clip(lines[0][1])}")
    return with_trace[0][0]["trace_id"] if with_trace else None


def jaeger_errors(start_us):
    res = proxy("otel-demo", "jaeger:16686", "/jaeger/ui/api/traces", service=SERVICE,
                tags=json.dumps({"error": "true"}), start=str(start_us), end=str(int(time.time() * 1e6)), limit="20")
    traces = res.get("data") or []
    if not traces:
        raise AssertionError(f"Jaeger: no traces with error spans for {SERVICE} since the fault started")
    t = traces[0]
    span = next(s for s in t["spans"]
                if t["processes"][s["processID"]]["serviceName"] == SERVICE
                and any(x["key"] == "error" and x["value"] in (True, "true") for x in s["tags"]))
    log(f"Jaeger: {len(traces)} traces with failing {SERVICE} spans, e.g. {t['traceID']} '{clip(span['operationName'], 60)}'")


def jaeger_has_trace(trace_id):
    res = proxy("otel-demo", "jaeger:16686", f"/jaeger/ui/api/traces/{trace_id}")
    spans = (res.get("data") or [{}])[0].get("spans", [])
    if not spans:
        raise AssertionError(f"Loki trace_id {trace_id} not found in Jaeger")
    log(f"Loki -> Jaeger: trace {trace_id} has {len(spans)} spans")


# --- main ---------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--context", help="kubectl context")
    args = ap.parse_args()
    use_context(args.context)

    current = read_flags()["flags"][FLAG]["defaultVariant"]
    if current != "off":
        sys.exit(f"{FLAG} is already {current!r}; turn it off before running the smoke test")
    if prom_state() != "inactive":
        sys.exit(f"{ALERT} for {SERVICE} is already {prom_state()}; wait for it to clear first")

    _, skip = webhook_events(0)
    start_ns = time.time_ns()
    t0 = time.time()
    try:
        set_flag(FAULT_VARIANT)
        fired = wait_for("firing", skip, FIRE_TIMEOUT)
        log(f"FIRING at webhook after {(time.time() - t0) / 60:.1f}m: {clip(fired['annotations'].get('summary'))}")

        trace_id = loki_errors(start_ns)
        jaeger_errors(start_ns // 1000)
        if trace_id:
            jaeger_has_trace(trace_id)
    finally:
        set_flag("off")

    t1 = time.time()
    wait_for("resolved", skip, RESOLVE_TIMEOUT)
    log(f"RESOLVED at webhook {(time.time() - t1) / 60:.1f}m after the flag was turned off")
    log(f"smoke test passed in {(time.time() - t0) / 60:.1f}m")


def _terminate(signum, frame):
    raise KeyboardInterrupt  # run the `finally` that turns the flag off, as on Ctrl-C


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)  # harnesses and CI stop processes with SIGTERM
    try:
        main()
    except (AssertionError, TimeoutError, RuntimeError) as e:
        log(f"FAILED: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        log("interrupted (flag restored)")
        sys.exit(130)
