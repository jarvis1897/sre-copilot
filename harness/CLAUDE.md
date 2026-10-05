# harness/ (M1)

Chaos Mesh fault templates plus a harness CLI. For each run it injects a fault, waits for alerts, snapshots telemetry, records a label (root cause, service, fault type, time window), then cleans up and verifies the system is healthy. Its output is the labeled incident dataset and the snapshots that replay mode uses.

Incidents and labels must follow the types in `schemas/`. Conventions specific to this folder will be added as M1 is built.
