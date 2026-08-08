#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
# pip install requests
# pip install ytmusicapi
import os, sys, json, re, glob, requests, pickle, shutil, subprocess
from urllib.parse import quote
from pathlib import Path
from datetime import datetime
from rapidfuzz import process, fuzz
from ytmusicapi import YTMusic
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(Path(__file__).resolve().parent)
print("Content-Type: text/html; charset=UTF-8\r\n")

if len(sys.argv) == 1:
    debug_idxs = set()                  # 引数なし → 全部走行
else:
    debug_idxs = {int(x) for x in sys.argv[1:]}   # 指定された番号だけ
debug_idxs = {0,1,2,3,6}  # 特定走行モード

NOIMG = "images/noimg.png"
karapath = open("../Apache24/conf/httpd-mochikara.conf", encoding="utf-8")\
    .read().split('"')[1]
htmlfhead = karapath + "/プレイリスト/"
scrbased  = karapath + "/MV_スクロール歌詞/"
thumbbased = htmlfhead + 'thumbimgs/'

# 関数
def make_thumbimg(mp4f, thumbimg, sec = "30"):  
    thumbimg = Path(thumbimg)
    thumbimg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "../bin/ffmpeg", "-y",  # 上書き
        "-ss", sec,             # 30秒位置
        "-i", str(mp4f),
        "-frames:v", "1",       # 1フレームだけ
        "-q:v", "2",            # jpg品質
        str(thumbimg),
    ]
    subprocess.run( cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

def open_text_auto(path):
    for enc in ( "utf-8-sig", "cp932", "utf-16", "utf-16-le", "utf-16-be", ):
        try:
            with open(path, encoding=enc) as f:
                f.read()
            return open(path, encoding=enc)
        except UnicodeDecodeError:
            pass
    raise ValueError(f"decode failed: {path}")

def read_ass_sinfo(assf):               # assのsonginfoを取得
    if not os.path.exists(assf):
        return None
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

def get_thumbimgf(mp4f):
    mp4i = mp4f.replace("\\", "/").replace(karapath + "/","")
    return thumbbased + mp4i.replace("/", "_").rsplit(".", 1)[0] + ".jpg"

def get_imgurl(sinfo, mp4f = None):           # youtubeの画像urlを返す
    vidid = ""
    if sinfo and sinfo.get('loopvid'):    vidid = sinfo['loopvid']
    elif sinfo and sinfo.get('vidid'):    vidid = sinfo['vidid']
    elif sinfo and sinfo.get('videoId'):  vidid = sinfo['videoId']
    if vidid:
        return "https://i.ytimg.com/vi/" + vidid + "/mqdefault.jpg"
    if os.path.exists(get_thumbimgf(mp4f)):
        return get_thumbimgf(mp4f).replace(htmlfhead,"")
    return NOIMG

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
    now = datetime.now().strftime("%Y/%m/%d")
    header = header.replace('🔈音量:<!--#include virtual="/htdocs/mochivol.txt" -->', \
                            f'playlist {now}作成')
    header = header.replace('<!--#include virtual="/cgi-bin/mochi2_bread.py" -->', \
                            f'<span class=big>{plst["name"]}</span>')
    header = header.replace('/htdocs/','images/')
    comment =  f'''\
<a href="index.html"><img class="pl-sicon" src="{plst["icon"]}"></a>
<div class="pre-gray">{plst["comment1"]}\n{plst["comment2"]}</div><hr>
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
        icon = NOIMG
    name_style = f'<span class="link-hover-b">{name}</span>'
    if "/" in name:
        i = name.rfind("/")
        name_style  = f'<span class="pl-smain">{emoji(name)} {name[:i+1]}</span><br>'
        name_style += f'<span class="link-hover-b">{name[i+1:]}</span>'
    return f'''
<tr class="pl-tr">
  <td rowspan=2 class="pl-no">{nocnt}</td>
  <td rowspan=2 class="pl-icon-hover"><a href="{quote(name, safe="/")}">
    <img class="pl-img" src="{icon}"></a></td>
  <td class="pl-main1"><a href="{quote(name, safe="/")}">
    <b>{name_style}</b></a></td>
</tr>
<tr class="pl-tr">
  <td class="pl-comment">{comment}</td>
</tr>
'''
def url_utanet(utaid):
    return f'https://www.uta-net.com/song/{utaid}/'

def url_youtube(vidid):
    return f'https://www.youtube.com/watch?v={vidid}'

def html_sinfo_tr(nocnt, ckfiles, views = 0, plorder = -1):  # sinfo行情報作成
    # 指定がなければ最終行、指定することもできる
    if plorder is None: plorder = -1
    mp4f = karapath + ckfiles[plorder]
    assf = str(Path(mp4f).with_suffix(".ass"))
    sinfo = read_ass_sinfo(assf)
    name_style = ckfiles[plorder]
    if sinfo:
        img = get_imgurl(sinfo,ckfiles[plorder])
        name_style  = f'{sinfo.get("title","")} ／ {sinfo.get("artist","")}<br>'
        name_style += f'{sinfo.get("tieup","")} '
        utaid = sinfo.get("utaid")
        vidid = sinfo.get("vidid")
        name_style += f'表示回数:{views:,}回 '
        if utaid:
            name_style += f'[<a class="link-hover" href="{url_utanet(utaid)}">🎼uta-net</a>] '
        if vidid:
            name_style += f'[<a class="link-hover" href="{url_youtube(vidid)}">▶️youtube</a>] '
    comment_style = '<table class="pl-table">'
    r = 1
    for ckfile in ckfiles:
        if '/' in ckfile:
            ckfile1, ckfile2 = ckfile.rsplit('/', 1)
        else:
            ckfile1 = "(フォルダなし)"
            ckfile2 = ckfile
        comment_style += f'''\
<tr class="pl-tr"><td class="pl-main{r}">
<a href="{quote(ckfile, safe="/")}"><span class="normal-blue">{emoji(ckfile)} {ckfile1}</span><br>
<span class="link-hover-b">{ckfile2}</span>
</a></td></tr>
'''
        r = 2 if r == 1 else 1
    comment_style += '</table>'
    return f'''
<tr class="pl-tr">
  <td rowspan=2 class="pl-no">{nocnt}</td>
  <td rowspan=2 class="pl-icon-hover"><a href="{quote(ckfiles[-1], safe="/")}">
    <img class="pl-img" src="{img}"></a></td>
  <td class="pl-main0">{comment_style}</td>
</tr>
<tr class="pl-tr">
  <td class="pl-comment">{name_style}</td>
</tr>
'''

# mk_pl 関数
def mk_pl_index(plst):                  # プレイリストのプレイリスト
    # htdocsからのコピーをやる
    shutil.copy("../htdocs/mochi2_header.css", htmlfhead + "images/" )
    shutil.copy("../htdocs/mochi2_fancy2.css", htmlfhead + "images/" )
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
        mp4f = karapath + mp4i['path']
        assf = str(Path(mp4f).with_suffix(".ass"))
        dt = datetime.fromtimestamp(mp4i["timestamp"])
        comment = "更新日時:" + dt.strftime("%Y-%m-%d %H:%M:%S")
        sinfo = read_ass_sinfo(assf)
        img = get_imgurl(sinfo,mp4f)
        comment += "<br>".join(get_songcomment(mp4f))
        html.append(html_index_tr(nocnt,img,mp4i['path'],comment))
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
            date = f"{s[:4]}<br>{s[4:6]}/{s[6:8]}"
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
                    sinfo = read_ass_sinfo(assf)
                    img = get_imgurl(sinfo,fname)
                    no = f"<center>{nocnt}</center>{date}"
                    fa.write(html_index_tr(no,img,line,comment))
                    nocnt += 1
        fa.write('</table>')
    mk_plfooter(plst)

scr_utaids = collect_ids("utaid")
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
        html.append(html_sinfo_tr(nocnt, ckfiles, views, plst.get('plorder')))
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
        html.append(html_sinfo_tr(nocnt, ckfiles, views, plst.get('plorder')))
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
    if plst.get("sort") == "reverse":
        songs.reverse()
    elif plst.get("sort") == "views":
        songs.sort(reverse=True, key=lambda x: x[0])    # 表示回数順
    nocnt = 1
    html = ['<table class="pl-table">']
    for views, ckfiles in songs:
        html.append(html_sinfo_tr(nocnt, ckfiles, views, plst.get('plorder')))
        nocnt += 1
    html.append("</table>")
    with open(htmlfhead + plst['name'] + ".html",
              'a', encoding='utf-8') as f:
        f.write("".join(html))
    mk_plfooter(plst)

def mk_thumbimgs(plst):  # vididがない動画にthumb_imgs付与、mk_pl_index（_no = 0）の時に実行
    for thumbdir in plst['thumbdirs']:
        based = karapath + '/' + thumbdir
        for mp4p in Path(based).rglob("*.mp4"):
            mp4f = str(mp4p).replace("\\", "/")
            if any(keyword in mp4f
                   for keyword in plst['exclude_keywords']):
                continue
            assf = mp4f.rsplit(".", 1)[0] + ".ass"
            sinfo = read_ass_sinfo(assf)
            if get_imgurl(sinfo, mp4f) != NOIMG:
                continue
            print(f"サムネイル作成...{get_thumbimgf(mp4f)}")
            make_thumbimg(mp4f, get_thumbimgf(mp4f))
    return

def mk_pl_hddfolder(plst):                      # 旧 初めにお読みください
    mk_plheader(plst)
    nocnt = 1
    html = ['<h3>■フォルダ構成</h3>',' 📁 リンククリックで該当フォルダに遷移します','<table class="pl-table">\n']
    for name, link, newmark, level, desc in plst["folderdesc"]:
        prefix = "-" * level                   # 階層表示
        if link:                                # 名前部分
            e="📁"
            if ".html" in name or ".mp4" in name: e = "📄"
            left = f'{prefix}<a class="link-hover-b" href="{link}">{e}{name}</a>'
        else:
            left = prefix + name
        if newmark:                              # NEW表示
            left += f' <font color="#ff2222">{newmark}</font>'
        cls = "pl-tr-line1" if nocnt % 2 else "pl-tr-line2"
        if level < 2:
            cls = "pl-tr-line0"
        html.append(
            f'<tr class="{cls}">'
            f'<td>{nocnt}</td>'
            f'<td>{left}</td>'
            f'<td>{desc}</td>'
            "</tr>\n"
        )
        nocnt += 1
    html.append("</table>\n")
    with open(htmlfhead + plst['name'] + ".html", 'a', encoding='utf-8') as f:
        f.write("".join(html))
        with open(htmlfhead +"【うたさちHDD】特徴.html", encoding='utf-8') as src:
            f.write(src.read())
    mk_plfooter(plst)

# メインループ
with open("mochi2_makepl.json", "r", encoding="utf-8") as f:
    plists = json.load(f)
for i, plst in enumerate(plists):
    if debug_idxs and i not in debug_idxs: continue
    print(f"プレイリスト:{plst['name']} pltype={plst['pltype']}")
    if plst['pltype'] == "index":
        mk_pl_index(plst)
#        mk_thumbimgs(plst)
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
    elif plst['pltype'] == "hddfolder":
        mk_pl_hddfolder(plst)
    elif plst['pltype'] == "allmp4" or plst['pltype'] == "allmp3":
        mk_pl_all(plst)