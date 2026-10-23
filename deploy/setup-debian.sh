#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || (${2:-} != "" && ${2:-} != --no-start) ]]; then
  echo "Usage: sudo bash deploy/setup-debian.sh DOMAIN [--no-start]" >&2
  exit 1
fi
domain=$1
if [[ ! $domain =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ || $domain == *..* ]]; then
  echo "Pass a hostname or IPv4 address, without a scheme, port, or path." >&2
  exit 1
fi
if [[ $(id -u) != 0 ]]; then
  echo "Run this script with sudo on the Debian VPS." >&2
  exit 1
fi
# shellcheck source=/dev/null
source /etc/os-release
if [[ $ID != debian ]]; then
  echo "This setup script targets Debian. No changes were made." >&2
  exit 1
fi
tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config=/etc/nginx/sites-available/n4ml
enabled=/etc/nginx/sites-enabled/n4ml
if [[ -e $config || -L $config || -e $enabled || -L $enabled ]]; then
  echo "N4ML is already configured. Deploy with n4ml-site; setup will not overwrite HTTPS settings." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  nginx python3 ca-certificates certbot python3-certbot-nginx logrotate
install -d -m 0755 /srv/n4ml/releases
install -m 0755 "$tools_dir/site.py" /usr/local/sbin/n4ml-site
sed "s/__DOMAIN__/$domain/g" "$tools_dir/nginx.conf" > "$config"
chmod 0644 "$config"
ln -s "$config" "$enabled"

# Disable only Debian's stock default symlink, preserving its configuration.
restore_default=false
if [[ -L /etc/nginx/sites-enabled/default && \
      $(readlink -f /etc/nginx/sites-enabled/default) == /etc/nginx/sites-available/default ]]; then
  rm /etc/nginx/sites-enabled/default
  restore_default=true
fi
if ! nginx -t; then
  rm "$enabled" "$config"
  if $restore_default; then
    ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
  fi
  echo "Nginx rejected the configuration; the previous site configuration was restored." >&2
  exit 1
fi
if [[ ${2:-} != --no-start ]]; then
  systemctl enable --now nginx
  systemctl reload nginx
fi
echo "Configured $domain. Install a release with: sudo n4ml-site install /path/to/n4ml-vps.tar.gz"
