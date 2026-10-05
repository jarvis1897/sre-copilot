.PHONY: help up down status smoke

help: ## List available targets
	@echo "Targets:"
	@echo "  up      Bring up cluster, demo app, and telemetry stack"
	@echo "  down    Tear down the cluster"
	@echo "  status  Show cluster, pod, and telemetry health"
	@echo "  smoke   Trigger a test alert and confirm it fires"

# Create the kind/k3d cluster and install the pinned Helm releases (demo app + telemetry).
up:
	@echo "up: not implemented yet (M0)"

# Delete the cluster and everything in it.
down:
	@echo "down: not implemented yet (M0)"

# Report cluster, pod, and telemetry-stack health.
status:
	@echo "status: not implemented yet (M0)"

# Trigger a known alert and verify Alertmanager receives it.
smoke:
	@echo "smoke: not implemented yet (M0)"
