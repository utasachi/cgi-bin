#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
import os, sys
from urllib.parse import unquote
sys.stdout.reconfigure(encoding='utf-8')
uri = os.environ.get("REQUEST_URI", "/").split("?", 1)[0]
print("Content-Type: text/html; charset=UTF-8\r\n")
if uri.startswith("/htdocs/"):
    exit()
print('<div class="pre-gray">', end="")
with open("../htdocs/mochi2topic.txt", "r", encoding="utf-8") as f:
    print(f.read(), end="")
print('\n【登録履歴】')
with open("../htdocs/mochilist.txt", "r", encoding="utf-8") as f:
    print(f.read(), end="")
print('</div>')
