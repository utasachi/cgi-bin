#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
import os, sys, cgi, subprocess
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
print("Content-Type: text/html; charset=UTF-8\r\n")
uri = os.environ.get("REQUEST_URI", "/").split("?", 1)[0]
form = cgi.FieldStorage()
k = form.getvalue('k')
print( f'''\
<html><head>
    <title>キー送信</title>
    <meta http-equiv=refresh content=0;URL=/?menu=main>
</head><body>
<div class="big">　🔄 処理中......</div>
<div class="normal">　　uwsc_vk にキーイベント{k}を送信しました</div>
</body></html>
''',flush=True)
p = Path("../htdocs/mochivol.txt")
if k == 'up':
    p.write_text(str(min(int(p.read_text()) + 5, 100)))
if k == 'down':
    p.write_text(str(max(int(p.read_text()) - 5, 0)))

subprocess.run(["../bin/uwsc.exe", "../bin/uwsc_vk.uws", k])
