# infra/ (M0)

Local Kubernetes cluster (kind, see [ADR 0002](../docs/adr/0002-local-cluster-kind.md)), OpenTelemetry Astronomy Shop through its Helm chart, and the telemetry stack: Prometheus, Loki, Tempo/Jaeger, Grafana, and Alertmanager with alert rules. The root `make up` / `make down` call into this folder.

Pin every chart and image version. Conventions specific to this folder will be added as M0 is built.

- The cluster is defined in `kind-config.yaml` (1 control-plane + 2 workers). The node image is pinned by digest; when bumping it, bump `KIND_VERSION` in the root Makefile to the kind release that built it.
- All pinned versions (kind, charts) live in `versions.env`, included by the root Makefile. Bump them deliberately.
- Chart overrides go in `values/<release>.yaml`, never in `--set` flags. The demo runs in namespace `otel-demo`; its UIs are behind `svc/frontend-proxy` on port 8080.
