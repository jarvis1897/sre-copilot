# 0004. Alerting: bundled Alertmanager, span-metric rules, webhook logger

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

M0's exit criterion is a manually triggered alert that fires. The copilot's input (from M3 on) is a firing Alertmanager alert, so the alert path needs to exist now. Start with three rules: service error rate, service p99 latency, and pod restarts or crash loops.

## Decision

- **Alertmanager and kube-state-metrics come from the demo chart's bundled Prometheus subchart.** They're configured in `infra/values/otel-demo.yaml` under `prometheus:`. Prometheus discovers Alertmanager on its own, and kube-state-metrics is scraped through its service annotation, so this adds no extra releases. The config-reload sidecar is enabled so rule changes apply without restarting Prometheus. That needs `--web.enable-lifecycle`, which the demo chart's `server.extraFlags` leaves out, so we restate the list with it.
- **Error-rate and latency rules use the collector's span metrics** (`traces_span_metrics_*`, server spans, grouped by `service_name`). Every demo service emits them in the same shape, whatever its language. The SDK HTTP/RPC metrics aren't consistent across services.
  - Error rate: more than 5% errors over 5m, with at least 0.01 req/s (3 requests in 5m), for 2m. A 0.05 req/s guard was tried first, but it silently excluded payment and checkout, which run at about 0.04 req/s.
  - Latency: p99 above 500ms for 5m. Baseline on 2026-10-06: steady-state p99 was at most ~100ms for every service except `agent` (LLM-backed, 0.4–15s), which is excluded. 500ms leaves room for noise at low traffic and still catches the demo's 5–10s slowdown faults. Long-lived streaming RPCs (flagd `EventStream`/`SyncFlags`) are excluded too: their span lasts as long as the stream, and in testing they set off false alerts. That includes the browser flag streams the frontend proxy carries. Envoy names those spans just `POST`, so a collector transform (`transform/label_streams`) renames them `POST /flagservice EventStream` before span metrics are computed. On a fresh stack, `frontend-proxy` p99 sat at about 3s from these streams alone.
- **The restart rule uses kube-state-metrics**: any container restart in 10m, or `CrashLoopBackOff`, in any namespace. Both sides aggregate to `namespace, pod, container`, so a crash-looping pod is one alert. Without that, the two halves fired and resolved separately.
- **The receiver is a ~50-line stdlib Python webhook** (`infra/manifests/alert-webhook.yaml`, namespace `observability`). It logs one JSON line per alert. It stands in for the copilot's alert intake, and payloads are only logged.
- **Span metrics carry exemplars** (`trace_id`). Each latency/error series points to concrete traces, so evidence for an alert can go from metric to trace to logs (logs share `trace_id`).
- **Validate before deploying:** `promtool check rules` and `amtool check-config` run on the rendered chart, using the image versions the chart deploys.

## Consequences

- **Demo feature flags:** flagd reads a runtime copy of `flagd-config`, which an init container copies into a shared volume at pod start. The flagd UI edits that copy. Patching the ConfigMap has no effect until flagd restarts. It also makes `make up` fail, because Helm 4's server-side apply sees a field-ownership conflict. Tests and the M1 harness should change flags through the runtime file (`/app/data/demo.flagd.json` in the `flagd-ui` container) or the flagd UI, never through the ConfigMap.
- `frontend-proxy` error ratios run high: Envoy exports far fewer spans for successful requests than for failed ones. In testing, an `ad` OOM outage showed up as "100%" errors on `frontend-proxy`. The alert was right; the percentage wasn't.
- Prometheus has no persistent volume. A Prometheus restart, a `make up` that changes its pod, or a VM restart clears metric history, and rate-based rules need about 5 minutes of new data before they can fire. As a side effect, a VM restart doesn't trigger a restart-alert storm: Prometheus comes back with every restart counter already at its new value. Revisit this if we need history across restarts.
- Thresholds are global. Per-service thresholds can come later, if the labeled M1 data shows the global ones are too noisy or too quiet.
- Found along the way: kind on this VM needs raised inotify limits, or kube-proxy crash-loops after a VM restart and Services break on that node (`docs/dev-environment.md` §3). Apply the sysctl file on its own. Running `sysctl --system` also re-applies the GCE image's `ip_forward=0`, which cuts the kind nodes off from the internet.
