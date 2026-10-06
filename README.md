# sre-copilot

A multi-agent system that takes a firing Alertmanager alert from a Kubernetes-hosted microservices app (the [OpenTelemetry Astronomy Shop](https://opentelemetry.io/docs/demo/)), investigates it, and writes a structured incident report. Remediation runs only after human approval. See [docs/problem-statement.md](docs/problem-statement.md) for the goals and [docs/milestones.md](docs/milestones.md) for status.

**Status:** M0 (environment and telemetry) is done. What works today: a local cluster running the demo app, with metrics, logs, traces, and alerts wired end to end. The agents come in later milestones.

## Quickstart

### Prerequisites

An Ubuntu 24.04 host with sudo. We develop on an 8 vCPU / 32 GB GCP VM ([setup](docs/dev-environment.md)); the full stack uses about 7 GB of RAM.

```bash
./infra/bootstrap.sh
```

This installs Docker, make, kind, kubectl and Helm at the versions pinned in [infra/versions.env](infra/versions.env), verifying each download, and raises the inotify limits that a multi-node kind cluster needs. Re-running it is safe. On another Linux distribution, install the same versions by hand and apply the sysctl settings from [docs/dev-environment.md](docs/dev-environment.md).

### Bring it up

```bash
make up      # kind cluster (1 control plane + 2 workers), Loki, alert webhook, demo app + telemetry
```

The first run takes several minutes, mostly image pulls. Re-running is safe: an existing cluster is reused and the Helm releases are upgraded in place.

Check that everything is healthy:

```bash
make status
```

```
cluster        OK    3/3 nodes ready
pods           OK    47/47 running
frontend       OK    HTTP 200
loadgen        OK    running
metrics        OK    frontend req rate 9.5/s
logs           OK    1,067 lines in last 60s
traces         OK    frontend traces in last 60s
alerts         OK    0 firing
flags          OK    all 18 off
host           OK    inotify limits ok, ip_forward on
```

It exits non-zero if any check fails, so scripts can gate on it; `python3 infra/status.py --json` prints the same results as JSON. Right after `make up` (or anything that restarts the OTel Collector), give telemetry a few minutes to flow before expecting all OK. `alerts` stays FAIL until any firing alert resolves, and `flags` until every demo fault flag is off: a fault-injection run has to start from a clean baseline.

### Look around

All UIs sit behind the demo's frontend proxy:

```bash
kubectl -n otel-demo port-forward svc/frontend-proxy 8080:8080
```

| UI | URL |
|---|---|
| Shop | http://localhost:8080/ |
| Grafana (Prometheus, Loki, Jaeger datasources) | http://localhost:8080/grafana/ |
| Jaeger | http://localhost:8080/jaeger/ui/ |
| Load generator (Locust) | http://localhost:8080/loadgen/ |
| Feature flags (fault injection) | http://localhost:8080/feature/ |

The load generator starts sending traffic as soon as the app is up. On a remote VM, tunnel the port first: `gcloud compute ssh <vm> --ssh-flag="-L 8080:localhost:8080"`, or use VS Code's **Ports** panel.

Alerts go to a webhook receiver that logs each one:

```bash
kubectl -n observability logs -f deploy/alert-webhook
```

### Smoke test with a real fault

```bash
make smoke
```

This runs `make status` first, then turns on the demo's `paymentFailure` flag, waits for the `ServiceHighErrorRate` alert to reach the webhook, and checks the failure in Loki (error logs) and Jaeger (failing spans). It also checks that a log line's `trace_id` opens in Jaeger. It then turns the flag off and waits for the alert to resolve. It takes 10–20 minutes because of the rule windows and Alertmanager's timers, and it always turns the flag off again, even on failure or Ctrl-C.

### Tear down

```bash
make down    # deletes the cluster and all data in it
```

## What's running

| Signal | Backend | Notes |
|---|---|---|
| Metrics | Prometheus (bundled with the demo chart) | Span metrics from the OTel Collector; kube-state-metrics |
| Traces | Jaeger (bundled) | |
| Logs | Loki (namespace `observability`) | OTLP from the collector ([ADR 0003](docs/adr/0003-logs-in-loki.md)) |
| Alerts | Alertmanager (bundled) → webhook logger | Rules: service error rate, service p99 latency, pod restart/crash loop ([ADR 0004](docs/adr/0004-alerting.md)) |

## Repository layout

```
schemas/      shared contracts between components
infra/        cluster, Helm values, alerting, smoke test (M0)
harness/      fault injection and labeled dataset (M1)
mcp_servers/  Prometheus, Loki, traces, and Kubernetes tool servers (M2)
agents/       agents and orchestration (M3–M4)
rag/          runbook and postmortem retrieval (M5)
evals/        eval runner, scorers, scorecards
ui/           investigation and approval UI (M10)
docs/         problem statement, milestones, ADRs
```

Decisions are recorded in [docs/adr/](docs/adr/).
