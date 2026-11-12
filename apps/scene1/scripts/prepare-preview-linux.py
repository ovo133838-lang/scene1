"""Prepare an isolated teaching preview after explicit approval; no formal release gates bypassed.

Run as root on the inspected Ubuntu host. Does not alter existing databases,
services, firewall rules, panel credentials, or the formal scene1 deployment.
Secrets are generated on the host, never printed, and stored in root-only files.
"""
import hashlib
import json
import os
import pathlib
import pwd
import secrets
import socket
import subprocess
import tarfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path('/opt/scene1-preview')
CONFIG = pathlib.Path('/etc/scene1-preview')
BUNDLE = pathlib.Path('/tmp/scene1-v1.0.0-preview.tar.gz')
BUNDLE_SHA256 = 'ee6757a310013be4e73fc7aa390ff8d3c2027d1edfbb35b4c67c8fac6df5aa2a'
VERSION = 'v1.0.0-preview.e5370c51a417'
CONTAINER = '1Panel-mysql-3fae'
DB_HOST = '172.18.0.1'
SHOP_DB, MOCK_DB = 'scene1_preview', 'scene1_mock_preview'
SHOP_USER, MOCK_USER = 'scene1_preview', 'scene1_mock_preview'


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def mysql(sql):
    # Root authentication remains inside the existing container environment.
    return run(['docker', 'exec', '-i', CONTAINER, 'sh', '-c',
                'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'], input=sql).stdout


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(text)


def request(path, body=None, token=None, method=None):
    headers = {'Content-Type': 'application/json', 'Idempotency-Key': secrets.token_hex(16)}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request('http://127.0.0.1:18080' + path, data, headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)['data']


def main():
    assert os.geteuid() == 0, 'root needed for new isolated systemd service'
    assert not ROOT.exists() and not CONFIG.exists(), 'preview already exists; inspect instead of overwriting'
    assert hashlib.sha256(BUNDLE.read_bytes()).hexdigest() == BUNDLE_SHA256, 'candidate bundle hash mismatch'
    gateway = run(['docker', 'inspect', '-f', '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}', CONTAINER]).stdout.strip()
    assert gateway == DB_HOST, 'database gateway changed; re-review exact grant host'
    for port in (18080, 18081):
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1', port)) != 0, 'preview port occupied'
    for name in ('shop', 'mock'):
        assert not pathlib.Path('/etc/systemd/system/scene1-preview-' + name + '.service').exists()
    assert not mysql("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN ('scene1_preview','scene1_mock_preview');").strip(), 'preview database exists; do not reset'
    assert not mysql("SELECT User FROM mysql.user WHERE User IN ('scene1_preview','scene1_mock_preview');").strip(), 'preview account exists; do not change credentials'
    try:
        pwd.getpwnam('scene1-preview')
        raise AssertionError('system account exists; re-review ownership')
    except KeyError:
        pass
    release = ROOT / 'releases' / VERSION
    release.mkdir(parents=True, mode=0o755)
    with tarfile.open(BUNDLE, 'r:gz') as archive:
        allowed = {'scene1', 'smoke.py', 'deploy-linux.sh', 'scene1-shop.service', 'scene1-mock.service', 'SHA256SUMS', 'candidate-version.json'}
        assert set(archive.getnames()) == allowed
        for member in archive.getmembers():
            assert member.isfile() and member.name in allowed, 'unexpected bundle entry'
        archive.extractall(release, filter='data')
    for line in (release / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split()
        assert hashlib.sha256((release / name).read_bytes()).hexdigest() == digest
    os.chmod(release / 'scene1', 0o755)
    CONFIG.mkdir(mode=0o700)
    values = {k: secrets.token_hex(32) for k in ('shop_db', 'mock_db', 'login', 'hmac', 'admin')}
    # Passwords have only hex characters; schema/user/host identifiers are fixed constants.
    sql = ''
    for db, user, password in [(SHOP_DB, SHOP_USER, values['shop_db']), (MOCK_DB, MOCK_USER, values['mock_db'])]:
        sql += f"CREATE DATABASE `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;\n"
        sql += f"CREATE USER '{user}'@'{DB_HOST}' IDENTIFIED BY '{password}';\n"
        sql += f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'{DB_HOST}';\n"
    mysql(sql)
    run(['useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'scene1-preview'])
    common = {'SCENE1_PASSWORD': values['login'], 'SCENE1_HMAC_SECRET': values['hmac'],
              'SCENE1_ADMIN_TOKEN': values['admin'], 'SCENE1_DEMO': 'true',
              'SCENE1_SHOP_URL': 'http://127.0.0.1:18080', 'SCENE1_MOCK_URL': 'http://127.0.0.1:18081'}
    (ROOT / 'current').symlink_to(release, target_is_directory=True)
    for mode, port, db, user, key in [('shop', 18080, SHOP_DB, SHOP_USER, 'shop_db'), ('mock', 18081, MOCK_DB, MOCK_USER, 'mock_db')]:
        env = dict(common)
        env.update(SCENE1_PORT=str(port), SCENE1_HOST='0.0.0.0' if mode == 'shop' else '127.0.0.1')
        env['SCENE1_MYSQL_DSN' if mode == 'shop' else 'SCENE1_MOCK_DSN'] = f'{user}:{values[key]}@tcp(127.0.0.1:3306)/{db}?parseTime=true&loc=UTC'
        write_private(CONFIG / (mode + '.env'), ''.join(k + '=' + v + '\n' for k, v in env.items()))
        unit = f'''[Unit]
Description=Scene1 isolated teaching preview {mode}
After=network-online.target docker.service
Wants=network-online.target
[Service]
User=scene1-preview
Group=scene1-preview
WorkingDirectory=/opt/scene1-preview/current
EnvironmentFile=/etc/scene1-preview/{mode}.env
ExecStart=/opt/scene1-preview/current/scene1 -mode {mode} -env /dev/null
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
'''
        pathlib.Path('/etc/systemd/system/scene1-preview-' + mode + '.service').write_text(unit)
    started = False
    try:
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'start', 'scene1-preview-mock', 'scene1-preview-shop'])
        started = True
        for attempt in range(60):
            try:
                ready = request('/health/ready')
                assert ready['version'] == VERSION
                break
            except (OSError, urllib.error.URLError):
                time.sleep(1)
        else:
            raise RuntimeError('preview readiness timed out')
        operator = request('/api/v1/auth/login', {'login_name': 'operator', 'password': values['login']})['token']
        try:
            products = request('/api/v1/operator/products', token=operator)['items']
            product = next(p for p in products if p['unit_price_cents'] == '10000')
            request('/api/v1/operator/products/' + product['id'],
                    {'version': product['version'], 'sale_status': 'ON_SHELF', 'reason': '教学预览首次上架'}, operator, method='PATCH')
        finally:
            request('/api/v1/auth/logout', {}, operator)
        env = os.environ.copy()
        env.update(SCENE1_PASSWORD=values['login'], SCENE1_EXPECT_VERSION=VERSION)
        smoke = json.loads(run(['python3', str(release / 'smoke.py')], env=env).stdout)
        result = {'status': 'PASS', 'kind': 'dev-branch-preview', 'formal_release': False,
                  'version': VERSION, 'mysql': '8.4.13', 'bundle_sha256': BUNDLE_SHA256,
                  'shop_port': 18080, 'mock_loopback_port': 18081, 'smoke': smoke,
                  'firewall_changed': False, 'credentials': 'root-only /etc/scene1-preview/*.env; not printed'}
        (release / 'preview-result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    except Exception:
        if started:
            subprocess.run(['systemctl', 'stop', 'scene1-preview-shop', 'scene1-preview-mock'], capture_output=True)
        print('Preview failed; only preview services stopped. New schema/config/artifacts retained for diagnosis; existing services untouched.')
        raise


if __name__ == '__main__':
    main()
