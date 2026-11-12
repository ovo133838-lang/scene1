#!/usr/bin/env bash
set -euo pipefail
# Run on an authorized teaching Linux host. No DB downgrade or secret copying.
bundle=${1:?bundle tar.gz required}
revision=${2:?full release commit required}
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid release revision'; exit 2; }
release_root=${SCENE1_RELEASE_ROOT:-/opt/scene1}
[[ "$release_root" = /* && "$release_root" != / ]] || exit 2
for required in /etc/scene1/shop.env /etc/scene1/mock.env /etc/systemd/system/scene1-shop.service /etc/systemd/system/scene1-mock.service; do
  test -f "$required" || { echo "missing host prerequisite: $required"; exit 2; }
done
destination="$release_root/releases/$revision"
test ! -e "$destination" || { echo 'release already exists; inspect previous run'; exit 2; }
previous=$(readlink -f "$release_root/current" || true)
mkdir -p "$destination"
tar -xzf "$bundle" -C "$destination" --no-same-owner
test -x "$destination/scene1"
(cd "$destination" && sha256sum -c SHA256SUMS)
rollback() {
  echo 'release failed; restore previous executable; keep DB forward migrations and evidence'
  if [[ -n "$previous" && -d "$previous" ]]; then
    ln -sfn "$previous" "$release_root/current.next"
    mv -Tf "$release_root/current.next" "$release_root/current"
    systemctl restart scene1-mock scene1-shop || true
  else
    systemctl stop scene1-shop scene1-mock || true
  fi
}
trap rollback ERR
ln -sfn "$destination" "$release_root/current.next"
mv -Tf "$release_root/current.next" "$release_root/current"
systemctl restart scene1-mock scene1-shop
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18080/health/ready >/dev/null && curl -fsS http://127.0.0.1:18081/health/live >/dev/null; then break; fi
  sleep 1
done
# root-readable env file contains SCENE1_PASSWORD; only the child sees it.
set -a
source /etc/scene1/shop.env
set +a
SCENE1_EXPECT_VERSION="$revision" python3 "$destination/smoke.py" >"$destination/smoke-result.json"
printf '{"revision":"%s","previous":"%s","status":"PASS"}\n' "$revision" "$previous" >"$destination/deployment.json"
trap - ERR
cat "$destination/deployment.json" "$destination/smoke-result.json"
