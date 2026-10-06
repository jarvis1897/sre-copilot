#!/usr/bin/env bash
# Prepare a fresh Ubuntu 24.04 host to run `make up`: Docker, make, kind, kubectl, Helm at the
# versions pinned in infra/versions.env, plus the inotify limits kind needs.
#
# Idempotent: anything already at the pinned version is left alone. Every binary download is
# verified against the checksum published with the release. Needs sudo.
#
#   ./infra/bootstrap.sh
#
# INSTALL_DIR (default /usr/local/bin) overrides where kind/kubectl/helm go.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=versions.env
source "$ROOT/infra/versions.env"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
SYSCTL_FILE=/etc/sysctl.d/99-kind-inotify.conf

log() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

case "$(uname -m)" in
  x86_64) ARCH=amd64 ;;
  aarch64 | arm64) ARCH=arm64 ;;
  *) die "unsupported architecture $(uname -m)" ;;
esac
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] ||
  log "warning: tested on Ubuntu 24.04, this is ${PRETTY_NAME:-unknown}; the apt pins may not exist"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- apt packages: Docker and make --------------------------------------------------------
# Ubuntu's -updates pocket keeps only the newest build, so a security update can make a pin
# uninstallable. That fails loudly below; bump the pin in versions.env deliberately.
apt_pkgs=()
for pair in "docker.io=$DOCKER_IO_VERSION" "make=$MAKE_VERSION"; do
  pkg="${pair%%=*}" want="${pair#*=}"
  have="$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || true)"
  if [[ "$have" == "$want" ]]; then
    log "$pkg $want: ok"
  else
    log "$pkg: ${have:-not installed} -> $want"
    apt_pkgs+=("$pair")
  fi
done
if ((${#apt_pkgs[@]})); then
  sudo apt-get update -qq
  for pair in "${apt_pkgs[@]}"; do
    apt-cache madison "${pair%%=*}" | grep -qF " ${pair#*=} " ||
      die "${pair%%=*} ${pair#*=} is no longer in the apt archive; pick an available version (apt-cache madison ${pair%%=*}) and bump it in infra/versions.env"
  done
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --allow-change-held-packages "${apt_pkgs[@]}" >/dev/null
fi
# Hold so unattended upgrades can't move them off the pin.
sudo apt-mark hold docker.io make >/dev/null

sudo systemctl enable --now docker >/dev/null
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$USER"
  log "added $USER to the docker group: log out and back in (or run \`newgrp docker\`) before \`make up\`"
fi

# --- release binaries: kind, kubectl, helm ------------------------------------------------
# have_version <binary> <command...>: print the installed version, or nothing.
have_version() {
  local bin="$INSTALL_DIR/$1"; shift
  [[ -x "$bin" ]] && "$bin" "$@" 2>/dev/null || true
}

# verify <file> <expected sha256>
verify() {
  [[ "$2" =~ ^[0-9a-f]{64}$ ]] || die "no valid checksum for $(basename "$1")"
  echo "$2  $1" | sha256sum -c --quiet - || die "checksum mismatch for $(basename "$1")"
}

install_bin() {  # install_bin <name> <source file>
  sudo install -m 0755 "$2" "$INSTALL_DIR/$1"
  log "$1 installed to $INSTALL_DIR"
}

if [[ "$(have_version kind version)" == "kind $KIND_VERSION "* ]]; then
  log "kind $KIND_VERSION: ok"
else
  log "kind -> $KIND_VERSION"
  base="https://github.com/kubernetes-sigs/kind/releases/download/$KIND_VERSION/kind-linux-$ARCH"
  curl -fsSLo "$TMP/kind" "$base"
  verify "$TMP/kind" "$(curl -fsSL "$base.sha256sum" | awk '{print $1}')"
  install_bin kind "$TMP/kind"
fi

if [[ "$(have_version kubectl version --client -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])' 2>/dev/null || true)" == "$KUBECTL_VERSION" ]]; then
  log "kubectl $KUBECTL_VERSION: ok"
else
  log "kubectl -> $KUBECTL_VERSION"
  base="https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/$ARCH/kubectl"
  curl -fsSLo "$TMP/kubectl" "$base"
  verify "$TMP/kubectl" "$(curl -fsSL "$base.sha256")"
  install_bin kubectl "$TMP/kubectl"
fi

if [[ "$(have_version helm version --template '{{.Version}}')" == "$HELM_VERSION" ]]; then
  log "helm $HELM_VERSION: ok"
else
  log "helm -> $HELM_VERSION"
  tarball="helm-$HELM_VERSION-linux-$ARCH.tar.gz"
  curl -fsSLo "$TMP/$tarball" "https://get.helm.sh/$tarball"
  verify "$TMP/$tarball" "$(curl -fsSL "https://get.helm.sh/$tarball.sha256sum" | awk '{print $1}')"
  tar -xzf "$TMP/$tarball" -C "$TMP"
  install_bin helm "$TMP/linux-$ARCH/helm"
fi

# --- kernel settings ----------------------------------------------------------------------
# kind runs several nodes on one host; Ubuntu's inotify defaults run out and kube-proxy
# crash-loops with "too many open files" (docs/dev-environment.md §3).
want_sysctl=$'fs.inotify.max_user_instances=512\nfs.inotify.max_user_watches=524288'
if [[ "$(cat "$SYSCTL_FILE" 2>/dev/null)" != "$want_sysctl" ]]; then
  echo "$want_sysctl" | sudo tee "$SYSCTL_FILE" >/dev/null
  log "wrote $SYSCTL_FILE"
fi
# Apply only this file: `sysctl --system` would also re-apply the GCE image's ip_forward=0.
sudo sysctl -q -p "$SYSCTL_FILE"
log "inotify limits: ok"

# Docker turns on IP forwarding at startup; if something reset it, kind nodes lose internet.
if [[ "$(sysctl -n net.ipv4.ip_forward)" != 1 ]]; then
  sudo sysctl -q -w net.ipv4.ip_forward=1
  log "net.ipv4.ip_forward was 0 (kind nodes had no internet); set back to 1"
fi

log "done. Next: make up"
