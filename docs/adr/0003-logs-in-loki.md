# 0003. Logs in Loki via OTLP, replacing the demo's OpenSearch

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

The OpenTelemetry demo chart bundles Prometheus, Jaeger, Grafana, and OpenSearch, and its OTel Collector sends logs to OpenSearch. Our plan (M2) includes a Loki tool server queried with LogQL, so we need logs in Loki. Running two log backends would double storage and memory for no benefit.

## Decision

- Keep the bundled Prometheus, Jaeger, and Grafana.
- Deploy Loki ourselves (`grafana/loki` chart, single-binary, filesystem storage, 72h retention) in its own `observability` namespace, so chaos experiments aimed at `otel-demo` don't take down log storage.
- Disable the bundled OpenSearch. The collector's logs pipeline exports only to Loki.
- Send logs over **OTLP/HTTP to Loki's native `/otlp` endpoint**. The contrib `loki` exporter was removed upstream. OTLP ingestion maps resource attributes like `service.name` and `k8s.*` to index labels, and keeps `trace_id`/`span_id` as structured metadata.
- Add a Grafana Loki datasource with a derived field that links `trace_id` to Jaeger.

## Consequences

- The M2 Loki tool server has a single log source, queried by `service_name` and the `k8s_*` labels.
- The chart bakes in some OpenSearch pieces we can't remove through values: the OpenSearch datasource and dashboard panels that use it stay in Grafana but show no data. Jaeger's "logs for this span" link still points at OpenSearch, so it's broken. Logs → trace (through Loki) works.
- The chart's default `opensearch` exporter stays defined but unused. Setting it to `null` leaves an empty config that fails collector validation.
- Loki data lives on a PVC in kind, so `make down` deletes it, which is fine for a dev cluster.
