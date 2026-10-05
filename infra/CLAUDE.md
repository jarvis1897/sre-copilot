# infra/ (M0)

Local Kubernetes cluster (kind or k3d), OpenTelemetry Astronomy Shop through its Helm chart, and the telemetry stack: Prometheus, Loki, Tempo/Jaeger, Grafana, and Alertmanager with alert rules. The root `make up` / `make down` call into this folder.

Pin every chart and image version. Conventions specific to this folder will be added as M0 is built.
