#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
# pip install requests
# pip install ytmusicapi
debug_idxs = set()    # 全部走行
#debug_idxs = {4}   # 特定走行モード

import os, sys, json, re, glob, requests, pickle, shutil
from urllib.parse import unquote
from pathlib import Path
from datetime import datetime
from rapidfuzz import process, fuzz
from ytmusicapi import YTMusic
sys.stdout.reconfigure(encoding='utf-8')
uri = os.environ.get("REQUEST_URI", "/").split("?", 1)[0]
os.chdir(Path(__file__).resolve().parent)
print("Content-Type: text/html; charset=UTF-8\r\n")

karapath = open("../Apache24/conf/httpd-mochikara.conf", encoding="utf-8")\
    .read().split('"')[1]
htmlfhead = karapath + "/プレイリスト/"
scrbased  = karapath + "/MV_スクロール歌詞/"

# 関数
def open_text_auto(path):           # 文字コード判定open
    for enc in ( "utf-8-sig","cp932","utf-16","utf-16-le","utf-16-be", ):
        try:
            f = open(path, encoding=enc)
            f.read(1)
            f.seek(0)
            return f
        except UnicodeDecodeError:
            try:
                f.close()
            except:
                pass
    raise ValueError(f"decode failed: {path}")

def read_ass_sinfo(assf):               # assのsonginfoを取得
    sinfo = {}
    in_sinfo = False
    with open_text_auto(assf) as f:
        for line in f:
            if line.startswith(";[Song Info]"):
                in_sinfo = True
                continue
            if in_sinfo and line.startswith(";["):
                break
            if in_sinfo and line.startswith(";"):
                text = line[1:].strip()
                if "=" in text:
                    key, value = text.split("=", 1)
                    sinfo[key] = value
    return sinfo

def get_imgurl(sinfo):                  # youtubeの画像urlを返す
    vidid = ""
    if sinfo.get('loopvid'):    vidid = sinfo['loopvid']
    elif sinfo.get('vidid'):    vidid = sinfo['vidid']
    elif sinfo.get('videoId'):  vidid = sinfo['videoId']
    if vidid:
        return "https://i.ytimg.com/vi/" + vidid + "/mqdefault.jpg"
    else:
        return "images/noimg.png"

def get_songcomment(fname):
    comment1 = f"[{Path(fname).suffix[1:]}]"
    comment2 = comment3 = ""
    assf = str(Path(fname).with_suffix(".ass"))
    txtf = str(Path(fname).with_suffix(".txt"))
    if os.path.exists(assf):
        comment1 += "[ass]"
        sinfo = read_ass_sinfo(assf)
        if sinfo.get('title'):
            comment1 += "[sinfo]"
            comment2 += f" title:{sinfo.get('title')}" 
        if sinfo.get('artist'): comment2 += f" artist:{sinfo.get('artist')}" 
        if sinfo.get('tieup'):  comment3 += f" tieup:{sinfo.get('tieup')}"
        if sinfo.get('year'):   comment3 += f" year:{sinfo.get('year')}"
    if not comment2 and not comment3:
        stem = Path(fname).stem  # 拡張子なし
        tieup = title = artist = ""
        m = re.match(r"\[(.*?)\]\s*(.*)", stem)
        if m:
            tieup = m.group(1).strip()
            stem = m.group(2).strip()
        if "／" in stem:
            title, artist = [x.strip() for x in stem.split("／", 1)]
        else:
            title = stem.strip()
        if title:   comment2 += f' title:{title}' 
        if artist:  comment2 += f' artist:{artist}' 
        if tieup:   comment3 += f' tieup:{tieup}' 
    if os.path.exists(txtf):
        comment1 += "[txt]"
    return [comment1,comment2,comment3]

def emoji(fname):                   # 絵文字分類表示
    emoji = '🎞️'
    if 'mv.' in fname.lower():
        emoji = '🎬'
    elif 'youtube.' in fname.lower():
        emoji = '📺'
    elif 'first take' in fname.lower():
        emoji = '📹'
    elif '.mp3' in fname.lower():
        emoji = '🎵'
    return emoji

def get_utanet_views(utaid):
    url = f"https://www.uta-net.com/song/{utaid}/"
    try:
        page = requests.get(url).text
        m = re.search(r'表示回数：\s*([\d,]+)回', page)
        if not m:
            return 0
        return int(m.group(1).replace(",", ""))
    except:
        return 0

def collect_ids(uvid,ass_dir = scrbased):     # ids集計 uvid = utaid or vidid
    cache_file = Path(f"../tmp/mochi2cache_{uvid}.pkl")
    if ass_dir != scrbased:
        cache_file = Path(f"../tmp/mochi2cache_{uvid}_{Path(ass_dir).name}.pkl")
    if cache_file.exists():                 # キャッシュがあればそれを使う
        with open(cache_file, "rb") as f:
            return pickle.load(f)
    print(f'作成中... collect_ids:{uvid} ass_dir={ass_dir}')
    ids = {}
    if uvid == "utaid":
        id_re = re.compile(r'^;utaid=(\d+)')
    if uvid == "vidid":
        id_re = re.compile(r'^;vidid=(.+)')
    for ass_path in Path(ass_dir).rglob("*.ass"):
        with ass_path.open(encoding="utf-8") as f:
            for line in f:
                m = id_re.match(line.strip())
                if m:
                    foundid = m.group(1)
                    ckfpath = ass_path.with_suffix(".mp4").as_posix()
                    ckrpath = ckfpath.replace(karapath,"")
                    ids.setdefault(foundid, []).append(ckrpath)
    with open(cache_file, "wb") as f:               # キャッシュ保存
        pickle.dump(ids, f)
    return ids

def mk_plheader(plst):                  # ヘッダ作成
    out = Path(htmlfhead) / f"{plst['name']}.html"
    title = f'''\
<html><head><title>{plst['name']}のプレイリスト</title>
    <meta charset="UTF-8">
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="cache-control" content="no-cache" />
    <meta http-equiv="expires" content="0" />
    <link rel="icon" href="/favicon.ico">
</head><body>
<iframe name="mpc" style="display:none"></iframe>
'''

    header = Path("../htdocs/mochi2_HEADER.shtml").read_text(encoding="utf-8")
    # ヘッダ内容置き換え
    now = datetime.now().strftime("%Y/%m/%d %H")
    header = header.replace('音量:<!--#include virtual="/htdocs/mochivol.txt" -->', \
                            f'プレイリスト {now}時作成')
    header = header.replace('<!--#include virtual="/cgi-bin/mochi2_bread.py" -->', \
                            f'<span class=big>{plst["name"]}</span>')
    header = header.replace('/htdocs/','images/')
    comment =  f'''\
<a href="index.html"><img class="pl-sicon" src="{plst["icon"]}"></a>
<div class="pre-gray">{plst["comment1"]}\n{plst["comment2"]}<hr></div>
'''
    with open(out, 'w', encoding='utf-8') as f:
        f.write( title + header + comment)
        
def mk_plfooter(plst):                  # フッタ作成
    out = Path(htmlfhead) / f"{plst['name']}.html"
    footer = Path("../htdocs/mochi2_README.shtml").read_text(encoding="utf-8")
    with open(out, 'a', encoding='utf-8') as f:
        f.write(footer)
    
def html_index_tr(nocnt, icon, name, comment):  # 行情報作成
    if not icon:
        icon = "images/noimg.png"
    name_style = name
    if "/" in name:
        i = name.rfind("/")
        name_style = f'<div class="pl-smain">{emoji(name)} {name[:i+1]}</div>{name[i+1:]}'
    mvlink = 'class="mvlink"'
    if '.html' in name:
        mvlink = ''
    return f'''
<tr class="pl-tr">
  <td rowspan=2 class="pl-no">{nocnt}</td>
  <td rowspan=2 class="pl-icon-hover"><a {mvlink} href="{name}"><img class="pl-img" src="{icon}"></a></td>
  <td class="pl-main1-hover"><a {mvlink} href="{name}"><b>{name_style}</b></a></td>
</tr>
<tr class="pl-tr">
  <td class="pl-comment">{comment}</td>
</tr>
'''
def url_utanet(utaid):
    return f'https://www.uta-net.com/song/{utaid}/'

def url_youtube(vidid):
    return f'https://www.youtube.com/watch?v={vidid}'

def html_sinfo_tr(nocnt, ckfiles, views = 0):  # sinfo行情報作成
    # 最終行を取りましょう
    assf = str(Path(karapath + ckfiles[-1]).with_suffix(".ass"))
    sinfo = read_ass_sinfo(assf)
    icon = get_imgurl(sinfo)
    name_style  = f'{sinfo.get("title","")} ／ {sinfo.get("artist","")}'
    name_style += f'<div class="pl-smain">{sinfo.get("tieup","")} '
    utaid = sinfo.get("utaid")
    vidid = sinfo.get("vidid")
    name_style += f'表示回数:{views:,}回 '
    if utaid:
        name_style += f'[<a class="link-hover" href="{url_utanet(utaid)}">🎼uta-net</a>] '
    if vidid:
        name_style += f'[<a class="link-hover" href="{url_youtube(vidid)}">▶️youtube</a>] '
    name_style += f'</div>'
    comment_style = '<table class="pl-table">'
    r = 1
    for ckfile in ckfiles:
        comment_style += f'<tr class="pl-tr"><td class="pl-main{r}-hover">'
        comment_style += f'<a href="{ckfile}">{emoji(ckfile)} <span class="mid">{ckfile}</span></a>'
        comment_style += f'</td></tr>'
        r = 2 if r == 1 else 1
    comment_style += '</table>'
    return f'''
<tr class="pl-tr">
  <td rowspan=2 class="pl-no">{nocnt}</td>
  <td rowspan=2 class="pl-icon-hover"><a href="{ckfiles[-1]}">
    <img class="pl-img" src="{icon}"></a></td>
  <td class="pl-main0">{name_style}</td>
</tr>
<tr class="pl-tr">
  <td class="pl-main0">{comment_style}</td>
</tr>
'''

# mk_pl 関数
def mk_pl_index(plst):                  # プレイリストのプレイリスト
    # htdocsからのコピーをやる
    shutil.copy("../htdocs/mochi2_header.css", htmlfhead + "images/" )
    shutil.copy("../htdocs/mochi2_script.js" , htmlfhead + "images/" )

    mk_plheader(plst)
    nocnt = 1
    html = ['<table class="pl-table">']
    for plst2 in plists[1:]:
        comment = f"{plst2['comment1']}<br />{plst2['comment2']}"
        html.append(
            html_index_tr(nocnt, plst2['icon'], plst2['name'] + ".html", comment)
        )
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html", 'a', encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)

def mk_pl_newrecords(plst):                 # 新譜
    def list_recent_mp4(base_dir, limit=100):   # 新譜(関数)
        base_path = Path(base_dir).resolve()
        files = []
        for p in base_path.rglob("*.mp4"):
            try:
                stat = p.stat()
                files.append((p, stat.st_mtime))
            except OSError:
                continue
        files.sort(key=lambda x: x[1], reverse=True)        # 更新日時で新しい順にソート
        result = []
        for p, mtime in files[:limit]:
            rel_path = p.relative_to(base_path)
            result.append({
                "path": "/" + str(rel_path).replace("\\","/"),
                "timestamp": mtime
            })
        return result
    recent_mp4i = list_recent_mp4(karapath, limit=100)
    mk_plheader(plst)
    nocnt = 1
    html = ['<table class="pl-table">']
    for mp4i in recent_mp4i:
        mp4f = karapath + "/" + mp4i['path']
        assf = str(Path(mp4f).with_suffix(".ass"))
        dt = datetime.fromtimestamp(mp4i["timestamp"])
        comment = "更新日時:" + dt.strftime("%Y-%m-%d %H:%M:%S")
        icon = "images/noimg.png"
        if os.path.exists(assf):
            sinfo = read_ass_sinfo(assf)
            icon = get_imgurl(sinfo)
            comment = "<br>".join(get_songcomment(mp4f))
            html.append(
                html_index_tr(nocnt,icon,mp4i['path'],comment)
            )
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html", 'a', encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)
    return

def mk_pl_all(plst):                        # ファイル一覧
    if plst['pltype'] == "allmp4":
        exts = ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.wmv", "*.flv", "*.webm", "*.m4v"]
    else:
        exts = ["*.mp3"]
    pkarapath = Path(karapath)
    mk_plheader(plst)
    with open(htmlfhead + plst['name'] + ".html", 'a', encoding='utf-8') as f:
        f.write('<div class="pre-allmp">')
        count = 0
        for ext in exts:
            for p in pkarapath.rglob(ext):
                if p.is_file():
                    rel_path = p.relative_to(pkarapath)
                    path_str = str(rel_path)
                    if any(kw in path_str for kw in plst['exclude_keywords']): continue
                    f.write(path_str + "\n")
                    count += 1
        f.write(f"\n--- total: {count} files ---\n")
        f.write("</div>\n")
    mk_plfooter(plst)

def mk_pl_mochilist(plst):                  # 過去回セットリスト
    kara_files = [
        str(p).replace("\\", "/")
        for p in Path(karapath).rglob("*")
        if p.is_file()
    ]
    mk_plheader(plst)
    files = []
    # ファイル収集＋日付抽出
    for fp in glob.glob(os.path.join(karapath, "**", "mochilist_????????.txt"), recursive=True):
        name = os.path.basename(fp)
        m = re.search(r"mochilist_(\d{8})\.txt", name)
        if m:
            date = m.group(1)
            files.append((date, fp))
    files.sort(reverse=True)
    nocnt = 1
    with open(htmlfhead + plst['name'] + ".html", 'a', encoding='utf-8') as fa:
        fa.write('<table class="pl-table">')
        for s, fp in files:
            date = f"{s[:4]}/{s[4:6]}/{s[6:8]}"
            with open_text_auto(fp) as f:
                for line in f:
                    img = None
                    emoji= ""
                    line = line.strip()
                    fname = karapath + line
                    if not line:
                        continue
                    if not os.path.exists(fname):
                        # ファイルがない場合探す
                        result = process.extractOne(
                            fname,
                            kara_files,
                            scorer=fuzz.ratio
                        )
                        if result:
                            fname, score, _ = result
                        line = fname.replace(karapath,'')
                        emoji = '[ℹ️ファイルパス修正]'
                    assf = str(Path(fname).with_suffix(".ass"))
                    comment = emoji + "<br>".join(get_songcomment(fname))
                    if os.path.exists(assf):
                        img = get_imgurl(read_ass_sinfo(assf))
                    no = f"<center>{nocnt}</center>{date}"
                    fa.write(html_index_tr(no,img,line,comment))
                    nocnt += 1
        fa.write('</table>')
    mk_plfooter(plst)

scr_utaids = collect_ids("utaid")
def mk_pl_utanet(plst):                     # uta-net アニメ
    page = requests.get(plst['url']).text
    pattern = re.compile(r'<a href="/song/(\d+)/">(.*?)</a>\s*/\s*(.*?)</td>')
    mk_plheader(plst)
    nocnt = 1
    html = ['<table class="pl-table">']
    for utaid, pgttl, pgart in pattern.findall(page):
        if int(utaid) < 300000:     # 古い曲除外
            continue
        ckfiles = scr_utaids.get(utaid)
        if not ckfiles:             # utaid見つからなければ除外
            continue
        html.append(
            html_sinfo_tr(nocnt,ckfiles)
        )
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html", 'a', encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)

def mk_pl_utanet(plst):                     # uta-net アニメ
    page = requests.get(plst['url']).text
    pattern = re.compile(
        r'<a href="/song/(\d+)/">(.*?)</a>\s*/\s*(.*?)</td>'
    )
    mk_plheader(plst)
    songs = []
    for utaid, pgttl, pgart in pattern.findall(page):
        if int(utaid) < 300000:     # 古い曲除外
            continue
        ckfiles = scr_utaids.get(utaid)
        if not ckfiles:             # utaid見つからなければ除外
            continue
        views = get_utanet_views(utaid)
        songs.append((views, ckfiles))
        print(utaid, pgttl, pgart, views)
    songs.sort(reverse=True, key=lambda x: x[0])    # 表示回数の多い順
    nocnt = 1
    html = ['<table class="pl-table">']
    for views, ckfiles in songs:
        html.append(html_sinfo_tr(nocnt, ckfiles, views))
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html",'a',encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)

def mk_pl_dirlist(plst):                    # ディレクトリ配下のプレイリスト
    based = Path(scrbased) / plst['folder']
    mk_plheader(plst)
    songs = []
    done_utaids = set()     # 処理済みutaid
    for mp4f in based.glob("*.mp4"):
        assf = str(Path(mp4f).with_suffix(".ass"))
        sinfo = read_ass_sinfo(assf)
        utaid = sinfo.get('utaid')
        if utaid and utaid in done_utaids:  # 同じutaidはスキップ
            continue
        if utaid:
            done_utaids.add(utaid)
            ckfiles = scr_utaids.get(utaid)
            views = get_utanet_views(utaid)
        else:
            ckfiles = [ str(mp4f).replace('\\', '/').replace(karapath, '') ]
            views = 0
        songs.append((views, ckfiles))
        print(utaid, sinfo.get('title'), sinfo.get('artist'), views)
    songs.sort(reverse=True, key=lambda x: x[0])    # 表示回数順
    nocnt = 1
    html = ['<table class="pl-table">']
    for views, ckfiles in songs:
        html.append(html_sinfo_tr(nocnt, ckfiles, views))
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html",
              'a', encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)

def mk_pl_ytplist(plst):                    # youtubeプレイリスト（フォルダあり/なし両対応）
    based = scrbased
    if plst.get('folder'):
        based = scrbased + plst['folder']
    scr_vidids_based = collect_ids("vidid",based)
    ytmusic = YTMusic()
    mk_plheader(plst)
    playlist = ytmusic.get_playlist(plst['plid'],limit=200)
    songs = []
    done_vidids = set()     # 処理済みvidid
    for track in playlist['tracks'][:200]:
        vidid = track['videoId']
        if vidid and vidid in done_vidids:  # 同じvididはスキップ
            continue
        ckfiles = scr_vidids_based.get(vidid)
        if not ckfiles:
            continue
        mp4f = karapath + ckfiles[0]
        assf = str(Path(mp4f).with_suffix(".ass"))
        sinfo = read_ass_sinfo(assf)
        utaid = sinfo.get('utaid')
        views = get_utanet_views(utaid)
        done_vidids.add(vidid)
        # フォルダ指定がある場合にはそのフォルダ内だけを対象(utaidの再検索なし)
        if plst.get('folder'):
            songs.append((views, ckfiles))
        # フォルダ指定がない場合にはutaidの再検索あり
        else:
            ckfiles_utaid = scr_utaids.get(utaid)
            songs.append((views, ckfiles_utaid))
        print(vidid, utaid, sinfo.get('title'), sinfo.get('artist'), views)
#    songs.sort(reverse=True, key=lambda x: x[0])    # 表示回数順
    nocnt = 1
    html = ['<table class="pl-table">']
    for views, ckfiles in songs:
        html.append(html_sinfo_tr(nocnt, ckfiles, views))
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html",
              'a', encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)



# メインループ
with open("mochi2_makepi.json", "r", encoding="utf-8") as f:
    plists = json.load(f)
for i, plst in enumerate(plists):
    if debug_idxs and i not in debug_idxs: continue
    print(f"プレイリスト:{plst['name']} pltype={plst['pltype']}")
    if plst['pltype'] == "index":
        mk_pl_index(plst)
    elif plst['pltype'] == "newrecords":
        mk_pl_newrecords(plst)
    elif plst['pltype'] == "uta-net":
        mk_pl_utanet(plst)
    elif plst['pltype'] == "mochilist":
        mk_pl_mochilist(plst)
    elif plst['pltype'] == "ytplist":
        mk_pl_ytplist(plst)
    elif plst['pltype'] == "dirlist":
        mk_pl_dirlist(plst)
    elif plst['pltype'] == "allmp4" or plst['pltype'] == "allmp3":
        mk_pl_all(plst)