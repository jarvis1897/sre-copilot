# infra/ (M0)

Local Kubernetes cluster (kind, see [ADR 0002](../docs/adr/0002-local-cluster-kind.md)), OpenTelemetry Astronomy Shop through its Helm chart, and the telemetry stack: Prometheus, Loki, Jaeger, Grafana, and Alertmanager with alert rules. The root `make up` / `make down` call into this folder.

Pin every chart and image version. Conventions specific to this folder will be added as M0 is built.

- The cluster is defined in `kind-config.yaml` (1 control-plane + 2 workers). The node image is pinned by digest; when bumping it, bump `KIND_VERSION` in `versions.env` to the kind release that built it.
- All pinned versions (host tools, kind, charts) live in `versions.env`, read by the root Makefile and `bootstrap.sh`. Bump them deliberately.
- Chart overrides go in `values/<release>.yaml`, never in `--set` flags. The demo runs in namespace `otel-demo`; its UIs are behind `svc/frontend-proxy` on port 8080.
- Telemetry: the demo chart's bundled Prometheus, Jaeger, and Grafana stay; OpenSearch is off. Logs go collector → OTLP/HTTP → Loki (`grafana/loki`, single-binary) in namespace `observability` ([ADR 0003](../docs/adr/0003-logs-in-loki.md)).
- Alerting ([ADR 0004](../docs/adr/0004-alerting.md)): Alertmanager, kube-state-metrics, and the rules live under `prometheus:` in `values/otel-demo.yaml` (bundled chart). Alerts go to the webhook logger in `manifests/alert-webhook.yaml` (ns `observability`); read them with `kubectl -n observability logs deploy/alert-webhook`.
- Validate before deploying: render with `helm template`, then run `otelcol-contrib validate` (collector config), `promtool check rules` and `amtool check-config`, using the same image versions the chart deploys. A bad collector exporter config stops all telemetry.
- `bootstrap.sh` provisions the host (tools + inotify limits); keep it idempotent and checksum-verified. Without the inotify limits kube-proxy crash-loops after a VM restart and Services break on that node.
- Flip demo feature flags through the runtime file (`kubectl -n otel-demo exec -i deploy/flagd -c flagd-ui -- sh -c 'cat > /app/data/demo.flagd.json'`) or the flagd UI (`/feature/`), never by patching the `flagd-config` ConfigMap: flagd ignores ConfigMap changes until it restarts, and the patch makes `make up` fail with a Helm field-ownership conflict.
- `make status` (`status.py`) is the health gate (10 checks, including `flags` all off and `host` sysctls): run it after `make up`, before `make smoke`, and before every fault-injection run. It exits non-zero on any failed check; `--json` is the harness interface, so keep its shape stable. `status.py` and `smoke.py` share kubectl helpers in `kube.py` and reach services through the API-server proxy, not port-forwards.
- After the OTel Collector restarts (any change to its config), each collector pod starts new span-metric series, so `status` reports `metrics FAIL` for a few minutes until two samples exist. That's expected; wait it out.
- The demo chart hard-codes `busybox:latest` init containers; `values/otel-demo.yaml` restates those lists with busybox pinned by digest. Re-check them when bumping the chart.
