#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
import os, sys, cgi, pickle
from pathlib import Path
from urllib.parse import quote
sys.stdout.reconfigure(encoding='utf-8')
# 定義
CONF = "../Apache24/conf/httpd-mochikara.conf"
PKLF = "../tmp/mochi2cache.pkl"
HEADER = "../htdocs/mochi2_HEADER.shtml"
FOOTER = "../htdocs/mochi2_README.shtml"
EXTS = {    ".mp4", ".mp4v", ".mpeg4", ".mkv", ".mpeg", ".mpg",
            ".mpe", ".m1v", ".m2v", ".avi", ".wmv", ".flv", ".mp3" }

print("Content-Type: text/html; charset=UTF-8\r\n")
form = cgi.FieldStorage()
with open(CONF, "r", encoding="utf-8") as f:
    docroot = f.readline().split('"')[1]

# ヘッダ出力
title_txt = "【スペース区切りand検索】"
print( f'''\
<html><head>
  <title>{title_txt}</title>
  <link rel="stylesheet" href="/htdocs/mochi2_fancy.css" type="text/css">
  <link rel="icon" href="/favicon.ico">
 </head><body>
''',flush=True)

# キャッシュ作成
cacheflg = ""
if not os.path.exists(PKLF) or not form.getvalue('q'):
    print('<div class="pre-gray">キャッシュ再作成 ....</div>',flush=True)
    cache = []
    for root, _, files in os.walk(docroot):
        for name in files:
            if os.path.splitext(name)[1].lower() in EXTS:
                cache.append(os.path.join(root, name).replace("\\", "/"))
    with open(PKLF, "wb") as f:
        pickle.dump(cache, f)
    cacheflg = "[キャッシュ再作成]"
else:
    with open(PKLF, "rb") as f:
        cache = pickle.load(f)

q = form.getvalue('q', "")
words = [w.lower() for w in q.split() if w]
results = [ p for p in cache
            if all(w in p.lower() for w in words) ]

with open(HEADER, "r", encoding="utf-8") as f:
    for line in f:
        if 'maxlength="64"' in line:
            print(line.replace('maxlength="64"',f'maxlength="64" value="{q}"'), end="")
        elif '<!--#include virtual="/cgi-bin/mochi2_bread.py" -->' in line:
            print(f'<span class="big">{title_txt}</span>{cacheflg} {len(results)}件 / 検索文字:{q} ')
        else:
            print(line, end="")
print("<hr>")

# 検索
results = sorted(results, key=lambda p: p.lower().endswith(".mp3"))
if len(results) > 200:
    print("　🔍 200件まで表示します")
print('<table id="indexlist">')
for i, path in enumerate(results[:200]):
    rowclass = "even" if i % 2 == 0 else "odd"
    if Path(path).suffix == ".mp3":
        icon = "/icons/sound2.gif"
    else:
        icon = "/icons/movie.gif"
    rel = "/" + os.path.relpath(path, docroot).replace("\\", "/")
    href = quote(rel, safe="/")

    print(
        f'<tr class="{rowclass}">'
        f'<td><img src="{icon}"></td>'
        f'<td><a href="{href}"> 📄 {rel}</a></td>'
        f'</tr>'
    )
print(f"</table>")

# フッタ表示
with open(FOOTER, "r", encoding="utf-8") as f:
    for line in f:
        print(line, end="")
print('</body></html>')