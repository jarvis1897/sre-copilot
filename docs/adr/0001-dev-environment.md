# 0001. Develop on a single GCP VM running kind/k3d

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

The full stack needs roughly 12–16 GB of RAM at steady state: the Astronomy Shop (~15 services plus the load generator), Prometheus, Loki, Tempo/Jaeger, Grafana, Alertmanager, Chaos Mesh and Postgres. Later milestones add more (pgvector, Langfuse, concurrent investigations). The developer's Windows laptop can't run this, and Windows tooling (`make`, shell scripts, Docker networking) adds friction on top.

The problem statement asks for a *local* Kubernetes cluster with a one-command deployment, and rules out cloud-provider-specific integrations for v1.

## Decision

- Develop on **one Linux VM on GCP Compute Engine** (Ubuntu LTS). Code, Docker, the cluster and `make` all live on the VM. The laptop only runs VS Code over Remote-SSH.
- Run the cluster with **kind or k3d on that VM**. The final choice between the two is part of M0.
- **No GKE and no GCP-managed services** (Cloud SQL, Cloud Logging, and so on) in the stack. `infra/` must work on any Linux host with Docker.
- Size the VM at **e2-standard-8 (8 vCPU, 32 GB)** with a 100 GB balanced persistent disk. e2-standard-4 (16 GB) is enough for replay-mode-only work.
- **Don't expose UIs publicly.** Reach Grafana and other UIs through SSH port forwarding. The only open firewall port is SSH.
- **Stop the VM when not in use**, and use a standard (non-spot) VM so long M1 dataset runs aren't preempted.

## Consequences

- The "one-command local deployment" deliverable still holds, since the VM is just a Linux host. Anyone can reproduce it on their own machine or VM.
- Ongoing cost while the VM is running. This is cut down by stopping it when idle, and by doing replay-mode work (M2 tests, M3–M7 evals) on a smaller VM or without the cluster up.
- Development depends on network access to the VM. Code still lives in git, so losing the VM loses nothing that isn't pushed.
- Revisit this if the cluster outgrows a single VM, which would most likely happen during M9 load testing.
