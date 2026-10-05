# 0002. Local cluster: kind, 1 control-plane + 2 workers

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

M0 needs a local, reproducible Kubernetes cluster on the dev VM (and on any Linux host with Docker, per the cloud-agnostic rule). M1 will inject faults with Chaos Mesh, including network faults, which are only realistic when traffic crosses node boundaries. The candidates were kind and k3d.

## Decision

Use **kind** with one control-plane node and two workers, configured in `infra/kind-config.yaml`.

- kind runs upstream kubeadm-built Kubernetes, so behavior matches real clusters more closely than k3s (which swaps in its own datastore, ingress, and service load balancer).
- kind node images can be pinned by `@sha256` digest per kind release, which satisfies "pin every version".
- kind is widely used in CI for Chaos Mesh and Kubernetes e2e testing, so fault behavior is well trodden.
- Two workers let pods of one service land on different nodes than their dependencies, so network partitions and latency faults affect real cross-node paths. More nodes would cost VM memory for little extra realism.

We pin Kubernetes v1.36.4 (built by kind v0.33.0) rather than the newest minor (1.37.0), since Helm charts and Chaos Mesh tend to lag the newest minor.

## Consequences

- The kind CLI version (`KIND_VERSION` in the Makefile) and the node image digest must be bumped together.
- Each node is a Docker container, so the VM needs enough memory for three nodes plus the demo app and telemetry stack (e2-standard-8 should be enough; revisit if pods get evicted).
- No host port mappings yet; UIs are reached via `kubectl port-forward` plus an SSH tunnel. Revisit when the telemetry stack lands.
