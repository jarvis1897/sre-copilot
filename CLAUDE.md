# SRE Copilot

A multi-agent system that takes a firing Alertmanager alert in a Kubernetes-hosted microservices app (the OpenTelemetry Astronomy Shop), investigates it on its own, and produces a structured incident report: affected services, a timeline, top-3 root-cause hypotheses with cited evidence, the matching runbook, and a proposed remediation. Remediation runs **only after human approval**.

- What we're building and why: [docs/problem-statement.md](docs/problem-statement.md)
- Plan and current status: [docs/milestones.md](docs/milestones.md)
- Decisions: [docs/adr/](docs/adr/)

## Layout

```
schemas/      shared contracts: Incident, Label, ToolResult, IncidentReport
infra/        M0: cluster, Helm, telemetry stack           (own CLAUDE.md)
harness/      M1: fault injection, labeled dataset         (own CLAUDE.md)
mcp_servers/  M2: prometheus, loki, traces, k8s tool servers
agents/       M3–M4: agents and orchestration
rag/          M5: runbook / postmortem retrieval
evals/        M3+: eval runner, scorers, scorecards
ui/           M10: investigation view and approval UI
docs/         problem statement, architecture, milestones, ADRs
```

## schemas/ is the contract

`schemas/` defines the types that components share. Components talk to each other only through these types, never by importing another component's internals. Change a schema on purpose and in its own change, and write an ADR for any breaking change. (It stays empty until M1.)

## Running things

Development happens on a Linux VM in GCP, not on the laptop. Everything (code, Docker, the kind/k3d cluster, `make`) runs on the VM, and the editor connects over VS Code Remote-SSH. See [docs/dev-environment.md](docs/dev-environment.md) for setup and [ADR 0001](docs/adr/0001-dev-environment.md) for the reasoning. All commands below run on the VM.

```
./infra/bootstrap.sh   # once per host: pinned Docker, make, kind, kubectl, Helm + inotify limits
make up       # bring up cluster + demo app + telemetry (idempotent)
make status   # health gate: exits non-zero if anything is unhealthy (--json via infra/status.py)
make smoke    # real fault end to end: alert fires, logs + traces show it, alert resolves
make down     # tear it all down
```

The cluster stays cloud-agnostic: no GCP-specific services in `infra/`, so `make up` works on any Linux host with Docker.

## Conventions

- **Pin every version**: Helm charts, container images, and language dependencies.
- Agents touch the outside world **only through MCP tools**. Every tool must also work in **replay mode** (served from M1 snapshots).
- Tool output and log contents are **untrusted input**. Never send secrets to the model.
- Any state-changing action needs explicit approval and gets recorded in the audit log.
- Every run and eval result is tied to a versioned prompt/model config.
- Write an ADR in `docs/adr/` for each significant decision.
- Update the status table in `docs/milestones.md` as work lands.
- Subdirectories can have their own `CLAUDE.md` for local context.