#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 || $(id -u) != 0 ]]; then
  echo "Usage: sudo bash deploy/setup-cicd.sh /path/to/ci-public-key.pub" >&2
  exit 1
fi
key_file=$1
ssh-keygen -lf "$key_file" >/dev/null
if [[ $(wc -l < "$key_file") != 1 ]] || ! [[ $(cat "$key_file") =~ ^ssh-ed25519[[:space:]] ]]; then
  echo "Expected one Ed25519 public key." >&2
  exit 1
fi
tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! id n4ml-deploy >/dev/null 2>&1; then
  useradd --system --user-group --create-home --home-dir /var/lib/n4ml-deploy --shell /bin/sh n4ml-deploy
fi
if [[ $(getent passwd n4ml-deploy | cut -d: -f6) != /var/lib/n4ml-deploy ]]; then
  echo "An unexpected n4ml-deploy account already exists." >&2
  exit 1
fi
install -d -m 0755 /usr/local/libexec
install -m 0755 "$tools_dir/site.py" /usr/local/sbin/n4ml-site
install -m 0755 "$tools_dir/receive.py" /usr/local/libexec/n4ml-receive
install -m 0755 "$tools_dir/check-live.py" /usr/local/libexec/n4ml-check-live
install -d -m 0755 /srv/n4ml/releases
install -d -m 0700 /srv/n4ml/incoming
chown -R n4ml-deploy:n4ml-deploy /srv/n4ml
install -d -m 0700 -o n4ml-deploy -g n4ml-deploy /var/lib/n4ml-deploy/.ssh
printf 'restrict,command="/usr/local/libexec/n4ml-receive" %s\n' "$(cat "$key_file")" \
  > /var/lib/n4ml-deploy/.ssh/authorized_keys
chown n4ml-deploy:n4ml-deploy /var/lib/n4ml-deploy/.ssh/authorized_keys
chmod 0600 /var/lib/n4ml-deploy/.ssh/authorized_keys
echo "CI key installed for n4ml-deploy. This account has no sudo privileges."
