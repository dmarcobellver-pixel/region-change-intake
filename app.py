#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改区服务 · 客户资料收集表（干净版）
- 客户侧：填邮箱、当前地区、目标地区、用途、联系方式、订单号、备注，提交后生成查询编号
- 店主侧：/admin 首次设置管理员口令后登录，看全部提交、标已处理、删除
- 绝不收集密码：页面明确提示密码不要填，登录在谷歌官方页面由客户本人输入
- 纯 Python 标准库 + SQLite，无第三方依赖
"""
import hashlib
import hmac
import html
import os
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_PATH = os.environ.get("INTAKE_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "intake.db"))
PORT = int(os.environ.get("PORT", "8080"))

COUNTRIES = ["中国", "美国", "日本", "中国香港", "中国台湾", "韩国", "新加坡", "英国", "加拿大",
             "澳大利亚", "德国", "法国", "印度", "巴西", "墨西哥", "泰国", "越南", "马来西亚",
             "印度尼西亚", "菲律宾", "俄罗斯", "土耳其", "阿根廷", "荷兰", "西班牙", "意大利", "其他"]
PURPOSES = ["工作需要", "学习需要", "生活需要", "其他"]

# ---------------- db ----------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ref TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        cur_region TEXT NOT NULL,
        target_region TEXT NOT NULL,
        purpose TEXT NOT NULL DEFAULT '',
        contact TEXT NOT NULL DEFAULT '',
        order_no TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT '待处理',
        created_at INTEGER NOT NULL
    );
    """)
    conn.commit()
    conn.close()


def meta_get(k):
    conn = db()
    row = conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    conn.close()
    return row["v"] if row else None


def meta_set(k, v):
    conn = db()
    conn.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
    conn.commit()
    conn.close()


# ---------------- auth ----------------

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()
    return salt + "$" + h


def check_pw(pw, stored):
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()
    return hmac.compare_digest(calc, h)


def server_secret():
    s = meta_get("secret")
    if not s:
        s = secrets.token_hex(32)
        meta_set("secret", s)
    return s


def make_session():
    ts = str(int(time.time()))
    sig = hmac.new(server_secret().encode(), ts.encode(), hashlib.sha256).hexdigest()
    return ts + "." + sig


def valid_session(val):
    if not val or "." not in val:
        return False
    ts, sig = val.rsplit(".", 1)
    expect = hmac.new(server_secret().encode(), ts.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return False
    return int(time.time()) - int(ts) < 7 * 24 * 3600


# ---------------- helpers ----------------

SUBMIT_LOG = {}


def rate_ok(ip):
    now = time.time()
    log = [t for t in SUBMIT_LOG.get(ip, []) if now - t < 3600]
    if len(log) >= 20:
        return False
    log.append(now)
    SUBMIT_LOG[ip] = log
    return True


def esc(s):
    return html.escape(str(s or ""), quote=True)


def options(items, current=""):
    out = []
    for it in items:
        sel = " selected" if it == current else ""
        out.append(f'<option value="{esc(it)}"{sel}>{esc(it)}</option>')
    return "".join(out)


CSS = """
<style>
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#FAF8FF;color:#2E2A3F}
.wrap{max-width:560px;margin:0 auto;padding:22px 16px 40px}
.card{background:#fff;border:1px solid #E7E1F7;border-radius:16px;padding:22px 18px;box-shadow:0 6px 24px rgba(139,123,216,.08)}
h1{font-size:21px;margin:0 0 6px;color:#4B3F8F}
.sub{font-size:13px;color:#7A7396;margin:0 0 16px;line-height:1.6}
label{display:block;font-size:13px;font-weight:600;margin:14px 0 6px;color:#4B3F8F}
input,select,textarea{width:100%;padding:11px 12px;border:1px solid #D9D2F0;border-radius:10px;font-size:15px;background:#FDFCFF;color:#2E2A3F}
textarea{resize:vertical;min-height:64px}
.btn{display:block;width:100%;margin-top:20px;padding:13px;border:0;border-radius:12px;background:#8B7BD8;color:#fff;font-size:16px;font-weight:700;cursor:pointer}
.btn:active{background:#7A68C9}
.warn{background:#FFF7E8;border:1px solid #F2D492;color:#7A5A12;border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.6;margin-top:14px}
.ok{background:#EEFBF1;border:1px solid #A9E5BC;color:#1C6B38}
.small{font-size:12px;color:#9A94B5;margin-top:10px;line-height:1.6}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid #EEE9FA;padding:8px 6px;text-align:left;vertical-align:top}
th{color:#4B3F8F;background:#F5F2FF}
.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;background:#EFE9FF;color:#6A5ACD}
.tag.done{background:#E5F6EC;color:#1C6B38}
.mini{padding:5px 10px;border-radius:8px;border:1px solid #D9D2F0;background:#fff;cursor:pointer;font-size:12px}
.rowbtns{display:flex;gap:6px}
</style>
"""

# ---------------- pages ----------------

def form_page(err=""):
    err_html = f'<div class="warn" style="background:#FDECEC;border-color:#F3B3B3;color:#8F2B2B">{esc(err)}</div>' if err else ""
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>谷歌改区服务 · 资料填写</title>{CSS}</head><body><div class="wrap">
<div class="card">
<h1>谷歌改区服务 · 资料填写</h1>
<p class="sub">填邮箱和想改到的地区就行。不要填密码。</p>
{err_html}
<form method="post" action="/submit">
<label>要改区的谷歌邮箱 *</label>
<input name="email" type="email" required placeholder="例如 abc@gmail.com" autocomplete="email">
<label>更改地区（想改到哪个地区）*</label>
<select name="target_region" required><option value="">请选择</option>{options(COUNTRIES)}</select>
<button class="btn" type="submit">提交资料</button>
</form>
</div></div></body></html>"""


def thanks_page(ref):
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>提交成功</title>{CSS}</head><body><div class="wrap">
<div class="card">
<h1>✅ 提交成功</h1>
<p class="sub">店主已经收到你的资料了。</p>
</div></div></body></html>"""


def admin_login_page(err="", setup=False):
    title = "店主后台 · 设置管理员口令" if setup else "店主后台 · 登录"
    btn = "设置并进入" if setup else "登录"
    action = "/admin/setup" if setup else "/admin/login"
    err_html = f'<div class="warn" style="background:#FDECEC;border-color:#F3B3B3;color:#8F2B2B">{esc(err)}</div>' if err else ""
    note = "第一次使用，先设一个管理员口令（至少 6 位）。设好后只有你能看客户资料，设之前不要把 /admin 发给任何人。" if setup else "输入管理员口令查看客户提交。"
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>{CSS}</head><body><div class="wrap">
<div class="card">
<h1>{title}</h1>
<p class="sub">{note}</p>
{err_html}
<form method="post" action="{action}">
<label>管理员口令</label>
<input name="password" type="password" required autocomplete="current-password">
<button class="btn" type="submit">{btn}</button>
</form>
</div></div></body></html>"""


def admin_page(rows):
    trs = []
    for r in rows:
        done = r["status"] == "已处理"
        tag = '<span class="tag done">已处理</span>' if done else '<span class="tag">待处理</span>'
        t = time.strftime("%m-%d %H:%M", time.localtime(r["created_at"]))
        nxt = "待处理" if done else "已处理"
        trs.append(f"""<tr>
<td>{t}</td>
<td>{esc(r['email'])}</td>
<td><b>{esc(r['target_region'])}</b></td>
<td>{tag}</td>
<td><div class="rowbtns">
<form method="post" action="/admin/action"><input type="hidden" name="id" value="{r['id']}"><input type="hidden" name="op" value="toggle"><button class="mini" type="submit">标{nxt}</button></form>
<form method="post" action="/admin/action" onsubmit="return confirm('删除这条？')"><input type="hidden" name="id" value="{r['id']}"><input type="hidden" name="op" value="delete"><button class="mini" type="submit">删</button></form>
</div></td></tr>""")
    body = "".join(trs) if trs else '<tr><td colspan="5" class="small">还没有客户提交。</td></tr>'
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>店主后台 · 客户资料</title>{CSS}</head><body><div class="wrap" style="max-width:920px">
<div class="card">
<h1>客户资料（共 {len(rows)} 条）</h1>
<p class="sub">客户填表页就是本站首页，把本站链接发给客户即可。</p>
<div style="overflow-x:auto"><table>
<tr><th>时间</th><th>邮箱</th><th>更改地区</th><th>状态</th><th>操作</th></tr>
{body}
</table></div>
</div></div></body></html>"""


# ---------------- handler ----------------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_html(self, code, body, extra=None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def read_form(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n).decode("utf-8", "replace")
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def cookie(self, name):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith(name + "="):
                return part[len(name) + 1:]
        return ""

    def authed(self):
        return valid_session(self.cookie("sess"))

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/healthz":
            self.send_html(200, '{"ok": true}')
        elif p == "/":
            self.send_html(200, form_page())
        elif p == "/admin":
            if meta_get("admin_pw") is None:
                self.send_html(200, admin_login_page(setup=True))
            elif not self.authed():
                self.send_html(200, admin_login_page())
            else:
                conn = db()
                rows = conn.execute("SELECT * FROM submissions ORDER BY id DESC").fetchall()
                conn.close()
                self.send_html(200, admin_page(rows))
        else:
            self.send_html(404, "not found")

    def do_POST(self):
        p = urlparse(self.path).path
        f = self.read_form()
        if p == "/submit":
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0]
            if not rate_ok(ip):
                self.send_html(429, form_page("提交太频繁，请过一会儿再试"))
                return
            email = (f.get("email") or "").strip()
            tgt = (f.get("target_region") or "").strip()
            if not email or "@" not in email or not tgt:
                self.send_html(400, form_page("邮箱和更改地区都要填好再提交"))
                return
            ref = "GX" + str(int(time.time()))[-6:] + secrets.token_hex(1).upper()
            conn = db()
            conn.execute(
                "INSERT INTO submissions(ref,email,cur_region,target_region,purpose,contact,order_no,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (ref, email[:120], "", tgt, "", "", "", "", int(time.time())))
            conn.commit()
            conn.close()
            self.send_html(200, thanks_page(ref))
        elif p == "/admin/setup":
            if meta_get("admin_pw") is not None:
                self.send_html(403, admin_login_page("管理员口令已设置，请直接登录"))
                return
            pw = f.get("password") or ""
            if len(pw) < 6:
                self.send_html(400, admin_login_page("口令至少 6 位", setup=True))
                return
            meta_set("admin_pw", hash_pw(pw))
            self.send_response(303)
            self.send_header("Location", "/admin")
            self.send_header("Set-Cookie", f"sess={make_session()}; Path=/; HttpOnly; Max-Age=604800")
            self.end_headers()
        elif p == "/admin/login":
            stored = meta_get("admin_pw")
            if stored and check_pw(f.get("password") or "", stored):
                self.send_response(303)
                self.send_header("Location", "/admin")
                self.send_header("Set-Cookie", f"sess={make_session()}; Path=/; HttpOnly; Max-Age=604800")
                self.end_headers()
            else:
                self.send_html(403, admin_login_page("口令不对"))
        elif p == "/admin/action":
            if not self.authed():
                self.send_html(403, admin_login_page("先登录"))
                return
            sid = f.get("id") or ""
            op = f.get("op") or ""
            conn = db()
            if op == "delete" and sid.isdigit():
                conn.execute("DELETE FROM submissions WHERE id=?", (int(sid),))
            elif op == "toggle" and sid.isdigit():
                row = conn.execute("SELECT status FROM submissions WHERE id=?", (int(sid),)).fetchone()
                if row:
                    nxt = "待处理" if row["status"] == "已处理" else "已处理"
                    conn.execute("UPDATE submissions SET status=? WHERE id=?", (nxt, int(sid)))
            conn.commit()
            conn.close()
            self.send_response(303)
            self.send_header("Location", "/admin")
            self.end_headers()
        else:
            self.send_html(404, "not found")


if __name__ == "__main__":
    init_db()
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
