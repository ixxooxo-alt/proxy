"""Isolated routing probe: original rules, all policy groups terminate at REJECT.

No subscription, TUN, system proxy, remote DNS, or remote health checks.
Only an ephemeral loopback HTTP proxy is opened for three CONNECT requests.
"""
from pathlib import Path
import json
import shutil
import socket
import subprocess
import time
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'audit-evidence' / 'qwen-route-check'
DEST.mkdir(exist_ok=True)
original = yaml.safe_load((ROOT / 'review-input/proxy-rules/dist/mihomo/mihomo-core.yaml').read_text())
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
config = {
    'mixed-port': port, 'allow-lan': False, 'bind-address': '127.0.0.1',
    'mode': 'rule', 'log-level': 'debug', 'ipv6': False,
    'geo-auto-update': False, 'geodata-mode': False,
    'dns': {'enable': False}, 'sniffer': {'enable': False},
    'proxy-groups': [{'name': g['name'], 'type': 'select', 'proxies': ['REJECT']}
                     for g in original['proxy-groups']],
    'rules': original['rules'],
}
assert config['rules'] == original['rules']
(DEST / 'probe.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
for source, target in [('geosite.dat', 'GeoSite.dat'), ('geoip.metadb', 'geoip.metadb')]:
    shutil.copyfile(ROOT / 'audit-tools/geodata' / source, DEST / target)
log_path = DEST / 'mihomo.log'
results = []
with log_path.open('w') as log:
    proc = subprocess.Popen([str(ROOT / 'audit-tools/mihomo-v1.19.31'), '-d', str(DEST),
                             '-f', str(DEST / 'probe.yaml')], stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError(log_path.read_text())
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError('Local test listener not ready')
        for host in ['qwen.ai', 'chat.qwen.ai', 'openai.com']:
            with socket.create_connection(('127.0.0.1', port), timeout=2) as s:
                s.settimeout(2)
                s.sendall(f'CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n'.encode())
                try:
                    response = s.recv(4096).decode(errors='replace').splitlines()[0:1]
                except OSError as e:
                    response = [str(e)]
                results.append({'host': host, 'response': response})
                time.sleep(0.1)
        time.sleep(0.2)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
logs = log_path.read_text()
matches = [line for line in logs.splitlines() if any(h in line for h in ('qwen.ai', 'openai.com'))]
result = {'original_rules_preserved': True, 'outbound_policy_stub': 'all groups -> REJECT',
          'network_scope': 'loopback only; no TUN or system proxy', 'requests': results,
          'routing_log': matches}
(ROOT / 'audit-evidence/qwen-routing-proof.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
assert all(any(f'--> {host}:443' in line and 'GeoSite(cn)' in line and '国内直连' in line
               for line in matches) for host in ('qwen.ai', 'chat.qwen.ai')), logs
