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

From the repo root on the VM:

```bash
./infra/bootstrap.sh
```

It installs Docker, make, kind, kubectl and Helm at the versions pinned in `infra/versions.env`, verifying each download against its published checksum. It holds the apt packages so unattended upgrades can't move them off the pin. Re-running it is safe; anything already at the pinned version is left alone. If it adds you to the `docker` group, log out and back in before `make up`.

It also raises the inotify limits. kind runs several Kubernetes nodes on one host, and the Ubuntu defaults run out: kube-proxy then crash-loops with `too many open files` and pods on that node can't reach Services ([kind known issue](https://kind.sigs.k8s.io/docs/user/known-issues/#pod-errors-due-to-too-many-open-files)). The settings live in `/etc/sysctl.d/99-kind-inotify.conf`, so they survive VM restarts, and `make up` warns if they're too low.

Don't run `sysctl --system` on this VM. The GCE image's `60-gce-network-security.conf` sets `net.ipv4.ip_forward=0`, which overrides the value Docker sets at startup and cuts the kind nodes off from the internet (image pulls time out). If that happens, `sudo sysctl -w net.ipv4.ip_forward=1` restores it, and so does re-running the bootstrap script.

If the script reports that a pinned apt version is gone from the archive, Ubuntu has shipped an update. Pick the new version from `apt-cache madison <pkg>` and bump it in `infra/versions.env`.

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
