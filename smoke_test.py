#!/usr/bin/env python3
"""Quick local smoke test for CardVault Pro."""
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PORT = int(os.getenv('TEST_PORT', '8097'))
ROOT = os.path.dirname(__file__)
BASE = f'http://localhost:{PORT}'
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ''

def req(path, method='GET', data=None):
    global csrf
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if method not in ('GET', 'HEAD') and csrf:
        headers['X-CSRF-Token'] = csrf
    r = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with opener.open(r, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))

def main():
    global csrf
    env = os.environ.copy()
    env.update({'PORT': str(PORT), 'HOST': '127.0.0.1', 'CARDVAULT_DB': os.path.join(ROOT, 'data', 'smoke.sqlite3')})
    p = subprocess.Popen([sys.executable, 'server.py'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if req('/api/health').get('ok'):
                    break
            except Exception:
                time.sleep(.25)
        else:
            raise RuntimeError('Server did not start')
        token = req('/api/csrf')
        csrf = token['csrf_token']
        assert req('/api/products')['products']
        assert req('/api/auth/login','POST',{'email':'admin@cardvault.local','password':'CardVaultAdmin2026!'})['user']['role'] == 'admin'
        assert req('/api/cart/items','POST',{'product_id':'aurora','qty':1})['cart']['count'] == 1
        order = req('/api/orders/checkout','POST',{'shipping':{'name':'Smoke','email':'smoke@example.com','phone':'+100','address':'Street 1'},'payment_method':'manual'})['order']
        assert order['order_no'].startswith('CV-')
        assert req('/api/admin/dashboard')['dashboard']['orders'] >= 1
        print('CardVault Pro smoke test: OK')
    finally:
        p.terminate()
        try:
            p.wait(timeout=4)
        except subprocess.TimeoutExpired:
            p.kill()

if __name__ == '__main__':
    main()
