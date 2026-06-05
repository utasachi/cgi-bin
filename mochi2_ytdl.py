#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
debug_idxs = set()    # 全部走行
debug_idxs = {6}   # 特定走行モード

import os, sys, json, re, requests, pickle, html, subprocess, glob, configparser
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(Path(__file__).resolve().parent)
print("Content-Type: text/html; charset=UTF-8\r\n")

karapath = bgvpath = ""
with open("../Apache24/conf/httpd-mochikara.conf", encoding="utf-8") as f:
    for line in f:
        if line.startswith("SetEnv BGV_PATH "): bgvpath  = line.split('"')[1]
        if line.startswith("SetEnv DOC_ROOT "): karapath = line.split('"')[1]
if not karapath or not bgvpath:
    raise RuntimeError("karapath か bgvpathの設定がない")
scrbased = karapath + "/MV_スクロール歌詞/"
dlbased  = bgvpath  + "/★未分類/"
downloads = Path.home() / "Downloads"
ytcookie = downloads / "www.youtube.com_cookies.txt"

# 関数
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
    url = f"https://www.uta-net.com/movie/{utaid}/"
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
    s = html.unescape(s)
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

def search_utanet(utaid):           # 歌ネットタグ取得
    requrl = "https://www.uta-net.com/song/" + utaid + "/"
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
    cmd = [
        "../bin/yt-dlp",
        "-f", "bv[height<=1080]+ba",
        "--merge-output-format", "mp4",
        "-N", "1",
        "-o", outfile, ]
    if os.path.isfile(ytcookie):
        cmd += ["--cookies", ytcookie]
    cmd += [f"https://www.youtube.com/watch?v={vidid}"]
    subprocess.run( cmd,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW, )
    if not os.path.exists(outfile):
        raise RuntimeError(f"yt-dlpに失敗 vidid={vidid} fname={outfile}")

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
        [
            "../bin/ffmpeg", "-y", "-i", vidf, "-vf",
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
        cmd += [f"https://www.youtube.com/watch?v={vidid}"]
        j = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW, )
        return json.loads(j)
    except subprocess.CalledProcessError as e:
        print("output=", repr(e.output))
        return None

def get_youtube_info(vidid):                    # youtube曲情報取得(まとめ)
    j = get_youtube_json(vidid)
    if not j:
        return None
    formats = j.get("formats", [])
    f = max(formats, key=lambda x: x.get("height") or 0) if formats else {}
    width = f.get("width") or 0
    height = f.get("height") or 0
    yinfo = {
        "title":      j.get("title", ""),
        "duration":   j.get("duration", 0),
        "view_count": j.get("view_count", 0),
        "width":      width,
        "height":     height,
        "aspect":     width / height if height else 0,
        "filesize": (
            j.get("filesize")
            or j.get("filesize_approx")
            or f.get("filesize")
            or f.get("filesize_approx")
            or 0 ),
    }
    return yinfo

def make_mp4_ass_single(plst,sinfo,vidid,mtype,vidname):  
    sinfo['vidid']   = vidid
    sinfo['vidname'] = vidname
    sinfo['mtype']   = mtype
    if plst['name'] == "THE FIRST TAKE":
        sinfo['mtype'] = "THE FIRST TAKE"
        sinfo['ystart'] = "720"
        sinfo['kstyle'] = "2"
    mp4f = get_fname(dldir,sinfo,"mp4")
    assf = get_fname(dldir,sinfo,"ass")
    if not os.path.exists(mp4f):
        print(f"downdoading...{vidid} {mp4f}")
        dl_youtube(vidid,mp4f)
    if not os.path.exists(assf):
        print(f"make ass...{vidid} {assf}")
        write_ass_sinfo(sinfo,assf)
        write_ass_diag(sinfo,assf)            

def make_mp4_ass_loopedit(sinfo,vidid,loopvid,mtype,vidname):  
    sinfo['vidid']   = vidid
    sinfo['loopvid'] = loopvid
    sinfo['vidname'] = vidname
    sinfo['mtype']   = mtype
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

def make_mp4_ass_1080p(sinfo,vidid,mtype):  
    sinfo['vidid']   = vidid
    sinfo['mtype']   = mtype
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

def not_pettern(plst,sinfo,yinfo0,yinfo1,yinfo2):
    print("情報取得失敗 or パターンにあてはまらない")
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
    url = f"https://www.uta-net.com/song/{utaid}/"
    writeini("error",utaid,url + " " + sinfo.get('title'),tini)
#    raise RuntimeError("情報取得失敗 or パターンにあてはまらない")
    return False

def make_mp4_ass(plst,sinfo,vidids):                 # ダウンロードパターン分け(ここが肝)
    yinfo0 = get_youtube_info(vidids[0])
    # パターン0 yinfo0の時点でダメな場合は返してしまう
    if not yinfo0:
        return not_pettern(plst,sinfo,yinfo0,None,None)
    if "ピアノ楽譜" in yinfo0.get('title'):
        return not_pettern(plst,sinfo,yinfo0,None,None)
    # パターン1 mv1 最初の候補がすべてかねそろえていれば
    # パターン1除外キーワードあり
    p1exkeywd = ["静止画","official audio"]
    if (    yinfo0['duration'] >= 120
        and yinfo0['aspect']   >= 1.1
        and not any(k.lower() in yinfo0['title'].lower() for k in p1exkeywd) ):
        title = yinfo0.get('title')
        print(f" パターン１ {vidids[0]} {title}")
        make_mp4_ass_single(plst,sinfo,vidids[0],"mv",title)
        return True
    # パターン2 mv2 次の候補がすべてかねそろえていれば
    yinfo1 = get_youtube_info(vidids[1])
    if ( yinfo1
        and yinfo1['duration'] >= 150
        and yinfo1['aspect']   >= 1.1 ):
        title = yinfo1.get('title')
        print(f" パターン２ {vidids[1]} {title}")
        make_mp4_ass_single(plst,sinfo,vidids[1],"mv",title)
        return True
    # パターン3 最初がフル、次が短い場合(short)、loopedit
    if ( yinfo1
        and yinfo0['duration'] >= 150
        and yinfo1['aspect']   >= 1.1 ):
        print(f" パターン３ aud={vidids[0]} vid={vidids[1]} utaid={utaid}")
        make_mp4_ass_loopedit(sinfo,vidids[0],vidids[1],"youtube",yinfo1.get('title'))
        return True
    # パターン4 最初が短い(short)、次がフルの場合、loopedit
    if ( yinfo1
        and yinfo1['duration'] >= 150
        and yinfo0['aspect']   >= 1.1 ):
        print(f" パターン４ aud={vidids[1]} vid={vidids[0]} utaid={utaid}")
        make_mp4_ass_loopedit(sinfo,vidids[1],vidids[0],"youtube",yinfo0.get('title'))
        return True
    # パターン5 最初も次もアルバムアート、次の次がshortの場合、loopedit
    yinfo2 = get_youtube_info(vidids[2])
    if ( yinfo1 and yinfo2
        and yinfo1 and yinfo2
        and yinfo0['duration'] >= 150
        and yinfo2['aspect']   >= 1.1 ):
        print(f" パターン５ aud={vidids[0]} vid={vidids[2]} utaid={utaid}")
        make_mp4_ass_loopedit(sinfo,vidids[0],vidids[2],"youtube",yinfo2.get('title'))
        return True
    # パターン6 最初も次もshort、次の次がアルバムアートの場合、loopedit
    yinfo2 = get_youtube_info(vidids[2])
    if ( yinfo1 and yinfo2
        and yinfo2['duration'] >= 150
        and yinfo0['aspect']   >= 1.1 ):
        print(f" パターン６ aud={vidids[2]} vid={vidids[0]} utaid={utaid}")
        make_mp4_ass_loopedit(sinfo,vidids[2],vidids[0],"youtube",yinfo0.get('title'))
        return True
    # パターン7 アルバムアートしかない場合、1080p　最初の使う
    if ( yinfo0['duration'] >= 150 ):
        print(f" パターン７ aud={vidids[0]} utaid={utaid}")
        make_mp4_ass_1080p(sinfo,vidids[0],"album art")
        return True
    # パターン8 アルバムアートしかない場合、1080p 次の使う
    if ( yinfo1 and yinfo1['duration'] >= 150 ):
        print(f" パターン８ aud={vidids[1]} utaid={utaid}")
        make_mp4_ass_1080p(sinfo,vidids[1],"album art")
        return True

    return not_pettern(plst,sinfo,yinfo0,yinfo1,yinfo2)

# メインループ
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
            ckfiles = scr_utaids.get(utaid)
            if ckfiles:
                continue                # ckfilesにあれば除外
            print(f"ckecking... https://www.uta-net.com/song/{utaid}/ {pgttl} {pgart}")
            vidids = get_vidids(utaid)
            if not vidids:
                print(f" no vidids!")
                continue                # 関連動画なければ除外
            sinfo = search_utanet(utaid)
            mp4s = glob.glob(glob.escape(get_fname(dldir,sinfo)[:-4]) + "*.mp4")
            asss = glob.glob(glob.escape(get_fname(dldir,sinfo)[:-4]) + "*.ass")
            if mp4s and asss:
                print(f" 作成済み {sinfo.get('title')}")
                continue                # 既に作成済みなら除外
            make_mp4_ass(plst,sinfo,vidids)

            # 継続ダイアログ
            # res = subprocess.run( ["../bin/UWSC.exe", "../bin/uwsc_vk.uws", "msg", "継続しますか？"])
            # print(res.returncode)
            # if res.returncode != 1:
            #     exit(0)
