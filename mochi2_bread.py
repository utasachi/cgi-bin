#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
import os, sys
from urllib.parse import unquote
sys.stdout.reconfigure(encoding='utf-8')
uri = os.environ.get("REQUEST_URI", "/").split("?", 1)[0]
print("Content-Type: text/html; charset=UTF-8\r\n")
if uri.startswith("/htdocs/"):
    print("<span class=mid>📖 もちからWeb^2 マニュアル</span>")
    exit()
parts = uri.strip("/").split("/")
path = "/"
print('<a href="/">Home</a>', end='')
for part in parts:
    if not part:
        continue
    path += part + "/"
    decoded = unquote(part)
    print(' <span>&gt;</span> ', end='')
    if path.rstrip("/") == uri.rstrip("/"):
        print(f'<span class="current">{decoded}</span>', end='')
    else:
        print(f'<a href="{path}">{decoded}</a>', end='')