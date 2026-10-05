# Dev environment (GCP VM)

Why we develop on a VM: [ADR 0001](adr/0001-dev-environment.md).

Run the `gcloud` commands from your laptop (with the [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and `gcloud auth login` done). Pick a zone close to you.

## 1. One-time setup

```bash
export PROJECT=<your-gcp-project-id>
export ZONE=<zone, e.g. us-central1-a>
export VM=sre-copilot-dev

gcloud config set project $PROJECT
gcloud config set compute/zone $ZONE
gcloud services enable compute.googleapis.com

gcloud compute instances create $VM \
  --machine-type=e2-standard-8 \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-balanced
```

The default network only allows SSH from outside, which is what we want. Don't add firewall rules for Grafana and other UIs. Use port forwarding (step 4).

Also set a **billing budget alert** in the GCP console (Billing → Budgets & alerts) so a VM you forgot to stop doesn't surprise you.

## 2. Connect VS Code

```bash
gcloud compute config-ssh
```

This writes an entry to `~/.ssh/config` named `$VM.$ZONE.$PROJECT`. In VS Code, install the **Remote - SSH** extension, run *Remote-SSH: Connect to Host…*, and pick that entry. Clone the repo on the VM and open it from there.

## 3. Tooling on the VM

You need Docker, kind or k3d, Helm, kubectl, `make` and Python. Install them at pinned versions. A bootstrap script for this comes with M0 (`infra/`).

## 4. Reaching UIs

Forward ports over SSH instead of exposing them:

```bash
gcloud compute ssh $VM -- -L 3000:localhost:3000   # Grafana
```

Then open http://localhost:3000 on your laptop. Add another `-L` for each UI you need. The exact ports are set in M0.

## 5. Daily use

```bash
gcloud compute instances start $VM    # start of session
gcloud compute instances stop  $VM    # end of session: stops compute billing (the disk is still billed)
```

After a start, run `gcloud compute config-ssh` again if VS Code can't connect (the external IP can change).
