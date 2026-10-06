.PHONY: help up down status smoke

include infra/versions.env

CLUSTER_NAME   := sre-copilot
KUBE_CONTEXT   := kind-$(CLUSTER_NAME)
KIND_CONFIG    := infra/kind-config.yaml
OTEL_DEMO_NS   := otel-demo
OTEL_DEMO_REPO := https://open-telemetry.github.io/opentelemetry-helm-charts
OBS_NS         := observability
GRAFANA_REPO   := https://grafana.github.io/helm-charts

help: ## List available targets
	@echo "Targets:"
	@echo "  up      Bring up cluster, demo app, and telemetry stack"
	@echo "  down    Tear down the cluster"
	@echo "  status  Show cluster, pod, and telemetry health"
	@echo "  smoke   Inject a real fault; check alert, logs, traces, and resolution"

# Create the kind cluster (no-op if it exists) and install the pinned Helm releases (demo app + telemetry).
up:
	@command -v docker >/dev/null || { echo "error: docker not found on PATH" >&2; exit 1; }
	@command -v kind >/dev/null || { echo "error: kind not found on PATH (want $(KIND_VERSION))" >&2; exit 1; }
	@command -v helm >/dev/null || { echo "error: helm not found on PATH" >&2; exit 1; }
	@kind version | grep -q '$(KIND_VERSION) ' || echo "warning: kind is not $(KIND_VERSION); the pinned node image may not match" >&2
	@[ "$$(sysctl -n fs.inotify.max_user_instances)" -ge 512 ] || echo "warning: fs.inotify.max_user_instances < 512; kube-proxy may crash with 'too many open files' (see docs/dev-environment.md)" >&2
	@if kind get clusters 2>/dev/null | grep -qx '$(CLUSTER_NAME)'; then \
		echo "cluster '$(CLUSTER_NAME)' already exists; skipping create"; \
	else \
		kind create cluster --config $(KIND_CONFIG) --wait 120s; \
	fi
	@# kind's --wait only covers the control-plane; wait for the workers too.
	@kubectl --context $(KUBE_CONTEXT) wait --for=condition=Ready nodes --all --timeout=120s
	helm upgrade --install loki loki --repo $(GRAFANA_REPO) \
		--version $(LOKI_CHART_VERSION) --kube-context $(KUBE_CONTEXT) \
		--namespace $(OBS_NS) --create-namespace \
		--values infra/values/loki.yaml --wait --timeout 10m
	kubectl --context $(KUBE_CONTEXT) apply -f infra/manifests/alert-webhook.yaml
	helm upgrade --install otel-demo opentelemetry-demo --repo $(OTEL_DEMO_REPO) \
		--version $(OTEL_DEMO_CHART_VERSION) --kube-context $(KUBE_CONTEXT) \
		--namespace $(OTEL_DEMO_NS) --create-namespace \
		--values infra/values/otel-demo.yaml --wait --timeout 15m

# Delete the cluster and everything in it.
down:
	kind delete cluster --name $(CLUSTER_NAME)

# Health check: nodes, pods, frontend, load generator, metrics, logs, traces, alerts.
# Exits non-zero if anything is unhealthy; `python3 infra/status.py --json` for programs.
status:
	@python3 infra/status.py --context $(KUBE_CONTEXT)

# Real fault end to end: paymentFailure flag -> error-rate alert at the webhook, evidence in
# Loki and Jaeger, flag off -> alert resolves. Takes ~10-20 min (rate windows + Alertmanager timers).
smoke: status
	python3 infra/smoke.py --context $(KUBE_CONTEXT)
