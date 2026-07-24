#!c:/mochikara2/.venv/Scripts/pythonw.exe
# -*- coding: utf-8 -*-
# pip install mutagen
# pip install chardet
# pip install rapidfuzz
import os, sys, cgi, subprocess, random, time, shutil, re
from urllib.parse import quote, unquote, urlsplit
from pathlib import Path
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from rapidfuzz import fuzz
import chardet

sys.stdout.reconfigure(encoding='utf-8')
print("Content-Type: text/html; charset=UTF-8\r\n")

# 定義
MPCBEEXE = "C:/mochikara2/MPC-BE/mpc-be64.exe"
LSTF = "../htdocs/mochilist.txt"
HEADER = "../htdocs/mochi2_HEADER.shtml"
FOOTER = "../htdocs/mochi2_README.shtml"
NOIMG = "/プレイリスト/images/noimg.png"

uri = os.environ.get("REQUEST_URI", "/").split("?", 1)[0]
splituri = urlsplit(uri)
uripath   = unquote(splituri.path)
uriquery  = splituri.query
unquri    = unquote(uri)
urifolder, urifile = uripath.rsplit("/", 1)

intermission = os.environ['INTERMISSION']
track_chg = os.environ['TRACK_CHG']
key_chg = os.environ['KEY_CHG']
bgvroot = f"{os.environ['BGV_PATH']}"
fname = f"{os.environ['DOC_ROOT']}{unquri}"
assf = str(Path(fname).with_suffix(".ass"))
ssaf = str(Path(fname).with_suffix(".ssa"))
txtf = str(Path(fname).with_suffix(".txt"))
extf = os.path.splitext(fname)[1].lstrip(".")
thumbimgf = (
    fname.replace('\\', '/')
         .replace('/', '_')
         .replace(':_karaoke_', ':/karaoke/プレイリスト/thumbimgs/')
         .rsplit('.', 1)[0] + '.jpg'
)

# 関数
def read_text(path):
    try:
        with open(path, "r", encoding="utf-16") as f:
            return f.read(), "utf-16"
    except UnicodeError:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read(), "utf-8"
        except UnicodeDecodeError:
            with open(path, "r", encoding="cp932", errors="replace") as f:
                return f.read(), "cp932"

def remove_time_tags(text):
    return re.sub(r"\[.*?\]", "", text)

def change_pitch(input_file, output_file, semitone):
    if semitone == 0 or not -12 <= semitone <= 12: return False
    pitch = 2 ** (semitone / 12)
    cmd = [ "../bin/ffmpeg", "-y",
        "-i", input_file,
        "-c:v", "copy",
        "-af", f"rubberband=pitch={pitch}:formant=preserved",
        output_file, ]
    result = subprocess.run(
        cmd,
        creationflags=subprocess.CREATE_NO_WINDOW,
        capture_output=True,
        text=True )
    return result

def count_audio_tracks(path):
    result = subprocess.run(
        [   "../bin/ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            path ],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    lines = result.stdout.strip().splitlines()
    return len(lines)

def extract_audio(input_path, output_path):
    result = subprocess.run(
        [   "../bin/ffmpeg",
            "-i", input_path,
            "-map", "0:a:1",
            "-c", "copy",
            output_path ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="ignore"))

def get_duration(path):
    result = subprocess.run(
        [   "../bin/ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return float(result.stdout.strip())

def trim_bgv(audf, duration, outf):
    subprocess.run(
        [   "../bin/ffmpeg",
            "-y",
            "-stream_loop", "-1",
            "-i", audf,
            "-t", str(duration),
            "-c", "copy",
            outf],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True
    )

def guess_func(s):
    if not s:
        return ""
    try:
        raw = s.encode("latin1")
    except:
        return s
    enc = chardet.detect(raw).get("encoding")    # エンコーディング推測
    if enc:     
        enc = enc.lower()
        if "utf" in enc:
            try:
                return raw.decode("utf-8")
            except:
                pass
        if "cp932" in enc or "shift_jis" in enc or "sjis" in enc:
            try:
                return raw.decode("cp932")
            except:
                pass
    for e in ("cp932", "utf-8"):
        try:
            return raw.decode(e)
        except:
            pass
    return s

def get_id3_guess(fname):
    title = artist = album = ""
    try:    # --- ID3v2 ---
        tags = ID3(fname)
        if "TIT2" in tags:
            title = guess_func(tags["TIT2"].text[0])
        if "TPE1" in tags:
            artist = guess_func(tags["TPE1"].text[0])
        if "TALB" in tags:
            album = guess_func(tags["TALB"].text[0])
        if title or artist or album:        # v2が取れたらそのまま返す（Perlと同じ）
            return title, artist, album
    except:
        pass
    try:    # --- ID3v1 ---
        audio = MP3(fname)
        if audio.tags:
            title = guess_func(str(audio.tags.get("TIT2", "")))
            artist = guess_func(str(audio.tags.get("TPE1", "")))
            album = guess_func(str(audio.tags.get("TALB", "")))
    except:
        pass
    return title, artist, album

def to_sec(tag):
    m, s, cs = map(int, tag.split(":"))
    return m * 60 + s + cs / 100  # 1/100秒想定

def to_tag(sec,tratio=1,p=":"):
    sec = sec / tratio
    if sec < 0: sec = 0
    m = int(sec // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))  # 1/100秒
    if cs == 100:    # 桁あふれ補正（例: 59.999 → 60.00 になるケース）
        cs = 0
        s += 1
    if s == 60:
        s = 0
        m += 1
    return f"{m:02}:{s:02}{p}{cs:02}"

def normalize(s):
    s = re.sub(r'【.*?】', '', s)
    return s.lower().replace(" ", "").replace("_", "")

def matchbgv(target):
    files = [   f for f in Path(bgvroot).iterdir()
        if f.is_file() and f.suffix.lower() == ".mp4" ]
    best_name = None
    best_score = 0
    for f in files:
        name = normalize(f.stem)
        score = fuzz.token_set_ratio(target, name)
        if score > best_score:
            best_score = score
            best_name = f.name
    return best_name, best_score

def to_cs(tag):
    m, s, cs = map(int, tag.split(":"))
    return (m * 60 + s) * 100 + cs

def txt2ass(mp3f,bgvf,asstmp):
    txtf = str(Path(mp3f).with_suffix(".txt"))
    title, artist, album = get_id3_guess(mp3f)
    assh,enc = read_text("../htdocs/mochi2_header.ass")
    fd = {  m.group(1): m.group(2)
        for line in assh.splitlines()
        if (m := re.match(r";(f\d+)=(.*)", line)) }
    txtl,enc = read_text(txtf)
    tagby = tratio = ""
    for line in txtl.splitlines():
        l = line.lower()
        if l.startswith("@taggingby="):     tagby  = line.split("=", 1)[1].strip()
        elif l.startswith("@timeratio="):   tratio = line.split("=", 1)[1].strip()    
        elif l.startswith("@title="):       title  = line.split("=", 1)[1].strip()    
        elif l.startswith("@artist="):      artist = line.split("=", 1)[1].strip()    
        elif l.startswith("@album="):       album  = line.split("=", 1)[1].strip()
    try:
        tratio = float(tratio)
    except (ValueError, TypeError):
        tratio = 0.9953125              # winamp時間
    assl  = f"{fd.get('f01')}{title}\n"
    assl += f"{fd.get('f02')}{artist}\n"
    assl += f"{fd.get('f03')}{album}\n"
    assl += f"{fd.get('f04')}{bgvf}\n"
    if tagby:
        assl += f"{fd.get('f05')}{tagby}\n"

    # タイムタグテキスト付与
    lines = [line for line in txtl.splitlines()
            if re.search(r"\[\d{2}:\d{2}:\d{2}\]", line)]
    fadeindur  = 3.5                     # フェードインデュレーション   秒
    fadeink = rf"{{\K{round(fadeindur * 100)}}}"
    fadeoutdur = 4.0                     # フェードアウトデュレーション 秒
    linecnt = 0
    mp3dur = get_duration(mp3f)
    for i, line in enumerate(lines):
        tags = re.findall(r"\[(\d{2}:\d{2}:\d{2})\]", line)
        if len(tags) == 1:              # 行タグの場合
            next_line = lines[i+1] if i+1 < len(lines) else None
            if next_line:
                next_tags = re.findall(r"\[(\d{2}:\d{2}:\d{2})\]", next_line)
                ee_sec = to_sec(next_tags[0]) + fadeoutdur if next_tags else to_sec(tags[-1]) + fadeoutdur
            else:
                ee_sec = mp3dur         # 最終行 → mp3の長さを使う
            ss = to_tag(to_sec(tags[0])  - fadeindur,  tratio, '.')
            ee = to_tag(ee_sec, tratio, '.')
            lyc = re.sub(r"\[.*?\]", "", line)
            assl += fd.get(f'f1{linecnt % 4}').replace("ss:ss.ss",ss).replace("ee:ee.ee",ee) + lyc + "\n"
        else:                           # 文字タグ（ワイプ）の場合
            ss = to_tag(to_sec(tags[0]) - fadeindur, tratio, '.')
            ee = to_tag(to_sec(tags[-1]) + fadeoutdur, tratio, '.')
            pairs = re.findall(
                r"\[(\d{2}:\d{2}:\d{2})\]([^\[]*)",
                line
            )
            lyc = fadeink
            for j in range(len(pairs)):
                curr_tag = pairs[j][0]
                text = pairs[j][1]
                if j + 1 < len(pairs):
                    next_tag = pairs[j + 1][0]
                    diff = round(
                        (to_cs(next_tag) - to_cs(curr_tag)) / tratio
                    )
                else:
                    diff = round(fadeoutdur * 100)
                lyc += rf"{{\K{diff}}}" + text
            assl += fd.get(f'f1{linecnt % 4}').replace("ss:ss.ss",ss).replace("ee:ee.ee",ee) + lyc + "\n"
        linecnt += 1
    ass_txt = f"{assh}\n{assl}"
    with open(asstmp, "w", encoding="utf-8") as f:
        f.write(ass_txt)

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
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

# ヘッダ設定
form = cgi.FieldStorage()
if form.getvalue('confirm') == 'y':
    title_txt = f"【楽曲登録中】{extf}"
elif form.getvalue('confirm') == 'ok':
    title_txt = f"【楽曲登完了】{extf}"
else :
    title_txt = f"【楽曲登録確認】{extf}"
print( f'''\
<html><head>
  <title>{title_txt}</title>
  <link rel="icon" href="/favicon.ico">
  <meta http-equiv="Cache-Control" content="no-cache">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
</head><body>
''')
with open(HEADER, "r", encoding="utf-8") as f:
    for line in f:
        if '<!--#include virtual="/cgi-bin/mochi2_bread.py" -->' in line:
            print(f'<span class="mid">{title_txt}</span>')
        else:
            print(line, end="")
print('\n',flush=True)

# チェック
if unquri.startswith("/bgv/"):
    print(f'<pre>背景動画は登録できません\n{unquri}</pre>')
    exit()
if not os.path.exists(fname):
    print(f'<pre>ファイルが見つかりません\n{fname}</pre>')
    exit()

# 動画登録確認
icon_img = sinfo_txt = mp3bgv_txt = offv_txt = pitch_txt = confirm_txt = kashi_txt = ""

# 動画登録中
if form.getvalue('confirm') == 'y':
    print('<center><div class="loader"></div>⏳ 楽曲登録中......<br />',flush=True)
    if form.getvalue('pitch_value') != '0':        # キーピッチ変更
        pitch_value = form.getvalue('pitch_value')
        pitch_v = pitch_value
        if int(pitch_v) > 0:
            pitch_v = f"+{pitch_v}"
        print(f'　🎵 キーピッチを変更します。しばらくお待ちください......{pitch_v}<br />',flush=True)
        ofile = os.path.join("../tmp", os.path.basename(fname))
        r = change_pitch(fname, ofile, int(pitch_value))
        if not r:
            print(f"キーピッチ変更エラー！")
        if r.returncode != 0 :
            print(f"キーピッチ変更エラー！\n")
            print(r.stderr.decode("utf-8", errors="ignore"))
        fname = ofile
    print('</center>')

    if intermission == "ON":        # インターミッション登録
        kashi_txt += f'　🍵 登録曲と曲の間に30秒のインターミッションが入ります\n'
        imrnd = random.randint(1, 4)
        t = int(time.time())
        immp4 = f"../htdocs/intermission30s-0{imrnd}.mp4"
        imass = "../htdocs/intermission30s-01.ass"
        imas2 = f"../tmp/intermission30s-{t}.ass"
        shutil.copy(imass, imas2)
        with open(imas2, "a", encoding="utf-8") as f:
            f.write(f"{urifile}\n")
        p = subprocess.Popen([MPCBEEXE,immp4,'/add','/sub',imas2])
        time.sleep(0.2)

    if extf == 'mp3':                           # mp3
        bgvf = unquote(form.getvalue('bgv'))
        kashi_txt += f'　🖼️ 背景動画を作成します... 背景動画={bgvf}\n'
        mp3dur = get_duration(fname)
        vidf = f"{bgvroot}/{bgvf}"
        outf = f"../tmp/{os.path.splitext(os.path.basename(fname))[0]}.mp4"
        trim_bgv(vidf,mp3dur,outf)
        if os.path.exists(assf):                # mp3 & ass
            p = subprocess.Popen([MPCBEEXE,outf,'/add','/dub',fname,'/sub',assf])
        elif os.path.exists(ssaf):                # mp3 & ass
            p = subprocess.Popen([MPCBEEXE,outf,'/add','/dub',fname,'/sub',ssaf])
        elif os.path.exists(txtf):              # mp3 & txt
            kashi_txt += f'　📝 タイムタグ付きテキストから歌詞ファイルを作成します\n'
            asstmp = f"../tmp/{os.path.splitext(os.path.basename(fname))[0]}.ass"
            txt2ass(fname,bgvf,asstmp)
            time.sleep(0.1)
            p = subprocess.Popen([MPCBEEXE,outf,'/add','/dub',fname,'/sub',asstmp])

    elif form.getvalue('offvocal') == 'on':     # mp4 & offボーカル
        kashi_txt += f'　🔇 オフボーカル(2番目の音声トラック)を登録します\n'
        audf = str(Path(f"../tmp/{urifile}").with_suffix(".m4a"))
        extract_audio(fname,audf)
        if os.path.exists(assf):
            p = subprocess.Popen([MPCBEEXE,fname,'/add','/dub',audf,'/sub',assf])
        elif os.path.exists(ssaf):
            p = subprocess.Popen([MPCBEEXE,fname,'/add','/dub',audf,'/sub',ssaf])
        else:
            p = subprocess.Popen([MPCBEEXE,fname,'/add','/dub',audf])

    else:                                       # mp4 & 通常登録
        if os.path.exists(assf):
            p = subprocess.Popen([MPCBEEXE,fname,'/add','/sub',assf])
        elif os.path.exists(ssaf):
            p = subprocess.Popen([MPCBEEXE,fname,'/add','/sub',ssaf])
        else:
            p = subprocess.Popen([MPCBEEXE,fname,'/add'])
    with open(LSTF, "a", encoding="utf-8") as f:
        f.write(f"{uripath}\n")
    kashi_txt += f'　🚫 登録中はリロードボタンを押さないでください'
    print(f'<meta http-equiv=refresh content=2;URL={uri}?confirm=ok>')

# 動画登録完了
elif form.getvalue('confirm') == 'ok':
    sinfo_txt = "<span class=mid>✅ 楽曲登録しました。</span>"

# 動画登録確認
else:
    sinfo_txt = f'''\
<form action="{uri}" method="get">
<input type="hidden" name="confirm" value="y">
'''
    sinfo_txt += f'ℹ️楽曲情報:[{extf}]'
    ### assある場合
    vidid = ""
    if os.path.exists(ssaf):
        sinfo_txt += f" [ssa]"
    if os.path.exists(assf):
        ass_txt,enc = read_text(assf)
        sinfo_txt += f" [ass({enc})]"
# Title: もちからass自動生成v4
# Title: もちからass自動生成v5 Timeless ver.
# Title: もちからass自動生成v6 AllInAss ver.
# Title: もちからass自動生成v7 LRCLIB ver.
        if "もちからass自動生成v7" in ass_txt:
            sinfo_txt += " <font color=red>[行同期歌詞(New!!)]</font>"
        elif "もちからass自動生成v6" in ass_txt:
            sinfo_txt += " <font color=blue>[スクロール歌詞]</font>"
        elif "もちからass自動生成v5" in ass_txt:
            sinfo_txt += " <font color=blue>[スクロール歌詞]</font>"
        kashi = []
        loopvid = videoid = url_utanet = url_youtube = "" 
        for line in ass_txt.splitlines():
            # 画像できれば読む
            if line.startswith(";vidid"):
                vidid = line.split("=", 1)[1]
                url_youtube = f'https://www.youtube.com/watch?v={vidid}'
            if line.startswith(";utaid"):
                utaid = line.split("=", 1)[1]
                url_utanet = f'https://www.uta-net.com/song/{utaid}/'
            if line.startswith(";loopvid") : loopvid = line.split("=", 1)[1]
            if line.startswith(";videoId") : videoid = line.split("=", 1)[1]
# 歌詞重複行除外処理
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if ( len(parts) >= 10
                    and parts[8] != "LineSync2"
                    and ")\\alpha&H10&\\t(" not in parts[9] ):
                    text = re.sub(r"\{.*?\}", "", parts[9])
                    kashi.append(text)
        if url_utanet:
            sinfo_txt += f'[<a class="link-hover-b" href="{url_utanet}">🎼uta-net</a>] '
        if url_youtube:
            sinfo_txt += f'[<a class="link-hover-b" href="{url_youtube}">▶️youtube</a>] '
        if   loopvid : vidid = loopvid
        elif videoid : vidid = videoid
        kashi_txt = "\n".join(kashi)
    if vidid:
        vidid_url = f'https://i.ytimg.com/vi/{vidid}/mqdefault.jpg'
        icon_img = f'<img class="pl-img" src="{vidid_url}">'
    elif os.path.exists(thumbimgf):
        thumb_url = thumbimgf.split(':/karaoke', 1)[1]
        icon_img = f'<img class="pl-img" src="{quote(thumb_url)}">'
    # リアルタイム作成処理
    elif fname.endswith('.mp4') and len(fname) < 100:
        make_thumbimg(fname,thumbimgf)
        if os.path.exists(thumbimgf):
            thumb_url = thumbimgf.split(':/karaoke', 1)[1]
            icon_img = f'<img class="pl-img" src="{quote(thumb_url)}">'
        else:
            icon_img = f'<img class="pl-img" src="{NOIMG}">'
    else:
        icon_img = f'<img class="pl-img" src="{NOIMG}">'

### txtある場合
    if os.path.exists(txtf):
        sinfo_txt += " [txt]"
        if not kashi_txt:
            text, enc = read_text(txtf)
            kashi_txt = remove_time_tags(text)
    if kashi_txt:
        kashi_txt = f'📝 [歌詞]\n<center>{kashi_txt}</center>'
### mp3の場合
    if extf == 'mp3':
        title, artist, album = get_id3_guess(fname)
        mp3_txt =  f'🎵 [mp3 id3 タグ情報]\n'
        mp3_txt += f'　title: {title}\n　artist: {artist}\n　album: {album}'
        kashi_txt = f'{mp3_txt}\n{kashi_txt}'

    # オフボーカル
    if extf == 'mp4' and track_chg == "ON":
        track_cnt = count_audio_tracks(fname)
        if track_cnt > 1:
            offv_txt =  '<label class="link-hover-b"><input type="checkbox" name="offvocal">'
            offv_txt += '<span class="big">🔇</span>offvocal'
            offv_txt += '<span class="normal"> (2番目の音声トラックを再生)</span></label>'

    # キーピッチ変更(mp4)
    pitch_txt = ""
    if extf == "mp4":
        pitch_txt = f'''\
    🎵 キーピッチ変更：
    <button type="button" onclick="changePitch(-1)">－</button>
    <span id="pitch_display">±0</span>
    <button type="button" onclick="changePitch(1)">＋</button>
    <button type="button" onclick="resetPitch()">リセット</button>
    <input type="hidden" name="pitch_value" id="pitch_value" value="0">
'''

    # mp3背景動画
    if extf == 'mp3':
        p = Path(fname)
        bgvfiles = [ f for f in os.listdir(bgvroot)     # ランダム
            if f.lower().endswith(".mp4") ]
        bgvfile_rnd = random.choice(bgvfiles) if bgvfiles else None
        if form.getvalue('bgvf'):
            bgvfile = unquote(form.getvalue('bgvf'))
        elif form.getvalue('b') == 'rnd':                 # ランダム
            bgvfile = bgvfile_rnd
        else:                                           # デフォルトは関連性(ファイル)
            bgvfile,score = matchbgv(normalize(p.parent.name + p.stem))
        if not bgvfile:
            bgvfile = bgvfile_rnd
        rows = []
        for i, f in enumerate(Path(bgvroot).iterdir()):
            if f.is_file() and f.suffix.lower() == ".mp4":
                rowclass = "pl-main1" if i % 2 == 0 else "pl-main2"
                rows.append(
                    f'<tr class="pl-tr"><td class="{rowclass}"><span class="normal">'
                    f'<a class="link-hover" href="?bgvf={f.name}">{f.name}</a></span>'
                    f'</td></tr>'
                )
        bgvlist = "\n".join(rows)

        mp3bgv_txt = f'''\
<tr class="pl-tr">
    <td rowspan=2 class="pl-no1"><span class="bbig">🎬</span></td>
    <td colspan=2 class="pl-main1"><span class="normal-gray">背景動画選択:</span>
        <button class="btn" type="button" onclick="location.href = location.pathname + \'?b=fname\'">文字列一致</button>
        <button class="btn" type="button" onclick="location.href = location.pathname + \'?b=rnd\'">ランダム</button>
        <button class="btn" type="button" onclick="toggleArea()">ファイル選択</button>
    </td>
</tr>
<tr class="pl-tr">
    <td colspan=2 class="pl-main1">
        <input class="bgv-input" type="input" name="bgv" value="{bgvfile}" size=80 readonly>
    </td>
</tr>
<tr class="pl-tr">
    <td colspan=3 class="pl-main1">
        <div id="fileArea" style="display:none;">
            <table class="pl-table">
{bgvlist}
            </table>
        </div>
    </td>
</tr>
'''
    # アラート表示
    alert = ""
    if extf == "mp3" and not os.path.exists(assf) and not os.path.exists(txtf):
        alert = "⚠️歌詞情報(ass or txt)がないため歌詞が表示されません。"
    elif any( c in ("\u3099", "\u309A") for c in unquri):
        alert = "ℹ️ファイル名に特殊文字(結合文字)を含みます。一部の機能が利用できません。"
    elif "#" in unquri or "&" in unquri or "%" in unquri:
        alert = "ℹ️ファイル名に特殊記号( # & % )を含みます。一部の機能が利用できません。"
    elif unquri.endswith(" .mp4"):
        alert = "ℹ️末尾に半角スペースを含むファイル名です。一部の機能が利用できません。"
    if alert:
        alert = f"<font color=blue><b>{alert}</b></font><br>"

    # 登録してもよろしいですか？
    confirm_txt = f'''\
<center>{alert}
<span class="big">❓</span>
<span class="mid">上記を登録してもよろしいですか？</span><br />
<button class="btn" type="submit">は い</button>　
<button class="btn" type="button" onclick="history.back()">戻 る</button>
</center>
'''

# html print
tr_txt = '<tr class="pl-tr"><td colspan=3'
if offv_txt:
    offv_txt    = f'{tr_txt} class="pl-main1">{offv_txt}</td></tr>'
if pitch_txt:
    pitch_txt   = f'{tr_txt} class="pl-main1">{pitch_txt}</td></tr>'
if confirm_txt:
    confirm_txt = f'{tr_txt} class="pl-main2">{confirm_txt}</td></tr>'
print(f'''\
<table class="pl-table">
    <tr class="pl-tr">
        <td rowspan=2 class="pl-no"><span class=bbig>{emoji(unquri)}</span></td>
        <td class="pl-main0"><div class="pl-smain">{urifolder}</div><div class="mid">{urifile}</div></td>
        <td rowspan=2 class="pl-icon">{icon_img}</td>
    </tr>
    <tr class="pl-tr"><td class="pl-comment">{sinfo_txt}</td></tr>
{mp3bgv_txt}
{offv_txt}
{pitch_txt}
{confirm_txt}
    <tr class="pl-tr"><td colspan=3 class="pre-gray">{kashi_txt}</td></tr>
 </table>
''')

# フッタ
if form.getvalue('confirm') != 'y':
    with open(FOOTER, "r", encoding="utf-8") as f:
        for line in f:
            print(line, end="")
print('</body></html>')
