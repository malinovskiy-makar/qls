# -*- coding: utf-8 -*-
"""Вход для VPN на машине tg-relay: конфиги и скрипты (deploy/web_relay/README.md).

tg-relay принимает 443/80 и пересылает TCP на боевой 8443/8080 с PROXY
protocol; боевой nginx верит заголовку только от адреса tg-relay
(`set_real_ip_from` из WEB_RELAY_IP, файл пишет deploy/web_relay/prod_realip.sh).

Конфиг nginx разбирается на блоки, а не ищется строкой: «строка есть в
файле» проходила бы, даже если 8443 стоит не в том server-блоке.

Что Django берёт адрес из X-Real-IP и не верит клиентскому X-Forwarded-For —
problems/tests/test_auth_hardening.py, ClientIpTests. Здесь — только то, что
nginx кладёт в эти заголовки.

Живые тесты (класс LiveNginxTests) поднимают nginx того же образа с боевым
конфигом и самоподписанным сертификатом; без Docker они пропускаются.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import skipUnless

import yaml
from django.test import SimpleTestCase

КОРЕНЬ = Path(__file__).resolve().parents[2]
DJANGO_CONF = КОРЕНЬ / 'deploy' / 'nginx' / 'available' / 'django.conf'
COMPOSE = КОРЕНЬ / 'deploy' / 'docker-compose.yml'
RELAY = КОРЕНЬ / 'deploy' / 'web_relay'
STREAM_CONF = RELAY / 'nginx-stream.conf'
SETUP = RELAY / 'setup.sh'
ROLLBACK = RELAY / 'rollback.sh'
PROD_REALIP = RELAY / 'prod_realip.sh'
PROD_FIREWALL = RELAY / 'prod_firewall.sh'
FIREWALL_UNIT = КОРЕНЬ / 'deploy' / 'systemd' / 'weconomics-web-relay-firewall.service'

PROD_IP = '135.106.181.151'


# ─── разбор конфига nginx ───────────────────────────────────────────────────

def _tokens(text):
    """Слова, строки в кавычках, `{`, `}`, `;`; комментарии выброшены."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == '#':
            while i < n and text[i] != '\n':
                i += 1
        elif ch in '{};':
            yield ch
            i += 1
        elif ch in '"\'':
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == '\\' else 1
            yield text[i + 1:j]
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '{};':
                j += 1
            yield text[i:j]
            i = j


def parse_nginx(text):
    """Дерево: список (имя, [аргументы], [дети] или None)."""
    stack = [[]]
    words = []
    for tok in _tokens(text):
        if tok == ';':
            stack[-1].append((words[0], words[1:], None))
            words = []
        elif tok == '{':
            node = (words[0], words[1:], [])
            stack[-1].append(node)
            stack.append(node[2])
            words = []
        elif tok == '}':
            stack.pop()
        else:
            words.append(tok)
    assert len(stack) == 1 and not words, 'конфиг nginx не разобрался: скобки не сошлись'
    return stack[0]


def directives(nodes, name):
    return [args for n, args, _ in nodes if n == name]


def blocks(nodes, name):
    return [(args, kids) for n, args, kids in nodes if n == name and kids is not None]


def walk(nodes):
    for node in nodes:
        yield node
        if node[2]:
            yield from walk(node[2])


def listens(server):
    """{порт: множество флагов} по директивам listen одного server-блока."""
    result = {}
    for args in directives(server, 'listen'):
        port = int(args[0].rsplit(':', 1)[-1])
        result.setdefault(port, set()).update(args[1:])
    return result


def django_servers():
    return [kids for _args, kids in blocks(parse_nginx(DJANGO_CONF.read_text('utf-8')), 'server')]


def code_lines(path):
    """Строки скрипта без строк-комментариев."""
    return [line for line in path.read_text('utf-8').splitlines()
            if not line.lstrip().startswith('#')]


# ─── 1. слушатели 8443/8080 рядом с 443/80 ─────────────────────────────────

class ListenersTests(SimpleTestCase):

    def test_у_каждого_блока_с_443_есть_8443_ssl_proxy_protocol(self):
        найдено = 0
        for server in django_servers():
            порты = listens(server)
            if 443 not in порты:
                continue
            найдено += 1
            with self.subTest(server_name=directives(server, 'server_name')):
                self.assertIn(8443, порты, 'блок слушает 443, а 8443 для входа нет')
                self.assertTrue({'ssl', 'proxy_protocol'} <= порты[8443])
                self.assertEqual('default_server' in порты[443],
                                 'default_server' in порты[8443],
                                 'флаг default_server у 8443 должен быть как у 443')
        self.assertEqual(найдено, 3, 'блоков с 443 должно быть три: _, бой, dev')

    def test_у_каждого_блока_с_80_есть_8080_proxy_protocol(self):
        найдено = 0
        for server in django_servers():
            порты = listens(server)
            if 80 not in порты:
                continue
            найдено += 1
            with self.subTest(server_name=directives(server, 'server_name')):
                self.assertIn(8080, порты, 'блок слушает 80, а 8080 для входа нет')
                self.assertIn('proxy_protocol', порты[8080])
                self.assertNotIn('ssl', порты[8080])
                self.assertEqual('default_server' in порты[80],
                                 'default_server' in порты[8080],
                                 'флаг default_server у 8080 должен быть как у 80')
        self.assertEqual(найдено, 3, 'блоков с 80 должно быть три: _, бой, dev')

    def test_8080_и_8443_только_с_proxy_protocol(self):
        """Без proxy_protocol первая строка PROXY пошла бы в TLS/HTTP как мусор."""
        for server in django_servers():
            for порт in (8080, 8443):
                if порт in listens(server):
                    self.assertIn('proxy_protocol', listens(server)[порт])


# ─── 2. realip: real_ip_header здесь, set_real_ip_from — из WEB_RELAY_IP ───

class RealIpTests(SimpleTestCase):

    def test_real_ip_header_proxy_protocol_на_уровне_http(self):
        верх = parse_nginx(DJANGO_CONF.read_text('utf-8'))
        self.assertEqual(directives(верх, 'real_ip_header'), [['proxy_protocol']])

    def test_set_real_ip_from_не_в_конфиге_а_в_файле_из_env(self):
        """Ни 0.0.0.0/0, ни любого другого адреса в django.conf: доверенный
        адрес один — WEB_RELAY_IP, и пишет его только prod_realip.sh."""
        все = [args for name, args, _ in walk(parse_nginx(DJANGO_CONF.read_text('utf-8')))
               if name == 'set_real_ip_from']
        self.assertEqual(все, [], 'set_real_ip_from в django.conf: %r' % все)

    def test_файл_realip_попадает_в_conf_d_который_видит_nginx(self):
        текст = PROD_REALIP.read_text('utf-8')
        out = re.search(r'OUT_FILE="\$\{OUT_FILE:-([^}]+)\}"', текст).group(1)
        self.assertEqual(out, '/srv/weconomics/nginx/conf.d/web_relay_realip.conf')
        тома = yaml.safe_load(COMPOSE.read_text('utf-8'))['services']['nginx']['volumes']
        self.assertIn('/srv/weconomics/nginx/conf.d:/etc/nginx/conf.d:ro', тома)
        self.assertIn('/srv/weconomics/.env', текст)


def _bash():
    if os.name == 'nt':
        git_bash = Path(r'C:\Program Files\Git\bin\bash.exe')
        return str(git_bash) if git_bash.exists() else None
    return shutil.which('bash')


@skipUnless(_bash(), 'нет bash')
class ProdRealipScriptTests(SimpleTestCase):
    """prod_realip.sh по-настоящему, без docker (NGINX_RELOAD=0)."""

    def run_script(self, env_line):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        env_file = tmp / '.env'
        env_file.write_bytes(('SECRET_KEY=x\r\n%s\r\n' % env_line).encode('utf-8'))
        out = tmp / 'web_relay_realip.conf'
        env = dict(os.environ, ENV_FILE=env_file.as_posix(), OUT_FILE=out.as_posix(),
                   NGINX_RELOAD='0')
        proc = subprocess.run([_bash(), PROD_REALIP.as_posix()], env=env,
                              capture_output=True, text=True, encoding='utf-8')
        текст = out.read_text('utf-8') if out.exists() else None
        return proc.returncode, текст

    def test_адрес_из_env_становится_set_real_ip_from(self):
        код, текст = self.run_script('WEB_RELAY_IP="192.0.2.10"')
        self.assertEqual(код, 0)
        верх = parse_nginx(текст)
        self.assertEqual(directives(верх, 'set_real_ip_from'), [['192.0.2.10']])

    def test_пусто_значит_не_верить_никому(self):
        код, текст = self.run_script('WEB_RELAY_IP=')
        self.assertEqual(код, 0)
        self.assertEqual(directives(parse_nginx(текст), 'set_real_ip_from'), [])

    def test_маска_и_мусор_отвергаются_и_файл_не_пишется(self):
        for плохое in ('0.0.0.0/0', '0.0.0.0', '10.0.0.0/8', '192.0.2.10:443',
                       '300.1.1.1', '127.0.0.1', 'tg.weconomics.ai'):
            with self.subTest(значение=плохое):
                код, текст = self.run_script('WEB_RELAY_IP=%s' % плохое)
                self.assertNotEqual(код, 0)
                self.assertIsNone(текст)


# ─── 3. /healthz для Gcore и acme-challenge на 8080 ─────────────────────────

class HealthAndAcmeTests(SimpleTestCase):

    def test_healthz_в_default_блоке_который_слушает_8080(self):
        """Gcore спрашивает http://<адрес tg-relay>/healthz без имени сайта:
        запрос приходит на 8080 и попадает в default_server."""
        default = [s for s in django_servers()
                   if 'default_server' in listens(s).get(80, set())]
        self.assertEqual(len(default), 1)
        server = default[0]
        self.assertIn('default_server', listens(server).get(8080, set()))
        health = [kids for args, kids in blocks(server, 'location') if args == ['=', '/healthz']]
        self.assertEqual(len(health), 1, 'нет location = /healthz в default-блоке')
        self.assertEqual(directives(health[0], 'return')[0][0], '200')

    def test_acme_challenge_на_8080_как_на_80(self):
        for server in django_servers():
            порты = listens(server)
            if 80 not in порты or 'default_server' in порты[80]:
                continue
            with self.subTest(server_name=directives(server, 'server_name')):
                self.assertIn(8080, порты)
                acme = [kids for args, kids in blocks(server, 'location')
                        if args == ['/.well-known/acme-challenge/']]
                self.assertEqual(len(acme), 1)
                self.assertEqual(directives(acme[0], 'root'), [['/var/www/certbot']])


# ─── 4. редиректы без порта ─────────────────────────────────────────────────

class RedirectTests(SimpleTestCase):

    def test_return_редиректы_без_порта(self):
        редиректов = 0
        for name, args, _ in walk(parse_nginx(DJANGO_CONF.read_text('utf-8'))):
            if name == 'return' and args[0] in ('301', '302', '307', '308'):
                редиректов += 1
                with self.subTest(редирект=args):
                    self.assertEqual(args[1], 'https://$host$request_uri')
        self.assertGreaterEqual(редиректов, 2)
        for name, args, _ in walk(parse_nginx(DJANGO_CONF.read_text('utf-8'))):
            for арг in args:
                self.assertNotRegex(арг, r'\$server_port|\$proxy_protocol_port|:8080|:8443')

    def test_port_in_redirect_off(self):
        """Свои редиректы nginx на 8443 иначе дописали бы «:8443»."""
        верх = parse_nginx(DJANGO_CONF.read_text('utf-8'))
        self.assertEqual(directives(верх, 'port_in_redirect'), [['off']])


# ─── 5. stream-конфиг на tg-relay ───────────────────────────────────────────

class StreamConfTests(SimpleTestCase):

    def setUp(self):
        stream = blocks(parse_nginx(STREAM_CONF.read_text('utf-8')), 'stream')
        self.assertEqual(len(stream), 1)
        self.stream = stream[0][1]

    def test_upstream_на_боевой_8443_и_8080(self):
        upstreams = {args[0]: directives(kids, 'server') for args, kids in blocks(self.stream, 'upstream')}
        self.assertEqual(upstreams, {'prod_https': [[PROD_IP + ':8443']],
                                     'prod_http': [[PROD_IP + ':8080']]})

    def test_443_и_80_уходят_с_proxy_protocol(self):
        servers = {}
        for _args, kids in blocks(self.stream, 'server'):
            for порт in listens(kids):
                servers[порт] = kids
        self.assertEqual(set(servers), {80, 443})
        for порт, upstream in ((443, 'prod_https'), (80, 'prod_http')):
            with self.subTest(порт=порт):
                self.assertEqual(directives(servers[порт], 'proxy_pass'), [[upstream]])
                self.assertEqual(directives(servers[порт], 'proxy_protocol'), [['on']])
        self.assertEqual(directives(servers[443], 'proxy_timeout'), [['1h']])


# ─── 6. docker-compose ──────────────────────────────────────────────────────

class ComposeTests(SimpleTestCase):

    def test_nginx_публикует_8080_и_8443(self):
        порты = yaml.safe_load(COMPOSE.read_text('utf-8'))['services']['nginx']['ports']
        for пара in ('80:80', '443:443', '8080:8080', '8443:8443'):
            self.assertIn(пара, порты)


# ─── 7. setup.sh и rollback.sh не трогают туннель бота и вход по SSH ────────

ЗАПРЕТНОЕ = [
    (r'sshd', 'настройки sshd'),
    (r'PasswordAuthentication|PermitRootLogin', 'настройки входа по SSH'),
    (r'tgtunnel', 'пользователь и ключ туннеля'),
    (r'authorized_keys|\.ssh\b', 'ключи SSH'),
    (r'\bufw\s+(--force\s+)?(reset|default|enable|disable)\b', 'политика ufw'),
    (r'^\s*systemctl\s+(stop|restart|disable|mask|kill|reload)\s+tg-tunnel',
     'служба туннеля'),
]


class RelayScriptsTests(SimpleTestCase):

    def test_setup_проверяет_туннель_до_и_после(self):
        строки = code_lines(SETUP)
        проверки = [i for i, s in enumerate(строки) if 'systemctl is-active tg-tunnel' in s]
        self.assertGreaterEqual(len(проверки), 2)
        первое_изменение = min(i for i, s in enumerate(строки)
                               if re.search(r'apt-get install|mv -f|install -m|ufw allow', s))
        перезапуск = max(i for i, s in enumerate(строки) if 'systemctl restart nginx' in s)
        self.assertLess(проверки[0], первое_изменение, 'туннель проверяется уже после правок')
        self.assertGreater(проверки[-1], перезапуск, 'после перезапуска nginx туннель не проверяется')

    def test_setup_и_rollback_не_трогают_ssh_туннель_и_политику_ufw(self):
        for путь in (SETUP, ROLLBACK):
            текст = '\n'.join(code_lines(путь))
            for шаблон, что in ЗАПРЕТНОЕ:
                with self.subTest(файл=путь.name, что=что):
                    self.assertIsNone(re.search(шаблон, текст, re.M),
                                      '%s трогает %s' % (путь.name, что))

    def test_ufw_только_80_и_443(self):
        for путь in (SETUP, ROLLBACK):
            for строка in code_lines(путь):
                # Без кавычки перед ufw: строка-образец в grep — не команда.
                for m in re.finditer(r'(?<!["\'])\bufw\s+(?:delete\s+)?allow\s+(\S+)', строка):
                    self.assertIn(m.group(1), ('80/tcp', '443/tcp'), строка)

    def test_setup_останавливается_на_чужом_на_80_443(self):
        текст = SETUP.read_text('utf-8')
        self.assertIn("sport = :80 or sport = :443", текст)
        self.assertRegex(текст, r'OLD_SITES=\(default tg_relay\)')


# ─── 8. в Django уходит $remote_addr после realip ───────────────────────────

class ForwardedHeadersTests(SimpleTestCase):

    def test_x_real_ip_и_x_forwarded_for_ровно_remote_addr(self):
        найдено = 0
        for name, args, _ in walk(parse_nginx(DJANGO_CONF.read_text('utf-8'))):
            if name == 'proxy_set_header' and args[0] in ('X-Real-IP', 'X-Forwarded-For'):
                найдено += 1
                with self.subTest(заголовок=args):
                    self.assertEqual(args[1], '$remote_addr')
        self.assertEqual(найдено, 8, 'четыре location с прокси, по два заголовка')


# ─── файрвол боевого ────────────────────────────────────────────────────────

class FirewallTests(SimpleTestCase):

    def test_скрипт_пускает_к_8080_8443_только_tg_relay(self):
        текст = '\n'.join(code_lines(PROD_FIREWALL))
        self.assertIn('source "$HERE/relay_ip.sh"', текст)
        self.assertIn('/srv/weconomics/.env', текст)
        self.assertIn('DOCKER-USER', текст)
        self.assertIn('PORTS=(8080 8443)', текст)
        self.assertIn('--ctorigdstport "$port"', текст)
        self.assertRegex(текст, r'-s "\$RELAY_IP"[^\n]*\\\n[^\n]*-j RETURN')
        self.assertRegex(текст, r'--ctorigdstport "\$port" --ctdir ORIGINAL -j DROP')
        self.assertIn('iptables -F "$CHAIN"', текст)

    def test_юнит_после_docker_и_запускает_скрипт(self):
        текст = FIREWALL_UNIT.read_text('utf-8')
        self.assertIn('After=docker.service', текст)
        self.assertIn('Type=oneshot', текст)
        self.assertIn('ExecStart=/srv/weconomics/app/deploy/web_relay/prod_firewall.sh', текст)


# ─── живые тесты: nginx того же образа с боевым конфигом ────────────────────

def _docker_ok():
    if not shutil.which('docker'):
        return False
    try:
        return subprocess.run(['docker', 'info'], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _nginx_image():
    текст = COMPOSE.read_text('utf-8')
    return yaml.safe_load(текст)['services']['nginx']['image']


def _self_signed(folder):
    """fullchain.pem и privkey.pem, самоподписанные, на имена боя и dev."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'weconomics.ai')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName(
                [x509.DNSName(d) for d in ('weconomics.ai', 'weconomics.site', 'dev.weconomics.ai')]),
                critical=False)
            .sign(key, hashes.SHA256()))
    for live in ('weconomics.site', 'dev.weconomics.ai'):
        d = folder / 'letsencrypt' / 'live' / live
        d.mkdir(parents=True)
        (d / 'fullchain.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (d / 'privkey.pem').write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))


def _relay_for_test(text):
    """Stream-конфиг tg-relay в том же контейнере: боевой — 127.0.0.1, а
    443/80 входа — 9443/9080 (свои 443/80 в контейнере занимает боевой блок)."""
    text = text.replace(PROD_IP, '127.0.0.1')
    text = re.sub(r'listen (\[::\]:)?443;', lambda m: 'listen %s9443;' % (m.group(1) or ''), text)
    return re.sub(r'listen (\[::\]:)?80;', lambda m: 'listen %s9080;' % (m.group(1) or ''), text)


@skipUnless(_docker_ok(), 'Docker недоступен — живой тест nginx пропущен')
class LiveNginxTests(SimpleTestCase):
    """Боевой django.conf + stream-конфиг tg-relay в одном контейнере nginx.

    Доверенный адрес входа — 127.0.0.1 (оттуда ходит stream-часть). curl
    шлёт PROXY-заголовок сам (`--haproxy-clientip`) или идёт через stream-часть
    с адреса 127.0.0.5 (`--interface`).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.name = 'weco-relay-test-' + uuid.uuid4().hex[:8]
        tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, tmp, True)
        _self_signed(tmp)
        (tmp / 'conf.d').mkdir()
        shutil.copy(DJANGO_CONF, tmp / 'conf.d' / 'weconomics.conf')
        (tmp / 'conf.d' / 'web_relay_realip.conf').write_text('set_real_ip_from 127.0.0.1;\n')
        (tmp / 'relay').mkdir()
        (tmp / 'relay' / 'stream.conf').write_text(
            _relay_for_test(STREAM_CONF.read_text('utf-8')), encoding='utf-8')

        start = ("grep -q relay/stream.conf /etc/nginx/nginx.conf || "
                 "echo 'include /etc/nginx/relay/stream.conf;' >> /etc/nginx/nginx.conf; "
                 "exec nginx -g 'daemon off;'")
        cmd = ['docker', 'create', '--name', cls.name]
        for host in ('web', 'ws', 'web-dev', 'ws-dev'):
            cmd += ['--add-host', '%s:127.0.0.1' % host]
        cmd += [_nginx_image(), 'sh', '-c', start]
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        cls.addClassCleanup(subprocess.run, ['docker', 'rm', '-f', cls.name], capture_output=True)
        for src, dst in ((tmp / 'conf.d', '/etc/nginx/'), (tmp / 'letsencrypt', '/etc/'),
                         (tmp / 'relay', '/etc/nginx/')):
            subprocess.run(['docker', 'cp', str(src), '%s:%s' % (cls.name, dst)],
                           check=True, capture_output=True)
        subprocess.run(['docker', 'start', cls.name], check=True, capture_output=True)
        for _ in range(40):
            if cls.curl('-o', '/dev/null', '-w', '%{http_code}', 'http://127.0.0.1/healthz') == '200':
                break
            time.sleep(0.25)
        else:
            logs = subprocess.run(['docker', 'logs', cls.name], capture_output=True, text=True)
            raise AssertionError('nginx не поднялся:\n' + logs.stdout + logs.stderr)

    @classmethod
    def curl(cls, *args):
        proc = subprocess.run(['docker', 'exec', cls.name, 'curl', '-sS', '-m', '5', *args],
                              capture_output=True, text=True)
        return proc.stdout.strip()

    def log_lines(self, marker):
        proc = subprocess.run(['docker', 'logs', self.name], capture_output=True, text=True)
        return [s for s in (proc.stdout + proc.stderr).splitlines() if marker in s]

    def nginx_t(self):
        return subprocess.run(['docker', 'exec', self.name, 'nginx', '-t'],
                              capture_output=True, text=True)

    def test_1_nginx_t_с_файлом_realip(self):
        self.assertEqual(self.nginx_t().returncode, 0, self.nginx_t().stderr)

    def test_2_healthz_на_8080_с_proxy_без_имени_сайта(self):
        код = self.curl('--haproxy-protocol', '--haproxy-clientip', '203.0.113.7',
                        '-o', '/dev/null', '-w', '%{http_code}', 'http://127.0.0.1:8080/healthz')
        self.assertEqual(код, '200')

    def test_3_адрес_из_proxy_заголовка_в_журнале_на_8443(self):
        код = self.curl('-k', '--haproxy-protocol', '--haproxy-clientip', '198.51.100.9',
                        '--resolve', 'weconomics.ai:8443:127.0.0.1',
                        '-o', '/dev/null', '-w', '%{http_code}',
                        'https://weconomics.ai:8443/429.html?probe-8443')
        self.assertEqual(код, '404')
        строки = self.log_lines('probe-8443')
        self.assertTrue(строки and строки[-1].startswith('198.51.100.9 '), строки)

    def test_4_редирект_на_8080_без_порта(self):
        ответ = self.curl('--haproxy-protocol', '--haproxy-clientip', '203.0.113.8',
                          '-H', 'Host: weconomics.ai', '-o', '/dev/null',
                          '-w', '%{http_code} %{redirect_url}', 'http://127.0.0.1:8080/probe-80')
        self.assertEqual(ответ, '301 https://weconomics.ai/probe-80')
        строки = self.log_lines('probe-80')
        self.assertTrue(строки and строки[-1].startswith('203.0.113.8 '), строки)

    def test_5_вся_цепочка_через_stream_часть(self):
        """curl с адреса 127.0.0.5 → stream (как tg-relay) → 8443 → журнал с 127.0.0.5."""
        код = self.curl('-k', '--interface', '127.0.0.5',
                        '--resolve', 'weconomics.ai:9443:127.0.0.1',
                        '-o', '/dev/null', '-w', '%{http_code}',
                        'https://weconomics.ai:9443/429.html?probe-chain')
        self.assertEqual(код, '404')
        строки = self.log_lines('probe-chain')
        self.assertTrue(строки and строки[-1].startswith('127.0.0.5 '), строки)
        здоровье = self.curl('--interface', '127.0.0.5', '-o', '/dev/null',
                             '-w', '%{http_code}', 'http://127.0.0.1:9080/healthz')
        self.assertEqual(здоровье, '200')

    def test_6_без_файла_realip_nginx_жив_и_заголовку_не_верит(self):
        subprocess.run(['docker', 'exec', self.name, 'rm', '-f',
                        '/etc/nginx/conf.d/web_relay_realip.conf'], check=True)
        self.addCleanup(subprocess.run, ['docker', 'exec', self.name, 'sh', '-c',
                                         'echo "set_real_ip_from 127.0.0.1;" > '
                                         '/etc/nginx/conf.d/web_relay_realip.conf && nginx -s reload'],
                        capture_output=True)
        проверка = self.nginx_t()
        self.assertEqual(проверка.returncode, 0, проверка.stderr)
        subprocess.run(['docker', 'exec', self.name, 'nginx', '-s', 'reload'],
                       check=True, capture_output=True)
        time.sleep(1)
        self.curl('-k', '--haproxy-protocol', '--haproxy-clientip', '198.51.100.66',
                  '--resolve', 'weconomics.ai:8443:127.0.0.1', '-o', '/dev/null',
                  'https://weconomics.ai:8443/429.html?probe-untrusted')
        строки = self.log_lines('probe-untrusted')
        self.assertTrue(строки and строки[-1].startswith('127.0.0.1 '), строки)
