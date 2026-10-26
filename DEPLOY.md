# Debian VPS deployment

Designed for **1 CPU, 1 GB RAM, and 20 GB disk**. Nginx serves the static site; there is no Node service, database, Docker daemon, or build step on the VPS. Build and test on GitHub or your computer, then upload a finished release.

The eight recordings total about 500 MiB. Three retained releases use roughly 1.5 GiB, plus the upload and small deployment tools. The installer caps each unpacked release at 1 GiB, checks free disk space, and prunes older releases after activation. Remove uploaded archives after deployment. Nginx streams audio with byte-range requests and serves precompressed text. Access logging is off; Debian's standard Nginx log rotation covers the error log.

## Set the public address

Set the GitHub Actions repository variable `SITE_URL` to the eventual HTTPS origin, such as `https://n4ml.net`, before producing a production release. Local builds also accept the `SITE_URL` environment variable or `.env.local`. Only an origin is accepted: no path, credentials, query, or fragment. Without it, absolute canonical/social URL tags are omitted. The site works at the root of any hostname; do not install under a subdirectory.

## Get a tested release

The workflow runs lint, application tests, packaging, installer/rollback tests, and real Nginx checks in a **Debian 12 and 13 containers limited to 1 CPU and 1 GiB RAM**. Tags beginning `vps-` publish verified bundles to [GitHub Releases](https://github.com/MaxFreedman/n4ml-website/releases). Main-branch pushes and manual runs also produce an Actions artifact retained for one day.

On your computer, download the three release assets:

```sh
gh release download vps-1.0.0 --repo MaxFreedman/n4ml-website --dir release
```

Or build them locally with Node 22.12+ or a current supported Node LTS:

```sh
npm ci
SITE_URL=https://YOUR_DOMAIN npm run package
```

Output: `release/n4ml-vps.tar.gz`, `release/n4ml-deploy-tools.tar.gz`, and `release/SHA256SUMS`. The site archive includes every recording and project file, a build receipt, and a SHA-256 inventory.

## Upload and configure Debian

Debian 12 and 13 are tested. Replace `USER`, `VPS_IP`, and `YOUR_DOMAIN`. The SSH user needs sudo; a provider-issued root account can omit `sudo`.

```sh
ssh USER@VPS_IP 'mkdir -p /var/tmp/n4ml-deploy'
scp release/* USER@VPS_IP:/var/tmp/n4ml-deploy/
ssh USER@VPS_IP
```

On the VPS:

```sh
cd /var/tmp/n4ml-deploy
sha256sum --check SHA256SUMS
tar -xzf n4ml-deploy-tools.tar.gz
sudo bash deploy/setup-debian.sh YOUR_DOMAIN
sudo n4ml-site install /var/tmp/n4ml-deploy/n4ml-vps.tar.gz
sudo n4ml-site status
curl --fail http://127.0.0.1/healthz
```

Setup installs Debian's Nginx, Python 3, Certbot, and logrotate packages, adds one site configuration, and enables Nginx. It disables only the stock default site's symlink, preserving the file. An existing N4ML config is never overwritten, so later deployments preserve HTTPS settings. Other existing Nginx sites may require adjustment to the default-server choice. `--no-start` is available for testing in a container without systemd.

The installer validates the inventory before activation, rejects unsafe archives, serializes installs, and atomically switches `/srv/n4ml/current`. Nginx reads the new files without restarting. Keep the deployment tools for later updates.

## DNS and HTTPS

Set an A record to the VPS IPv4 address. Add AAAA only if IPv6 works on the VPS. Allow TCP 80 and 443 in the provider/server firewall while retaining SSH access. Once DNS resolves to the VPS:

```sh
sudo certbot --nginx -d YOUR_DOMAIN --redirect
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

Certbot prompts for account details and terms. Add `-d www.YOUR_DOMAIN` only if it also resolves to the VPS. Debian's renewal timer handles renewal. Do not rerun setup after enabling HTTPS; install only the next site archive.

## Verify the deployed site

```sh
curl --fail https://YOUR_DOMAIN/healthz
curl --fail https://YOUR_DOMAIN/release.json
curl --fail -I https://YOUR_DOMAIN/projects/mb4x-radio-archive/
curl --fail -I https://YOUR_DOMAIN/projects/expeditionops/
curl --fail -r 0-15 -D - -o /dev/null https://YOUR_DOMAIN/audio/recording-01.mp3
```

The audio request should return **206 Partial Content**. Open both projects in a browser, test archive playback, and export/import an ExpeditionOps backup. Missing paths/assets return 404, not the homepage.

ExpeditionOps remains browser-local. Plans saved under the old GitHub origin are not copied by moving server files; import JSON backups into the new origin. Unpublishing the old site does not delete browser storage, but the new domain cannot read it directly.

## Updates and rollback

Upload a tested release and install it. Three releases are retained by default; `--keep 2` through `--keep 5` are supported. Remove the uploaded archive once checks pass.

```sh
sudo n4ml-site install /var/tmp/n4ml-deploy/n4ml-vps.tar.gz
sudo n4ml-site rollback
sudo n4ml-site status
```

Rollback verifies the previous release before switching; running it again switches back. There is no server-side user data in the releases. Back up `/etc/nginx` and `/etc/letsencrypt` separately, and keep ExpeditionOps JSON backups.

References: [Nginx static serving](https://docs.nginx.com/nginx/admin-guide/web-server/serving-static-content/), [precompressed files](https://nginx.org/en/docs/http/ngx_http_gzip_static_module.html), [Debian's Certbot package](https://packages.debian.org/trixie/python3-certbot-nginx).


## Automatic GitHub deployment

The production server is `http://162.0.233.219` for now. Every successful push to `main`, or a manual workflow run on `main`, deploys after lint, application tests, and both constrained Debian/Nginx jobs pass. Pull requests and release tags never deploy to production. The `production` environment permits only `main`. Deployments are serialized and an active deployment is not cancelled by a newer push.

The production environment holds the encrypted `VPS_SSH_KEY` secret plus `VPS_HOST`, `VPS_PORT`, `VPS_USER`, `VPS_URL`, and `VPS_KNOWN_HOSTS` variables. `SITE_URL` is a repository variable used during the build. The server host key is pinned from the initial administrative connection; workflow runs never trust a fresh network key automatically. The root password is not used by GitHub.

Server setup for this transport (run once as administrator, after the Nginx setup):

```sh
sudo bash deploy/setup-cicd.sh /path/to/ci-public-key.pub
```

This creates the unprivileged `n4ml-deploy` account and installs a forced SSH command. Its key accepts only `status` or a release stream with an exact commit and SHA-256. It cannot open a shell, allocate a terminal, forward connections, edit Nginx, or use sudo. The receiver checks the upload, verifies all extracted files, requires the expected commit before activation, and removes the upload afterward. It then checks the receipt, pages, assets, contact index, and range requests for all eight recordings. A failed server-side health check restores the previous release when one exists. GitHub repeats the live checks from outside the VPS.

Keep the server-side deployment tools root-owned and update them through an administrative session when their code changes; routine CI deployment updates only static site files. For manual rollback after CI is configured, preserve file ownership by using:

```sh
sudo -u n4ml-deploy /usr/local/sbin/n4ml-site rollback
sudo -u n4ml-deploy /usr/local/sbin/n4ml-site status
```

To change to a domain later, update Nginx and DNS, obtain HTTPS, then change `SITE_URL` and `VPS_URL` and run the workflow on `main`.
