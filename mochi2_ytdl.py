#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
debug_idxs = set()  # 全部走行
debug_idxs = {6}    # 特定走行モード
uwdiag = True       # 一行ごとにuwscのダイアログで聞いてくるやつ

import os, sys, json, re, pickle, html, subprocess, glob, configparser,shutil
import requests, time
from urllib.parse import quote, parse_qs
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(Path(__file__).resolve().parent)

# 定義
MPCBEEXE = "C:/mochikara2/MPC-BE/mpc-be64.exe"
LSTF = "../htdocs/mochilist.txt"
HEADER = "../htdocs/mochi2_HEADER.shtml"
FOOTER = "../htdocs/mochi2_README.shtml"
NOIMG = "/プレイリスト/images/noimg.png"
MOCSCEXE = r"..\ahk\MochiutaSC\MochiutaSC.exe"
MOCSCASS = r"..\..\htdocs\moass_header.ass"
URLYT = "https://www.youtube.com/watch?v="
URLUTAS = "https://www.uta-net.com/song/"
URLUTAM = "https://www.uta-net.com/movie/"

uri = os.environ.get("REQUEST_URI", "/").split("?", 1)[0]
karapath = bgvpath = ""
with open("../Apache24/conf/httpd-mochikara.conf", encoding="utf-8") as f:
    for line in f:
        if line.startswith("SetEnv BGV_PATH "): bgvpath  = line.split('"')[1]
        if line.startswith("SetEnv DOC_ROOT "): karapath = line.split('"')[1]
if not karapath or not bgvpath:
    raise RuntimeError("karapath か bgvpathの設定がない")
scrbased = karapath + "/MV_スクロール歌詞/"
dlbased  = bgvpath  + "/★未分類/"
ytcookie = "../tmp/www.youtube.com_cookies.txt"

# 関数
UWSC_MSG = "次に進みます。<#CR>[無視]でダイアログ出力を行わず継続します"
def uwsc_dialog(msg=UWSC_MSG):
    global uwdiag                # 継続ダイアログ
    if not uwdiag:
        return
    res = subprocess.run(["../bin/UWSC.exe", "../bin/uwsc_vk.uws", "msg",msg])
    # OK=1 x=2 中止=16 無視=64
    if res.returncode == 2 or res.returncode == 16:
        exit(0)
    elif res.returncode == 64:
        uwdiag = False
    elif res.returncode == 1:
        pass
    else:
        print(f"exit code={res.returncode}")
        exit(0)

def readini(section, key, filename, default=""):        # configparser版readini
    cfg = configparser.ConfigParser()
    cfg.read(filename, encoding="utf-8")
    return cfg.get(section, key, fallback=default)

def writeini(section, key, value, filename):            # configparser版writeini
    cfg = configparser.ConfigParser()
    cfg.read(filename, encoding="utf-8")
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg[section][key] = str(value)
    with open(filename, "w", encoding="utf-8") as f:
        cfg.write(f)

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

def get_vidids(utaid):
    url = f"{URLUTAM}{utaid}/"
    print(f"★歌ネットビデオ情報取得wait "+url)
    time.sleep(5)
    html = requests.get(url).text
    return list(dict.fromkeys(re.findall(
        r'https://www\.youtube\.com/embed/([^"?/]+)',
        html
    )))

def rep(s):                         # 文字列置き換え
    if s is None: return ""
    replacements = {
        '=': '＝',  ',': '，', '\'': '’',  '"': '“',
        '\\': '＼', '/': '／', ':': '：',  ';': '；',
        '<': '＜',  '>': '＞', '|': '｜',  '~': '～',
        '^': '＾',  '`': '｀', '*': '＊',  '?': '？',
        '%': '％',  '$': '＄', '[': '［',  ']': '］',
        '@': '＠',  '　': ' ', ' ': ' ',   '+': '＋',
        'é': 'e',   '&': '＆', '〜': '～'
    }
    s = html.unescape(s).replace('\xa0', ' ')
    for k, v in replacements.items():
        s = s.replace(k, v)
    # s = normalize_filename(s)
    return s

RE_PAREN = re.compile(r'\s*[（(][^）)]*[）)]')
def shorten_artist(name, limit=100):
    if len(name) <= limit:  return name         # 1. そのままで収まるなら何もしない
    shortened = RE_PAREN.sub('', name).strip()  # 2. 括弧内を削除
    if len(shortened) > limit:                  # 3. それでも長ければ … 付けて切る
        shortened = shortened[:limit-1].rstrip() + "…"
    return shortened

def get_fname(basedir, tag, ext="mp4",mmtype=""):   # tagからファイルパスを生成
    if not tag.get('mtype'):
        mtype = ""
    else:
        mtype = " " + tag['mtype'].replace("(on)","")
    if mmtype:
        mtype = mmtype
    artist = shorten_artist(tag['artist'])
    if tag.get('tieup'):
        fname = f"{basedir}/[{tag.get('tieup')}]{tag['title']}／{artist}{mtype}.{ext}"
    else:
        fname = f"{basedir}/{tag['title']}／{artist}{mtype}.{ext}"
    return fname

def get_fdir_fname(basedir, tag, ext="mp4", mmtype=""): # tagからファイルパス、フォルダも生成
    subdir = tag.get('subdir','')
    if not subdir:
        year = tag.get('year', '')
        try:
            y = int(year)
            if y <= 1989:   subdir = '1989以前'
            elif y <= 1999: subdir = '1990-1999'
            elif y <= 2009: subdir = '2000-2009'
            elif y <= 2019: subdir = '2010-2019'
            else:           subdir = year
        except (TypeError, ValueError):
            subdir = year
    return get_fname(basedir + subdir,tag,ext,mmtype)

def search_utanet(utaid):           # 歌ネットタグ取得
    requrl = URLUTAS + utaid + "/"
    print(f"★歌ネットタグ取得wait "+requrl)
    time.sleep(5)
    texts = requests.get(requrl).text
    tag = {}
    m = re.search(r'<h2 class="ms-2 ms-md-3 kashi-title">(.+?)</h2>', texts)
    tag['title'] = rep(m.group(1)) if m else ""
    m = re.search(r'<p class="ms-2 ms-md-3 mb-0" style=\'font-size:12px;\'>.+?</p>', texts, re.DOTALL)
    if m:
        tieup_text = re.search(r'>(.+?)</p>', m.group(0), re.DOTALL)
        tag['tieup'] = rep(tieup_text.group(1).strip()) \
            .replace('オープニング','OP').replace('エンディング','ED') \
            if tieup_text else ""
    else:
        tag['tieup'] = ""
    m = re.search(r'<span itemprop="byArtist name">(.+?)</span></a></h3>', texts)
    tag['artist'] = shorten_artist(rep(m.group(1))) if m else ""
    m = re.search(r'作詞：<a [^>]*itemprop="lyricist"[^>]*>(.+?)</a>', texts)
    tag['lyrics'] = rep(m.group(1)) if m else ""
    m = re.search(r'作曲：<a [^>]*itemprop="composer"[^>]*>(.+?)</a>', texts)
    tag['composition'] = rep(m.group(1)) if m else ""
    m = re.search(r'編曲：<a [^>]*itemprop="arranger"[^>]*>(.+?)</a>', texts)
    tag['arrangement'] = rep(m.group(1)) if m else ""
    m = re.search(r'発売日：(\d{4}/\d{2}/\d{2})', texts)
    if m:
        tag['release'] = m.group(1)
        tag['year'] = m.group(1).split("/")[0]
    else:
        tag['release'] = ""
        tag['year'] = ""
    ptn = r'<div id="kashi_area" itemprop="text">(.+?)</div>'
    m = re.search(ptn, texts, re.DOTALL)
    if m:
        kashi = m.group(1).replace('<br />', '\n').strip()
        tag['kashi'] = kashi
    else:
        tag['kashi'] = ""
    tag['utaid'] = utaid
    # チェック入れよう
    if tag['title'] == "" or tag['artist'] == "" or tag['year'] == "":
        print(texts)
        raise RuntimeError(f"タグ情報が不正 utaid={utaid}")
    return tag

def is_drange(v, min=0, max=0):                         # 数値範囲内チェック
    try:
        n = int(v)
    except (TypeError, ValueError):
        return False
    if min == 0 and max == 0:
        return True
    return min <= n <= max

def get_inif(filepath, enc=""):         # iniファイルの読み込み（簡易版）
    result = {}
    if enc == "":
        try:
            text = Path(filepath).read_text(encoding="utf-8")
            enc="utf-8"
        except UnicodeDecodeError:
            text = Path(filepath).read_text(encoding="cp932")
            enc="cp932"
    with open(filepath, encoding=enc) as f:
        for line in f:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, value = map(str.strip, line.split('=', 1))
            result[key] = value
    return result

def mmss(duration_seconds):             # mm:ss表記はこれに統一
    duration_seconds = int(duration_seconds)
    minutes = int(duration_seconds // 60)
    seconds = int(duration_seconds % 60)
    return f"{minutes:02}:{seconds:02}"

def get_video_duration(video):          # ffprobeからファイルのduration取得
    cmd = [ "../bin/ffprobe.exe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video ]
    out = subprocess.check_output(cmd, text=True).strip()
    sec = int(float(out))
    return sec

def write_ass_sinfo(sinfo,assf):                  # ass sinfo部分記入
    lines = []
    in_sinfo = False
    replaced = False
    # assのフォーマットはmoassのバージョンのものを使用
    with open("../htdocs/moass_header.ass", encoding="utf-8") as f:
        for line in f:
            if line.startswith(";[Song Info]"):         # 開始
                in_sinfo = True
                replaced = True
                lines.append(";[Song Info]\n")
                for k, v in sinfo.items():
                    if k == 'kashi' : continue
                    lines.append(f";{k}={v}\n")
                continue
            if in_sinfo and line.startswith(";["):   # 終了
                in_sinfo = False
                lines.append(line)
                continue
            if in_sinfo:         # Song Info 内の既存行は捨てる
                continue
            lines.append(line)
    if not replaced:                # セクションが存在しなかった場合は異常
        raise RuntimeError("no ;[Song Info]")
    with open(assf, "w", encoding="utf-8") as f:        # 上書き保存
        f.writelines(lines)

def write_ass_diag(sinfo,assf):                  # ass diag部分記入
    kashi = sinfo['kashi'].splitlines()
    if len(kashi) < 3:
        raise RuntimeError("len(kashi) < 3")
    lines = []
    with open(assf, encoding="utf-8") as f:
        for line in f:
            if line.startswith("Dialogue:"):            # 既存Diag削除
                continue
            lines.append(line)
    # assのフォーマットはmoassのバージョンのものを使用
    diag = get_inif("../htdocs/moass_header.ass","utf-8")
    if is_drange(sinfo.get('kstyle'),1,8):              # スタイル差し替え
        for k, v in diag.items():
            diag[k] = v.replace('Kanji1','Kanji' + sinfo['kstyle']) \
                .replace('sInfo1','sInfo' + sinfo['kstyle']) \
                .replace('sRuby1','sRuby' + sinfo['kstyle'])
    lines.append(diag[';f01'] + sinfo['title'] +"\n")       # 曲情報歌詞記入
    artist = sinfo['artist']                                # artist名長いの対応
    if len(artist) > 56:
        artist = shorten_artist(sinfo['artist'],56)
    if len(artist) > 32:
        diag[';f02'] = diag[';f02'].replace('sInfo', 'sRuby')
    lines.append(diag[';f02'] + artist +"\n")
    if diag.get(';f03') and sinfo.get('tieup'):
        lines.append(diag[';f03'] + sinfo['tieup'] +"\n")
        lines.append(diag[';f04'] + sinfo['year'] +"\n")
    else:
        lines.append(diag[';f03'] + sinfo['year'] +"\n")
    if diag.get(';f05') and sinfo.get('lyrics'):
        lines.append(diag[';f05'] + sinfo['lyrics'] +"\n")
    if diag.get(';f06') and sinfo.get('composition'):
        lines.append(diag[';f06'] + sinfo['composition'] +"\n")
    if diag.get(';f07') and sinfo.get('arrangement'):
        lines.append(diag[';f07'] + sinfo['arrangement'] +"\n")
    if diag.get(';f08') and sinfo.get('vidname'):
        lines.append(diag[';f08'] + shorten_artist(sinfo['vidname'],36) +"\n")
    ystart = 480
    if is_drange(sinfo.get('ystart')):
        ystart = int(sinfo['ystart'])
    yend = 200
    if is_drange(sinfo.get('yend')):
        yend   = int(sinfo['yend'])
    t1 = ystart
    t2 = yend - ((len(kashi) - 1) * 40)
    mp4f = str(Path(assf).with_suffix(".mp4"))
    durat = mmss(get_video_duration(mp4f)) 
    f11 = diag[';f11'].replace(":ee:ee.",f":{durat}.")
    for kline in kashi:
        fv = f11.replace('t1',str(t1)).replace('t2',str(t2))
        if len(kline) > 50: fv = fv.replace('Kanji', 'sInfo')
        lines.append(fv + kline +"\n")
        t1=t1 + 40
        t2=t2 + 40
    with open(assf, "w", encoding="utf-8") as f:        # 上書き保存
        f.writelines(lines)

def dl_youtube(vidid, outfile):                 # youtubeからDL 本体
    cmd = [ "../bin/yt-dlp",
            "-f", "bv[height<=1080]+ba",
            "--merge-output-format", "mp4",
            "-N", "1",
            "-o", outfile,]
    if os.path.isfile(ytcookie):
        cmd += ["--cookies", ytcookie]
    cmd += [f"{URLYT}{vidid}"]
    try:
        subprocess.run( cmd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,)
    except subprocess.CalledProcessError as e:
        print(e.stdout)      # yt-dlp のエラー内容を表示
        raise
    if not os.path.exists(outfile):
        raise RuntimeError(
            f"yt-dlpに失敗 vidid={vidid} fname={outfile}"
        )

def mk_loopedit(audf, vidf, mp4f):              # ffmpeg loopedit 本体
    subprocess.run(
        [  "../bin/ffmpeg", "-y", "-stream_loop", "5",
            "-i", vidf,
            "-i", audf,
            "-shortest", "-map", "0:v:0", "-map", "1:a",
            "-c:v", "copy", "-c:a", "copy", mp4f ],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW )
    if not os.path.exists(mp4f):
        raise RuntimeError(f"ffmpegに失敗 fname={mp4f}")

def mk_1080p(vidf, mp4f):                       # 1080p 本体
    subprocess.run(
        [   "../bin/ffmpeg", "-y", "-i", vidf, "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:0:(oh-ih)/2:black",              # 左端寄せ
#            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",     # 中央寄せ
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23", "-c:a", "copy", mp4f ],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW )
    if not os.path.exists(mp4f):
        raise RuntimeError(f"ffmpegに失敗 fname={mp4f}")

def get_youtube_json(vidid):                    # youtubeから曲情報取得 本体
    try:
        cmd = ["../bin/yt-dlp", "-J", ]
        if os.path.isfile(ytcookie):
            cmd += ["--cookies", ytcookie]
        cmd += [f"{URLYT}{vidid}"]
        j = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW, )
        return json.loads(j)
    except subprocess.CalledProcessError as e:
        print("output=", repr(e.output))
        return None

def get_pl_vidids(plid):
    try:
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-single-json",
            f"https://www.youtube.com/playlist?list={plid}",
        ]
        data = json.loads(subprocess.check_output(
            cmd, text=True, encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW
            ))
        return [ e["id"]
            for e in data.get("entries", [])
            if e and "id" in e ]
    except subprocess.CalledProcessError as e:
        print("output=", repr(e.output))
        return None

def get_youtube_info(vidid):                    # youtube曲情報取得(まとめ)
    j = get_youtube_json(vidid)
    if not j:
        return None
    formats = j.get("formats", [])
    f = max(formats, key=lambda x: x.get("height") or 0) if formats else {}
    width  = f.get("width") or 0
    height = f.get("height") or 0
    track  = j.get("track") or j.get("alt_title") or j.get("title")
    artist = j.get("artist") or j.get("creator") or j.get("channel") or j.get("uploader")
    yinfo = {
        "title":      rep(j.get("title", "")),
        "duration":   j.get("duration", 0),
        "view_count": j.get("view_count", 0),
        "track":      track,
        "artist":     artist,
        "width":      width,
        "height":     height,
        "aspect":     width / height if height else 0,
        "filesize": (
            j.get("filesize")
            or j.get("filesize_approx")
            or f.get("filesize")
            or f.get("filesize_approx")
            or 0 ), }
    return yinfo

def make_mp4_ass_single(plst,sinfo,vidid,mtype,vidname):  
    sinfo['vidid']   = vidid
    sinfo['vidname'] = vidname
    sinfo['mtype']   = mtype
    if plst['name'] == "THE FIRST TAKE":
        sinfo['mtype'] = "THE FIRST TAKE"
        sinfo['ystart'] = "720"
        sinfo['kstyle'] = "2"
    if plst.get('folder',''):
        sinfo['subdir'] = plst['folder']
    mp4f = get_fname(dldir,sinfo,"mp4")
    assf = get_fname(dldir,sinfo,"ass")
    if not os.path.exists(mp4f):
        print(f"downdoading...{vidid} {mp4f}")
        dl_youtube(vidid,mp4f)
    if not os.path.exists(assf):
        print(f"make ass...{vidid} {assf}")
        write_ass_sinfo(sinfo,assf)
        write_ass_diag(sinfo,assf)            

def make_mp4_ass_loopedit(plst,sinfo,vidid,loopvid,mtype,vidname):
    sinfo['vidid']   = vidid
    sinfo['loopvid'] = loopvid
    sinfo['vidname'] = vidname
    sinfo['mtype']   = mtype
    if plst.get('folder',''):
        sinfo['subdir'] = plst['folder']
    audf = get_fname(dldir,sinfo,"aud.mp4")
    vidf = get_fname(dldir,sinfo,"vid.mp4")
    mp4f = get_fname(dldir,sinfo,"mp4")
    assf = get_fname(dldir,sinfo,"ass")
    if not os.path.exists(audf):
        print(f"  downdoad audf...{vidid} {audf}")
        dl_youtube(vidid  ,audf)
    if not os.path.exists(vidf):
        print(f"  downdoad vidf...{loopvid} {vidf}")
        dl_youtube(loopvid,vidf)
    if not os.path.exists(mp4f):
        print(f"  marge ...{mp4f}")
        mk_loopedit(audf,vidf,mp4f)
    if not os.path.exists(assf):
        print(f"  make ass...{assf}")
        write_ass_sinfo(sinfo,assf)
        write_ass_diag(sinfo,assf)            

def make_mp4_ass_1080p(plst,sinfo,vidid,mtype):  
    sinfo['vidid']   = vidid
    sinfo['mtype']   = mtype
    if plst.get('folder',''):
        sinfo['subdir'] = plst['folder']
    vidf = get_fname(dldir,sinfo,"vid.mp4")
    mp4f = get_fname(dldir,sinfo,"mp4")
    assf = get_fname(dldir,sinfo,"ass")
    if not os.path.exists(vidf):
        print(f"  downdoad vidf...{vidid} {vidf}")
        dl_youtube(vidid,vidf)
    if not os.path.exists(mp4f):
        print(f"  make 1080p ...{mp4f}")
        mk_1080p(vidf,mp4f)
    if not os.path.exists(assf):
        print(f"  make ass...{assf}")
        write_ass_sinfo(sinfo,assf)
        write_ass_diag(sinfo,assf)            

def trace_nopat_yinfo(plst,sinfo,yinfo0=None,yinfo1=None,yinfo2=None):
    print("youtube情報取得失敗 or パターンにあてはまらない")
    print("  yinfo0----------")
    if yinfo0:
        for k, v in yinfo0.items():
            print(f"   {k}: {v}")
    print("  yinfo1----------")
    if yinfo1:
        for k, v in yinfo1.items():
            print(f"   {k}: {v}")
    print("  yinfo2----------")
    if yinfo2:
        for k, v in yinfo2.items():
            print(f"   {k}: {v}")
    tini = dlbased + plst['name'] + "/!mochi2err.txt"
    utaid = sinfo.get('utaid')
    url = f"{URLUTAS}{utaid}/"
    writeini("no_yinfo",utaid,url + " " + sinfo.get('title'),tini)
    return False

def trace_nopat_utaid(plst,vidid,yinfo0=None):
    print("uta-net情報取得失敗")
    print("  yinfo0----------")
    if yinfo0:
        for k, v in yinfo0.items():
            print(f"   {k}: {v}")
    tini = dlbased + plst['name'] + "/!mochi2err.txt"
    url = f"{URLYT}{vidid}"
    writeini("no_utaid",vidid,url + " " + yinfo.get('title'),tini)
    return False

def make_mp4_ass(plst,sinfo,vidids,expat=""):        # ダウンロードパターン分け(ここが肝)
    # 成功したらそのパターン番号、失敗したら取得内容をtrace出力してFalseを返す
    # expatに"mv"を指定した場合、パターン番号1と2(mvを出力するパターン)は作成していても後続の処理をする
    yinfo0 = get_youtube_info(vidids[0])
    # パターン0 yinfo0の時点でダメな場合は返してしまう
    if not yinfo0:
        return trace_nopat_yinfo(plst,sinfo,yinfo0)
    if "ピアノ楽譜" in yinfo0.get('title'):
        return trace_nopat_yinfo(plst,sinfo,yinfo0)
    # パターン1 mv1 最初の候補がすべてかねそろえていれば
    # パターン1除外キーワードあり
    p1exkeywd = ["静止画","official audio"]
    if (    yinfo0['duration'] >= 120
        and yinfo0['aspect']   >= 1.1
        and not any(k.lower() in yinfo0['title'].lower() for k in p1exkeywd)
        and expat != "mv" ):
        title = yinfo0.get('title')
        print(f" パターン１ {vidids[0]} {title}")
        make_mp4_ass_single(plst,sinfo,vidids[0],"mv",title)
        return 1
    # パターン2 mv2 次の候補がすべてかねそろえていれば
    yinfo1 = get_youtube_info(vidids[1]) if len(vidids) >= 2 else None
    if ( yinfo1
        and yinfo1['duration'] >= 150
        and yinfo1['aspect']   >= 1.1
        and expat != "mv" ):
        title = yinfo1.get('title')
        print(f" パターン２ {vidids[1]} {title}")
        make_mp4_ass_single(plst,sinfo,vidids[1],"mv",title)
        return 2
    # パターン3 最初がフル、次が短い場合(short)、loopedit
    if ( yinfo1
        and yinfo0['duration'] >= 150
        and yinfo1['aspect']   >= 1.1 ):
        print(f" パターン３ aud={vidids[0]} vid={vidids[1]} utaid={utaid}")
        make_mp4_ass_loopedit(plst,sinfo,vidids[0],vidids[1],"youtube",yinfo1.get('title'))
        return 3
    # パターン4 最初が短い(short)、次がフルの場合、loopedit
    if ( yinfo1
        and yinfo1['duration'] >= 150
        and yinfo0['aspect']   >= 1.1 ):
        print(f" パターン４ aud={vidids[1]} vid={vidids[0]} utaid={utaid}")
        make_mp4_ass_loopedit(plst,sinfo,vidids[1],vidids[0],"youtube",yinfo0.get('title'))
        return 4
    # パターン5 最初も次もアルバムアート、次の次がshortの場合、loopedit
    yinfo2 = get_youtube_info(vidids[2]) if len(vidids) >= 3 else None
    if ( yinfo1 and yinfo2
        and yinfo0['duration'] >= 150
        and yinfo2['aspect']   >= 1.1 ):
        print(f" パターン５ aud={vidids[0]} vid={vidids[2]} utaid={utaid}")
        make_mp4_ass_loopedit(plst,sinfo,vidids[0],vidids[2],"youtube",yinfo2.get('title'))
        return 5
    # パターン6 最初も次もshort、次の次がアルバムアートの場合、loopedit
    if ( yinfo1 and yinfo2
        and yinfo2['duration'] >= 150
        and yinfo0['aspect']   >= 1.1 ):
        print(f" パターン６ aud={vidids[2]} vid={vidids[0]} utaid={utaid}")
        make_mp4_ass_loopedit(plst,sinfo,vidids[2],vidids[0],"youtube",yinfo0.get('title'))
        return 6
    # パターン7 アルバムアートしかない場合、1080p　最初の使う
    if ( yinfo0['duration'] >= 150 ):
        print(f" パターン７ aud={vidids[0]} utaid={utaid}")
        make_mp4_ass_1080p(plst,sinfo,vidids[0],"album art")
        return 7
    # パターン8 アルバムアートしかない場合、1080p 次の使う
    if ( yinfo1 and yinfo1['duration'] >= 150 ):
        print(f" パターン８ aud={vidids[1]} utaid={utaid}")
        make_mp4_ass_1080p(plst,sinfo,vidids[1],"album art")
        return 8
    return trace_nopat_yinfo(plst,sinfo,yinfo0,yinfo1,yinfo2)

def search_site(s, n=0):                # キーワードで歌ネット検索（n番目のhit）
    FENRIR = "https://search.fenrir-inc.com/?hl=ja&channel=sleipnir_s&safe=off&lr=all&fr=ss&q="
    requrl = FENRIR + "歌ネット 歌詞ページ " + quote(s)
    lines = requests.get(requrl).text.splitlines()
    hits = []
    for line in lines:
        if URLUTAS in line:
            m = re.search(r'/song/(\d+)/', line)
            if m:
                hits.append(m.group(1))
        if URLUTAM in line:
            m = re.search(r'/movie/(\d+)/', line)
            if m:
                hits.append(m.group(1))
    return hits[n] if n < len(hits) else ""

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

def read_ass_kashi(assf):           # assの歌詞部分を取得
    kashi = ""
    with open(assf, encoding="utf-8") as f:
        for line in f:
            if line.startswith("Dialogue: 1,"):
                kashi = kashi + line.rsplit('}', 1)[1]
    return kashi

def get_imgurl(sinfo, mp4f = None):           # youtubeの画像urlを返す
    vidid = ""
    if sinfo and sinfo.get('loopvid'):    vidid = sinfo['loopvid']
    elif sinfo and sinfo.get('vidid'):    vidid = sinfo['vidid']
    elif sinfo and sinfo.get('videoId'):  vidid = sinfo['videoId']
    if vidid:
        return "https://i.ytimg.com/vi/" + vidid + "/mqdefault.jpg"
    return NOIMG

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

def a_cmdlink(c, t, msg, p1, p2default=None):   # コマンドリンク作成
    p1 = quote(p1, safe="/")
    if p2default is not None:
        return (
            f'[<a class="link-hover" href="#" '
            f'onclick="'
            f'let s=prompt(\'{msg}\', \'{p2default}\');'
            f'if(s!==null){{location.href=\'?c={c}&p1={p1}&p2=\'+encodeURIComponent(s);}}'
            f'return false;">'
            f'{t}</a>]\n'
        )
    elif msg:
        return (
            f'[<a href="?c={c}&p1={p1}" '
            f'onclick="return confirm(\'{msg}\');">{t}</a>]\n'
        )
    else:
        return f'[<a href="?c={c}&p1={p1}">{t}</a>]\n'

def html_tr(nocnt,based,mp4f):                  # スクロール歌詞編集
        mp4i = mp4f.replace(based,'')
        name_style = mp4i
        if "/" in mp4i:
            i = mp4i.rfind("/")
            name_style = f'<div class="pl-smain">{emoji(mp4i)} {mp4i[:i+1]}</div>{mp4i[i+1:]}'
        assf = str(Path(mp4f).with_suffix(".ass"))
        sinfo = read_ass_sinfo(assf)
        comment = ""
        for k, v in sinfo.items():
            if k == "utaid":
                v = f'<a class="link-hover" href="{URLUTAM}{v}/">{v}</a>'
            elif k in ("vidid", "loopvid"):
                v = f'<a class="link-hover" href="{URLYT}{v}">{v}</a>'
            comment += f"{k}:{v} , "
        mvlink = 'class="mvlink"'
        icon = get_imgurl(sinfo)
# ここにコマンドリンクを羅列
        cmd_style  = a_cmdlink('mochiutasc',"編集","",mp4i)
        cmd_style += a_cmdlink('loopedit',"ループ","ループ編集する映像(mp4)を指定してください",mp4i,"")
        cmd_style += a_cmdlink('edit_ass',"ass","",mp4i)
        cmd_style += a_cmdlink('edit_ini',"ini","",mp4i)
        cmd_style += a_cmdlink('delete',"🗑️削除",f"🗑️削除してもよろしいですか？\\n{mp4i}",mp4i)
        cmd_style += a_cmdlink('deploy',"📦配置",f"📦配置してもよろしいですか？\\n{mp4i}",mp4i)
        print (f'''
    <tr class="pl-tr">
    <td rowspan=3 class="pl-no">{nocnt}</td>
    <td rowspan=3 class="pl-icon-hover">
        <a {mvlink} href="?c=play&p1={quote(mp4i, safe="/")}">
        <img class="pl-img" src="{icon}"></a></td>
    <td class="pl-main1-hover">
        <a {mvlink} href="?c=play&p1={quote(mp4i, safe="/")}">
        <b>{name_style}</b></a></td>
    </tr>
    <tr class="pl-tr"><td class="pl-main2-hover">
{cmd_style}
    </td></tr>
    <tr class="pl-tr"><td class="pl-comment">{comment}</td></tr>
''')

def utaidav(p2):
    print("<pre>uta-net指定作成...")
    parts = p2.split(",")
    if len(parts) < 3:
        print(f"パラメータが足りない {p2}")
        return False
    utaid, audseq, vidseq = parts[:3]
    if "uta-net" in utaid:
        utaid = utaid.rstrip("/").split("/")[-1]
    print(f"utaid={utaid},audseq={audseq},vidseq={vidseq}",flush=True)
    sinfo = search_utanet(utaid)
    if not sinfo.get('title'):
        print(f"not utaid {utaid}",flush=True)
        return False

    # make_mp4_ass_loopedit(plst,sinfo,vidid,loopvid,mtype,vidname):
    print("</pre>")


# メイン
# コマンドラインの場合
if uri == "/":
    scr_utaids = collect_ids("utaid")
    with open("mochi2_makepl.json", "r", encoding="utf-8") as f:
        plists = json.load(f)
    for i, plst in enumerate(plists):
        if debug_idxs and i not in debug_idxs: continue
        if not plst.get('download'): continue
        print(f"プレイリスト:{plst['name']} pltype={plst['pltype']}")
        dldir = dlbased + plst['name'] + "/"
        Path(dldir).mkdir(parents=True, exist_ok=True)

    # 歌ネット
        if plst['pltype'] == "uta-net":
            page = requests.get(plst['url']).text
            pattern = re.compile(r'<a href="/song/(\d+)/">(.*?)</a>\s*/\s*(.*?)</td>')
            for utaid, pgttl, pgart in pattern.findall(page):
                if int(utaid) < 300000:     # 古い曲除外
                    continue
                if any("youtube.mp4" in f for f in scr_utaids.get(utaid, [])):
                    continue
                print(f"ckecking... {URLUTAS}{utaid}/ {pgttl} {pgart}")
                mvpat = ""
                if scr_utaids.get(utaid):
                    mvpat = "mv"
                    print (f" mvありyoutubeなし {utaid} {pgttl} {pgart}")
                    continue                # ★mv以外作成モードはお休み
                tini = dlbased + plst['name'] + "/!mochi2err.txt"
                if readini("no_sinfo",utaid,tini):
                    print(f" 歌詞なし {utaid} {pgttl} {pgart}")
                    continue                # no_utaid にあれば除外
                vidids = get_vidids(utaid)
                if not vidids:
                    print(f" no vidids!")
                    continue                # 関連動画なければ除外
                sinfo = search_utanet(utaid)
                # ★mv以外作成モードはお休み
                # mp4s = glob.glob(glob.escape(get_fname(dldir,sinfo)[:-4]) + "*youtube.mp4")
                # asss = glob.glob(glob.escape(get_fname(dldir,sinfo)[:-4]) + "*youtube.ass")
                mp4s = glob.glob(glob.escape(get_fname(dldir,sinfo)[:-4]) + "*.mp4")
                asss = glob.glob(glob.escape(get_fname(dldir,sinfo)[:-4]) + "*.ass")
                if mp4s and asss:
                    print(f" 作成済み {sinfo.get('title')}")
                    continue                # 既に作成済みなら除外
                # ★mv以外作成モードはお休み
                # pat = make_mp4_ass(plst,sinfo,vidids,mvpat)
                # if pat == 1:
                #     print(" mv作成済み、youtube作成")
                #     make_mp4_ass(plst,sinfo,vidids,"mv")
                make_mp4_ass(plst,sinfo,vidids)
                uwsc_dialog()

    # ytplist FirstTakeなど
        if plst['pltype'] == "ytplist":
            # フォルダ指定があった場合はフォルダのなかでだけ探す
            if plst.get('folder'):
                scr_vidids = collect_ids("vidid",scrbased + plst.get('folder'))
            else:
                scr_vidids = collect_ids("vidid")           
            vidids = get_pl_vidids(plst.get('plid'))
            for vidid in vidids[:20]:
                if scr_vidids.get(vidid):
                    continue                # ckfilesにあれば除外
                tini = dlbased + plst['name'] + "/!mochi2err.txt"
                if readini("no_utaid",vidid,tini):
                    print(f" 歌詞なし {vidid}")
                    continue                # ★ no_utaid にあれば除外
                yinfo = get_youtube_info(vidid)
                if not yinfo:
                    print(f" no yinfo vidid={vidid}")
                    uwsc_dialog()
                    continue
                s = f"{yinfo.get('track') or ''} {yinfo.get('artist') or ''}"
                s = s.replace("\xa0", " ").replace("-"," ").replace("/"," ").replace("  "," ")
                s = s.replace("THE FIRST TAKE","")
                print(f"ckecking... {URLYT}{vidid} , {repr(s)}")
                utaid = search_site(s)
                if not utaid:
                    print(f" no utaid search={repr(s)}")
                    writeini("no_utaid",vidid,f"{URLYT}{vidid} {s}",tini)
                    uwsc_dialog()
                    continue
                print(f"ckecking... {URLUTAM}{utaid}/ , {repr(s)}")
                sinfo = search_utanet(utaid)
                print(f" track  yt={yinfo.get('track')}")
                print(f"       uta={sinfo.get('title')}")
                print(f" artist yt={yinfo.get('artist')}")
                print(f"       uta={sinfo.get('artist')}")
                # ★ここで照合のプロセス入れたほうがいい
                # 存在チェック、ytplistの場合ほかのフォルダも見る
                basepat = os.path.basename(get_fname(dldir, sinfo)[:-4])
                mp4s = glob.glob(f"{glob.escape(dlbased)}/**/{glob.escape(basepat)}*.mp4", recursive=True)
                asss = glob.glob(f"{glob.escape(dlbased)}/**/{glob.escape(basepat)}*.ass", recursive=True)
                if mp4s and asss:
                    print(f" 作成済み {sinfo.get('title')}")
                    continue
                make_mp4_ass(plst,sinfo,[vidid])
                uwsc_dialog()

        # 該当フォルダの.aud.mp4 / .vid.mp4を消す
        for f in Path(dldir).glob("*.vid.mp4"): f.unlink()
        for f in Path(dldir).glob("*.aud.mp4"): f.unlink()

# CGI の場合
else:
    print("Content-Type: text/html; charset=UTF-8\r\n")
    params  = parse_qs(os.environ.get("QUERY_STRING", ""))
    paramc  = params.get("c",[''])[0]
    p1 = params.get("p1",[''])[0]
    p2 = params.get("p2",[''])[0]
    based = dlbased
    mp4f = based + p1
    assf = str(Path(mp4f).with_suffix(".ass"))

# ヘッダ表示
    py = "/cgi-bin/mochi2_ytdl.py"
    title_page="開発者メニュー"
    title_txt = f'<a href="{py}">{title_page}</a>：{based} -> {paramc}'
    meta_add = ""
    if paramc:
        meta_add = f'<meta http-equiv=refresh content=2;URL={py}>'
    if p1:
        title_txt += f'<div class="normal-blue">{p1}</div>'
    print( f'''\
    <html><head><title>{title_page}:{paramc}</title>
    <link rel="icon" href="/favicon.ico">
    {meta_add}
    </head><body>
    ''')
    with open(HEADER, "r", encoding="utf-8") as f:
        for line in f:
            if '<!--#include virtual="/cgi-bin/mochi2_bread.py" -->' in line:
                print(f'<span class="big">{title_txt}</span>')
            else:
                print(line, end="")
    print('<hr>',flush=True)

# コマンド一覧
    if paramc == "play":
        p = subprocess.Popen([MPCBEEXE,'/add',mp4f,'/sub',assf,'/play'])
        print(f"【再生】<br>{mp4f}<br>")

    if paramc == "mochiutasc":
        mp4f = mp4f.replace('/','\\')
        p = subprocess.Popen([MOCSCEXE,mp4f,MOCSCASS])
        print(f"【編集 MochiutaSC】<br>{mp4f}<br>")

    if paramc == "loopedit":
        p2f = os.path.join(os.path.dirname(mp4f), p2)
        if not os.path.isfile(mp4f):
            print(f"ファイルがありません<br>mp4f={mp4f}")
        elif not os.path.isfile(assf):
            print(f"ファイルがありません<br>assf={assf}")
        elif not os.path.isfile(p2f):
            print(f"ファイルがありません<br>p2f={p2f}")
        else:
            print(f"loopedit開始します<br>",flush=True)
            loopf = mp4f.replace(".mp4","_loopedit.mp4")
            loopassf = loopf.replace(".mp4",".ass")
            sinfo = read_ass_sinfo(assf)
            sinfo['mtype'] = "youtube"
            sinfo['kashi'] = read_ass_kashi(assf)
            sinfo['vidname'] = p2.replace(".mp4","")
            sinfo['loopvid'] = "x"
            mk_loopedit(mp4f,p2f,loopf)
            write_ass_sinfo(sinfo,loopassf)
            write_ass_diag(sinfo,loopassf)
            os.remove(p2f)
            print(f"完了しました。assを修正してloopvid,vidnameを編集してください",flush=True)

    if paramc == "utaidav":
        utaidav(p2)

    if paramc == "edit_ass":
        p = subprocess.Popen(['notepad.exe',assf])
        print(f"【編集 ass】<br>{assf}<br>")
    
    if paramc == "deploy":
        sinfo = read_ass_sinfo(assf)
        tomp4f = get_fdir_fname(scrbased,sinfo,"mp4")
        toassf = get_fdir_fname(scrbased,sinfo,"ass")
        if os.path.exists(tomp4f):
            print(f"【削除mp4】<br>{tomp4f}<br>")
            os.remove(tomp4f)
        print(f"【配置mp4】<br>{tomp4f}<br>")
        shutil.move(mp4f, tomp4f)
        if os.path.exists(toassf):
            print(f"【削除ass】<br>{toassf}<br>")
            os.remove(toassf)
        print(f"【配置ass】<br>{toassf}<br>")
        shutil.move(assf, toassf)
        print(f"キャッシュを削除します")
        for f in glob.glob("../tmp/*.pkl"):
            os.remove(f)

    if paramc == "delete":
        if os.path.isfile(assf):
            tini = os.path.dirname(assf) + "/!mochi2err.txt"
            sinfo = read_ass_sinfo(assf)
            # ちょいと雑だがuta-netフォルダならno_sinfoで削除
            if "uta-net" in os.path.basename(os.path.dirname(assf)):
                utaid = sinfo.get("utaid")
                url = URLUTAS + utaid + "/"
                writeini("no_sinfo",utaid,f"{url} {sinfo['title']} ／ {sinfo['artist']}" ,tini)
                print(f"【削除 - no_sinfo】<br>{assf}<br>")
            # ちょいと雑だがそれ以外のフォルダならno_utaidで削除
            else:
                vidid = sinfo.get("vidid")
                url = f"{URLYT}{vidid}"
                writeini("no_utaid",vidid,url + " " + sinfo.get('vidname'),tini)
                print(f"【削除 - no_utaid】<br>{assf}<br>")
            Path(assf).unlink(missing_ok=True)
        print(f"【削除】<br>{mp4f}<br>")
        Path(mp4f).unlink(missing_ok=True)

    if paramc == "edit_ini" or paramc == "delete":
        tini = os.path.dirname(assf) + "/!mochi2err.txt"
        p = subprocess.Popen(['notepad.exe',tini])
        print(f"【編集 ini】<br>{tini}<br>")

    if not paramc:
# ヘッダ下
        msg  = "動画のutaid,audioの順番,videoの順番をカンマ区切りで指定してください\\n"
        msg += "(順番は0始まりの数字です)"
        print(a_cmdlink("utaidav","uta-net指定作成",msg,"",""))

# 編集楽曲一覧
        nocnt = 1
        for mp4p in Path(based).rglob("*.mp4"):
            mp4f = str(mp4p).replace('\\','/')
            print('<table class="pl-table">')
            html_tr(nocnt,based,mp4f)
            print('</table>')
            nocnt += 1
    else:
        print("<hr>ページを転送しています。しばらくお待ちください……\n</body></html>")