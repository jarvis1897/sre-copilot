# Architecture

> Stub. This gets filled in during M2–M4.

## Target shape

```
Alertmanager alert
      │
      ▼
 Supervisor ── plans the investigation, manages the token budget, decides when evidence is enough
      │
      ├── Triage agent        dedupes and groups alerts, finds blast radius
      ├── Metrics agent ──► Prometheus MCP server
      ├── Logs agent    ──► Loki MCP server
      ├── Traces agent  ──► Traces MCP server (Tempo/Jaeger)
      ├── Runbook agent ──► hybrid RAG (runbooks + past incidents)
      ├── Diagnosis agent     ranks root-cause hypotheses with cited evidence
      └── Remediation agent ──► K8s MCP server (writes only behind the approval gate)
      │
      ▼
 IncidentReport (schemas/)
```

## Key properties

- **Replay mode:** each MCP server can answer from M1 incident snapshots instead of the live cluster, so evals are fast, cheap, and deterministic.
- **Approval gate:** state-changing tools only run after explicit human approval, and every one is written to the audit log.
- **Scoped permissions:** per-agent tool allowlists are enforced at the MCP layer.
- **Durable state:** investigation state persists at every step and resumes after a worker crash.
