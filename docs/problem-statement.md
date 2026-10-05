

# Background

In a microservices system, a single fault (a crashed pod, a slow database, a bad config push) spreads across many services. It shows up as a flood of alerts, error logs, and degraded traces far from the actual cause. On-call engineers spend most of an incident gathering context: correlating alerts, querying metrics, reading logs, following traces across service boundaries, and searching runbooks. Industry post mortems consistently show that time-to-diagnose, not time-to-fix, dominates mean time to resolution (MTTR). That investigation work is repetitive and tool-heavy, which makes it a good fit for coordinated agents.

# Problem

Build a system that, given a firing alert in a Kubernetes-hosted microservices application, autonomously investigates the incident and produces:

•       a ranked root-cause hypothesis, with supporting evidence pulled from telemetry,

•       a recommended remediation, which it executes only after human approval.

It must do this reliably, safely, and observably, under production constraints: partial failures, cost budgets, untrusted tool output, and changing prompts and models.

# Environment

The target system is the OpenTelemetry Astronomy Shop demo (around 15 services in multiple languages) running on a local Kubernetes cluster. The telemetry stack is Prometheus for metrics, Loki for logs, and Jaeger or Tempo for traces. Chaos Mesh injects faults on demand. Runbooks and synthetic postmortems are written once as markdown and serve as the RAG corpus.

# Fault Taxonomy (the test universe)

Each fault type is injectable into any service, giving a labeled incident with a known root cause:

|**Category**|**Faults**|
|---|---|
|**Resource**|Pod crash/OOM, CPU throttling, memory leak|
|**Network**|Added latency, packet loss, network partition between two services|
|**Dependency**|Downstream service down, database or Redis slowdown|
|**Application**|Error-rate spike from a feature flag (the demo ships with built-in failure flags)|
|**Config**|Bad environment variable or replica count set to zero|

Harder variants:

•       two simultaneous faults,

•       a fault whose symptoms appear three hops away from the cause,

•       red herrings, such as an unrelated noisy alert firing at the same time.

# Inputs and Outputs

**Input:** an alert payload from Alertmanager. Optionally, an engineer's follow-up questions in a chat interface.

**Output:** a structured incident report with these fields:

•       affected services,

•       a timeline of events,

•       the top-3 root-cause hypotheses with confidence scores and cited evidence (specific metric queries, log lines, trace IDs),

•       the matching runbook,

•       a proposed remediation action.

Any state-changing action (restart, rollback, scale) waits for explicit approval and is recorded in an audit log.

# Agents (initial decomposition)

•       **Triage agent:** dedupes and groups alerts, and identifies blast radius.

•       **Metrics, Logs, and Traces agents:** each queries its tool through its own MCP server.

•       **Runbook agent:** retrieves relevant runbooks and similar past incidents using hybrid RAG.

•       **Diagnosis agent:** synthesizes evidence and ranks hypotheses.

•       **Remediation agent:** proposes actions and stops at a human approval gate before executing.

•       **Supervisor:** plans the investigation, manages the budget, and decides when the evidence is sufficient.

# Success Metrics

|**Metric**|**Target**|
|---|---|
|**Root-cause accuracy (top-1 / top-3) on the eval suite**|≥70% / ≥90% for single faults|
|**Median time-to-diagnosis**|< 3 minutes|
|**Evidence faithfulness (every claim backed by a real query result)**|≥95%|
|**Unapproved state-changing actions**|0|
|**Cost per investigation**|Tracked and budget-capped|
|**Recovery**|A run resumes correctly after a worker is killed mid-investigation|
|**Regression gating**|Every prompt or model change runs the eval suite in CI and is blocked on regression|

_The exact percentages are starting targets. Set real ones after measuring a baseline._

# Non-Functional Requirements

## Durability and fault tolerance

•       Investigation state persists across crashes.

•       Tool calls are idempotent.

•       Timeouts and retries are explicit.

## Observability of the agents themselves

•       End-to-end traces cover every LLM call and tool call.

•       Token cost and latency are tracked per run.

## Versioning

•       Prompts and model configs are versioned.

•       Every run and eval result is tied to those versions.

## Security

•       Tool permissions are scoped per agent (for example, the logs agent cannot call kubectl).

•       Log contents are treated as untrusted input, with prompt-injection test cases in the eval suite.

•       Secrets are never sent to the model.

## Cost control

•       Model routing (a cheaper model for triage and extraction, a stronger one for diagnosis).

•       Prompt and semantic caching.

•       A per-incident token budget.

# Out of Scope (v1)

•       Multi-cluster or cloud-provider-specific integrations.

•       Fully autonomous remediation without approval.

•       Fine-tuning models.

•       Real production traffic. Load is generated by the demo's built-in load generator.

# Deliverable

The deliverable has four parts:

1.      A one-command local deployment.

2.      A fault-injection harness that generates labeled incidents.

3.      An eval runner producing a scorecard per prompt or model version.

4.      A dashboard showing investigations, traces, and cost.

The demo story: inject a fault, watch the agents investigate live, approve the fix, and see the scorecard.