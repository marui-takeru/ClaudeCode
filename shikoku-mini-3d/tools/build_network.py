#!/usr/bin/env python3
"""四国の鉄道ネットワーク定義 (data/network.js) を生成するスクリプト。

駅座標の出典:
  piuccio/open-data-jp-railway-stations (元データ: 駅データ.jp)
  https://github.com/piuccio/open-data-jp-railway-stations

使い方:
  python3 tools/build_network.py                # stations.json を自動ダウンロード
  python3 tools/build_network.py stations.json  # 手元のファイルを使う

線路形状は「駅と駅を直線で結んだ近似」です。実際の線形 (国土数値情報 N02 や
OpenStreetMap) に差し替える場合は、各 line の path を置き換えてください。
運行パターン (運転間隔・運転時間帯・停車駅) は公開時刻表を参考にした概算値であり、
実際のダイヤではありません。
"""
import json
import math
import os
import sys
import urllib.request

SRC_URL = ("https://raw.githubusercontent.com/piuccio/"
           "open-data-jp-railway-stations/master/stations.json")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "network.js")

# 表示名の置き換え (ekidata の名称 -> 利用者に馴染みのある名称)
RENAME = {"松山駅前": "JR松山駅前"}

# --------------------------------------------------------------------------
# 物理路線 (線路) の定義
#   ekidata: 駅データ.jp の路線コード
#   seq:     駅の並び (None の場合は ekidata の駅コード順)
# --------------------------------------------------------------------------
LINES = {
    # ---- 伊予鉄道 市内電車 ----
    "iyo_loop": dict(name="伊予鉄 環状線", operator="伊予鉄道", group="matsuyama_tram",
                     kind="tram", color="#7CB342", ekidata="99808",
                     # 松山市駅前→南堀端→西堀端→…→市役所前→南堀端→松山市駅前
                     seq=["松山市駅前", "南堀端", "西堀端", "大手町", "松山駅前", "宮田町", "古町",
                          "萱町六丁目", "本町六丁目", "木屋町", "高砂町", "清水町", "鉄砲町",
                          "赤十字病院前", "平和通一丁目", "上一万", "警察署前", "勝山町", "大街道",
                          "県庁前", "市役所前", "南堀端", "松山市駅前"]),
    "iyo_shieki": dict(name="伊予鉄 城南線(市駅線)", operator="伊予鉄道", group="matsuyama_tram",
                       kind="tram", color="#F08300", ekidata="99810"),
    "iyo_ekimae": dict(name="伊予鉄 松山駅前線", operator="伊予鉄道", group="matsuyama_tram",
                       kind="tram", color="#E4007F", ekidata="99811"),
    "iyo_honmachi": dict(name="伊予鉄 本町線", operator="伊予鉄道", group="matsuyama_tram",
                         kind="tram", color="#00A0E9", ekidata="99812",
                         seq=["本町六丁目", "本町五丁目", "本町四丁目", "本町三丁目", "本町一丁目",
                              "南堀端", "松山市駅前"]),
    # ---- 伊予鉄道 郊外電車 ----
    "iyo_takahama": dict(name="伊予鉄 高浜線", operator="伊予鉄道", group="matsuyama_rail",
                         kind="rail", color="#FF8F00", ekidata="99806", reverse=True),
    "iyo_yokogawara": dict(name="伊予鉄 横河原線", operator="伊予鉄道", group="matsuyama_rail",
                           kind="rail", color="#FBC02D", ekidata="99807"),
    "iyo_gunchu": dict(name="伊予鉄 郡中線", operator="伊予鉄道", group="matsuyama_rail",
                       kind="rail", color="#EF6C00", ekidata="99805"),
    # ---- JR四国 ----
    "jr_yosan": dict(name="JR予讃線 (高松〜松山)", operator="JR四国", group="jr",
                     kind="rail", color="#1E88E5", ekidata="11806"),
    "jr_yosan_uchiko": dict(name="JR予讃線・内子線 (松山〜宇和島)", operator="JR四国", group="jr",
                            kind="rail", color="#00897B", ekidata="11807",
                            seq=["松山", "市坪", "北伊予", "伊予横田", "鳥ノ木", "伊予市", "向井原",
                                 "伊予大平", "伊予中山", "伊予立川", "内子", "五十崎", "喜多山", "新谷",
                                 "伊予大洲", "西大洲", "伊予平野", "千丈", "八幡浜", "双岩", "伊予石城",
                                 "上宇和", "卯之町", "下宇和", "立間", "伊予吉田", "高光", "北宇和島",
                                 "宇和島"]),
    "jr_yosan_nagahama": dict(name="JR予讃線 (愛ある伊予灘線)", operator="JR四国", group="jr",
                              kind="rail", color="#26C6DA", ekidata="11807",
                              seq=["向井原", "高野川", "伊予上灘", "下灘", "串", "喜多灘", "伊予長浜",
                                   "伊予出石", "伊予白滝", "八多喜", "春賀", "五郎", "伊予大洲"]),
    "jr_dosan": dict(name="JR土讃線", operator="JR四国", group="jr",
                     kind="rail", color="#E53935", ekidata="11801"),
    "jr_kotoku": dict(name="JR高徳線", operator="JR四国", group="jr",
                      kind="rail", color="#8E24AA", ekidata="11802"),
    "jr_tokushima": dict(name="JR徳島線", operator="JR四国", group="jr",
                         kind="rail", color="#43A047", ekidata="11803"),
    "jr_mugi": dict(name="JR牟岐線", operator="JR四国", group="jr",
                    kind="rail", color="#FB8C00", ekidata="11804"),
    # 瀬戸大橋線 (本四備讃線) の四国側。途中駅がなく、駅データ.jp の四国の路線に含まれないので駅を直接指定する
    # (座標は国土数値情報の駅で置き換わる)
    "jr_seto_ohashi": dict(name="JR瀬戸大橋線 (児島〜宇多津)", operator="JR四国", group="jr",
                           kind="rail", color="#0277BD", ekidata=None,
                           manual=[("児島", [133.80769, 34.462815]), ("宇多津", [133.81375, 34.30632])]),
    # マリンライナーは瀬戸大橋から坂出へ直接向かう (宇多津を通らない三角線の一辺)
    "jr_seto_ohashi_sakaide": dict(name="JR瀬戸大橋線 (児島〜坂出)", operator="JR四国", group="jr",
                                   kind="rail", color="#0277BD", ekidata=None,
                                   manual=[("児島", [133.80769, 34.462815]), ("坂出", [133.856785, 34.31319])]),
    "jr_naruto": dict(name="JR鳴門線", operator="JR四国", group="jr",
                      kind="rail", color="#EC407A", ekidata="11805", reverse=True),
    "jr_yodo": dict(name="JR予土線", operator="JR四国", group="jr",
                    kind="rail", color="#6D4C41", ekidata="11808"),
    # ---- 四国のその他の鉄道 ----
    "kotoden_kotohira": dict(name="ことでん 琴平線", operator="高松琴平電気鉄道", group="shikoku_other",
                             kind="rail", color="#F6C400", ekidata="99802"),
    "kotoden_nagao": dict(name="ことでん 長尾線", operator="高松琴平電気鉄道", group="shikoku_other",
                          kind="rail", color="#3AB54A", ekidata="99803"),
    "kotoden_shido": dict(name="ことでん 志度線", operator="高松琴平電気鉄道", group="shikoku_other",
                          kind="rail", color="#E4007F", ekidata="99804"),
    "tosaden_ino": dict(name="とさでん 伊野線", operator="とさでん交通", group="shikoku_other",
                        kind="tram", color="#00873C", ekidata="99818"),
    "tosaden_sanbashi": dict(name="とさでん 桟橋線", operator="とさでん交通", group="shikoku_other",
                             kind="tram", color="#2E7D32", ekidata="99819"),
    "tosaden_gomen": dict(name="とさでん ごめん線", operator="とさでん交通", group="shikoku_other",
                          kind="tram", color="#66BB6A", ekidata="99817"),
    "tkr_asa": dict(name="ごめん・なはり線", operator="土佐くろしお鉄道", group="shikoku_other",
                    kind="rail", color="#0097A7", ekidata="99816"),
    "tkr_nakamura": dict(name="土佐くろしお 中村線", operator="土佐くろしお鉄道", group="shikoku_other",
                         kind="rail", color="#3949AB", ekidata="99814"),
    "tkr_sukumo": dict(name="土佐くろしお 宿毛線", operator="土佐くろしお鉄道", group="shikoku_other",
                       kind="rail", color="#5C6BC0", ekidata="99815"),
    "asa_kaigan": dict(name="阿佐海岸鉄道 (DMV)", operator="阿佐海岸鉄道", group="shikoku_other",
                       kind="rail", color="#D81B60", ekidata="99801"),
}

GROUPS = [
    dict(id="matsuyama_tram", name="松山 市内電車 (伊予鉄)"),
    dict(id="matsuyama_rail", name="松山 郊外電車 (伊予鉄)"),
    dict(id="jr", name="JR四国 普通"),
    dict(id="jr_ltd", name="JR四国 特急"),
    dict(id="shikoku_other", name="四国のその他の鉄道"),
]

# --------------------------------------------------------------------------
# 運行系統の定義
#   route: [(line, 始点, 終点), ...] を連結した経路
#   bands: [(開始時刻, 終了時刻, 運転間隔[分]), ...]  (始発駅の発車時刻)
#   departures: 明示的な発車時刻 (bands の代わり)
#   stops: 停車駅 (省略時は全駅停車)
#   loop: 環状運転 (片方向のみ)
#   both: 上下両方向を運行するか
# --------------------------------------------------------------------------
TRAM = dict(kind="tram", cars=1, carLength=12, width=2.3, height=3.6,
            speed=14, dwell=20, accel=8)
IYO_RAIL = dict(kind="rail", cars=3, carLength=18, width=2.8, height=3.9,
                speed=50, dwell=30, accel=20)
JR_LOCAL = dict(kind="rail", cars=2, carLength=20, width=2.9, height=4.0,
                speed=75, dwell=30, accel=30)
ISHIZUCHI_COLOR = "#D6E8FA"  # 併結したときに見分けられるよう、いしづち の車両はわずかに青みがかった色にする
JR_LTD = dict(kind="rail", cars=5, carLength=21, width=2.9, height=4.0,
              speed=95, dwell=60, accel=40, group="jr_ltd", color="#FFFFFF")

DAY = [("06:30", "22:30")]


def bands(spec, headway):
    return [(a, b, headway) for a, b in spec]


def _hm(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


RUSH = (("06:30", "08:30"), ("16:30", "19:00"))


def spread(n, first, last, peak=2.0, rush=RUSH):
    """first〜last に n 本を並べる。rush の時間帯は peak 倍の密度にする (朝夕の増発の再現)"""
    a, b = _hm(first), _hm(last)
    if n <= 1:
        return [first][:n]
    step = 1
    mins = list(range(a, b + 1, step))
    w = [peak if any(_hm(x) <= m < _hm(y) for x, y in rush) else 1.0 for m in mins]
    cum = [0.0]
    for x in w[:-1]:
        cum.append(cum[-1] + x)
    total = cum[-1]
    out, j = [], 0
    for i in range(n):
        target = total * i / (n - 1)
        while j < len(cum) - 1 and cum[j + 1] <= target:
            j += 1
        out.append(mins[j])
    out = sorted(set(out))
    return [f"{m // 60:02d}:{m % 60:02d}" for m in out]


def clk(*parts):
    """発車時刻のパターン。"HH:MM" はその時刻、(h1, h2, mm) は h1〜h2 時の毎時 mm 分、
    (h1, h2, mm, step) は step 時間おき。公式時刻表を参照して「始発・終発・毎時◯分」を合わせるのに使う"""
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        else:
            h1, h2, mm = p[:3]
            step = p[3] if len(p) > 3 else 1
            out += [f"{h:02d}:{mm:02d}" for h in range(h1, h2 + 1, step)]
    return sorted(out)


def daily(n, first, last, rfirst=None, rlast=None, peak=2.0, nr=None):
    """平日 1 日の本数 n (上りは nr) を、始発・終発の時刻の間に並べた発車時刻。
    本数は「全国鉄道運行本数データ」(区間ごとの平日の本数) に合わせ、時刻は推計"""
    return dict(departures=spread(n, first, last, peak),
                departuresReturn=spread(nr or n, rfirst or first, rlast or last, peak))


SUBURBAN = [("05:30", "07:00", 20), ("07:00", "21:30", 15), ("21:30", "23:30", 30)]

SERVICES = [
    # ======== 松山 市内電車 ========
    dict(TRAM, id="iyo1", name="1系統 環状線 右回り", line="iyo_loop", loop=True,
         route=[("iyo_loop", None, None)], **daily(91, "06:20", "22:30", peak=1.2)),
    dict(TRAM, id="iyo2", name="2系統 環状線 左回り", line="iyo_loop", loop=True, reverse=True,
         route=[("iyo_loop", None, None)], **daily(91, "06:26", "22:36", peak=1.2)),
    dict(TRAM, id="iyo3", name="3系統 松山市駅前〜道後温泉", line="iyo_shieki", both=True,
         route=[("iyo_shieki", "松山市駅前", "道後温泉")], **daily(75, "06:10", "22:20", "06:30", "22:45", peak=1.2)),
    dict(TRAM, id="iyo5", name="5系統 JR松山駅前〜道後温泉", line="iyo_ekimae", both=True,
         route=[("iyo_ekimae", "松山駅前", "道後温泉")], **daily(68, "06:15", "22:15", "06:35", "22:40", peak=1.2)),
    dict(TRAM, id="iyo6", name="6系統 本町六丁目〜松山市駅前", line="iyo_honmachi", both=True,
         route=[("iyo_honmachi", "本町六丁目", "松山市駅前")], **daily(7, "07:10", "19:10", "07:30", "19:30", peak=1.0)),
    dict(TRAM, id="botchan", name="坊っちゃん列車", line="iyo_shieki", both=True,
         color="#6D3B1F", cars=2, carLength=9, height=3.4, speed=12, dwell=30,
         route=[("iyo_shieki", "道後温泉", "松山市駅前")],
         stops=["道後温泉", "大街道", "松山市駅前"],
         departures=["09:30", "11:30", "13:30", "15:30"], departuresReturn=["10:30", "12:30", "14:30", "16:30"],
         note="運行日・時刻は季節により異なります (土日祝中心)"),
    # ======== 松山 郊外電車 ========
    # 伊予鉄の郊外電車は、公表時刻表 (2026-10-16 改正) の運行パターン (始発・終電・時間帯ごとの間隔、
    # 高浜線と横河原線の直通運転) に合わせた推計。個々の発車時刻は再現していない
    dict(IYO_RAIL, id="takahama", name="高浜・横河原線", line="iyo_takahama", both=True,
         route=[("iyo_takahama", "高浜", "松山市"), ("iyo_yokogawara", "松山市", "横河原")],
         bandsByDay={
             "weekday": [("05:50", "06:40", 25), ("06:47", "07:15", 23), ("07:24", "08:50", 13),
                         ("08:58", "20:44", 15), ("21:05", "22:31", 30)],
             "holiday": [("05:50", "07:15", 25), ("07:20", "20:44", 15), ("21:05", "22:31", 30)]},
         bandsByDayReturn={
             "weekday": [("06:08", "06:41", 32), ("06:58", "07:14", 15), ("07:28", "08:43", 12),
                         ("09:05", "20:49", 15), ("21:18", "22:19", 30), ("22:58", "22:59", 1)],
             "holiday": [("06:08", "07:14", 32), ("07:20", "20:49", 15), ("21:18", "22:19", 30),
                         ("22:58", "22:59", 1)]}),
    dict(IYO_RAIL, id="gunchu", name="郡中線", line="iyo_gunchu", both=True, cars=2,
         route=[("iyo_gunchu", "松山市", "郡中港")],
         bandsByDay={"weekday": [("05:56", "06:40", 31), ("06:49", "08:40", 21), ("09:00", "20:31", 15),
                                 ("21:00", "22:31", 30)]},
         bandsByDayReturn={"weekday": [("05:35", "06:16", 40), ("06:37", "08:24", 21), ("08:53", "20:39", 15),
                                       ("21:08", "22:09", 30)]}),
    # ======== JR四国 普通・快速 ========
    # 1 日の本数は、区間ごとの平日の本数 (全国鉄道運行本数データ 2026 年版。普通・快速のみ) に合わせた。
    # 主な駅 (高松・松山・宇和島・高知・徳島・多度津) を出る時刻は、JR四国の駅時刻表を参照して
    # 「始発・終発・毎時◯分」のパターンを合わせた推計 (時刻表そのものは収録していない)。
    # 反対方向など参照していない時刻は、本数を始発〜終発に並べた推計。
    # 両数は車両形式から (7200系 2両・7000系 1両・1000形/1500形 1〜2両 など)、朝夕は増結
    # -- 高松口 (高松発: 琴平行き 毎時25分、快速サンポート 観音寺行き 毎時13分 など)
    dict(JR_LOCAL, id="yosan_kanonji", name="予讃線 普通・快速サンポート", line="jr_yosan", both=True,
         route=[("jr_yosan", "高松", "観音寺")], rushCars=4,
         departures=clk("06:53", "07:40", "09:04", (10, 18, 13), "14:52", "16:52", "17:56", "18:52", "20:13",
                        "21:45", "22:34"),
         departuresReturn=spread(19, "05:20", "22:10")),
    dict(JR_LOCAL, id="takamatsu_kotohira", name="予讃線・土讃線 普通", line="jr_dosan", both=True,
         route=[("jr_yosan", "高松", "多度津"), ("jr_dosan", "多度津", "琴平")], rushCars=4,
         departures=clk("05:42", "06:12", "07:10", "07:55", "08:15", "08:57", (9, 18, 25), "17:58", "19:13",
                        "19:53", "20:25", "21:20", "22:08"),
         departuresReturn=spread(22, "05:30", "22:20")),
    dict(JR_LOCAL, id="yosan_tadotsu", name="予讃線 普通", line="jr_yosan", both=True,
         route=[("jr_yosan", "高松", "多度津")], rushCars=4,
         departures=clk("10:52", "12:52", "15:52", "19:25", "20:52", "23:33"), departuresReturn=spread(4, "06:20", "22:48")),
    dict(JR_LOCAL, id="dosan_kotohira", name="土讃線 普通", line="jr_dosan", both=True,
         route=[("jr_dosan", "多度津", "琴平")], **daily(6, "06:40", "23:03", "06:00", "21:50")),
    dict(JR_LOCAL, id="yosan_tadotsu_kanonji", name="予讃線 普通", line="jr_yosan", both=True, cars=1,
         route=[("jr_yosan", "多度津", "観音寺")], **daily(4, "06:20", "21:00", "05:50", "20:30")),
    dict(JR_LOCAL, id="yosan_kanonji_saijo", name="予讃線 普通", line="jr_yosan", both=True, cars=1,
         route=[("jr_yosan", "観音寺", "伊予西条")], **daily(13, "05:30", "22:10", "05:40", "21:50")),
    # -- 松山口 (松山発の時刻は駅時刻表のパターン。伊予西条・観音寺行きは毎時58分 など)
    #    松山行きは今治を出る時刻で指定 (今治発 10〜19 時の毎時04分ごろ。departuresAt="今治")
    #    松山〜今治は行き違い・特急の通過待ちで実際は約 85 分かかるため、途中駅の停車時間を長くしている
    dict(JR_LOCAL, id="matsuyama_kanonji", name="予讃線 普通", line="jr_yosan", both=True, stopDwell={"伊予北条": 540, "菊間": 480, "大西": 420}, cars=2,
         route=[("jr_yosan", "観音寺", "松山")],
         departures=clk("08:51", "11:04", "14:05", "17:04", "20:08"), departuresAt="今治",
         departuresReturn=clk("05:53", "09:36", "12:58", "15:58", "16:58")),
    dict(JR_LOCAL, id="matsuyama_saijo", name="予讃線 普通", line="jr_yosan", both=True, stopDwell={"伊予北条": 540, "菊間": 480, "大西": 420}, cars=1, rushCars=2,
         route=[("jr_yosan", "伊予西条", "松山")],
         departures=clk("06:33", "06:58", "08:11", "10:04", "12:04", "13:04", "15:04", "16:06", "18:02", "19:04"),
         departuresAt="今治",
         departuresReturn=clk("06:32", "07:48", "08:40", "10:58", "11:58", "13:58", "14:58", "18:10", "19:07", "21:35")),
    dict(JR_LOCAL, id="matsuyama_imabari", name="予讃線 普通", line="jr_yosan", both=True, stopDwell={"伊予北条": 540, "菊間": 480, "大西": 420}, cars=1, rushCars=2,
         route=[("jr_yosan", "今治", "松山")], departures=clk("05:58", "21:45"), departuresReturn=clk("07:23", "20:29")),
    # 今治始発の新居浜行き (朝)
    dict(JR_LOCAL, id="imabari_niihama", name="予讃線 普通", line="jr_yosan", both=True, cars=1,
         route=[("jr_yosan", "新居浜", "今治")], departures=[], departuresReturn=clk("05:50")),
    # 特急 モーニングEXP松山 (新居浜→松山、朝 1 本。今治 6:29 発)
    dict(JR_LTD, id="morning_matsuyama", name="特急 モーニングEXP松山", line="jr_yosan", both=True, cars=3,
         route=[("jr_yosan", "新居浜", "松山")], stops=["新居浜", "伊予西条", "壬生川", "今治", "伊予北条", "松山"],
         departures=clk("06:29"), departuresAt="今治", departuresReturn=[], color=ISHIZUCHI_COLOR),
    dict(JR_LOCAL, id="matsuyama_hojo", name="予讃線 普通", line="jr_yosan", both=True, cars=1, rushCars=2,
         route=[("jr_yosan", "伊予北条", "松山")],
         departures=spread(7, "06:15", "21:40", peak=3.0),
         departuresReturn=clk("11:32", "13:29", "16:31", "17:40", "22:50")),
    # 松山から南 (伊予灘線経由 毎時45分の2時間おき、内子経由 偶数時45分、伊予市行き 毎時19分 など)
    dict(JR_LOCAL, id="yosan_iyoshi", name="予讃線 普通", line="jr_yosan_uchiko", both=True, cars=1, rushCars=2,
         route=[("jr_yosan_uchiko", "松山", "伊予市")],
         departures=clk("07:31", "08:18", "10:19", "15:19", "18:19", "20:19", "22:59"),
         departuresReturn=spread(7, "06:30", "23:20", peak=3.0)),
    dict(JR_LOCAL, id="uchiko_local", name="予讃線 普通 (内子経由)", line="jr_yosan_uchiko", both=True, cars=1,
         route=[("jr_yosan_uchiko", "松山", "伊予大洲")],
         departures=clk("05:23", "06:13", (8, 18, 45, 2)), departuresReturn=spread(7, "05:20", "21:00")),
    # 内子経由で八幡浜まで (松山 20:45 発、八幡浜 6:02 発)
    dict(JR_LOCAL, id="uchiko_yawatahama", name="予讃線 普通 (内子経由)", line="jr_yosan_uchiko", both=True, cars=1,
         route=[("jr_yosan_uchiko", "松山", "八幡浜")], departures=clk("20:45"), departuresReturn=clk("06:02")),
    # 伊予灘線経由 (松山発 毎時45分の2時間おき、八幡浜発 9〜17 時の奇数時44分)
    dict(JR_LOCAL, id="nagahama_local", name="予讃線 普通 (伊予灘線経由)", line="jr_yosan_nagahama", both=True,
         cars=1, route=[("jr_yosan_uchiko", "松山", "向井原"), ("jr_yosan_nagahama", "向井原", "伊予大洲"),
                        ("jr_yosan_uchiko", "伊予大洲", "八幡浜")],
         departures=clk("05:51", "06:56", (9, 19, 45, 2)), departuresReturn=clk("05:42", "07:28", (9, 17, 44, 2))),
    # 八幡浜発の区間列車 (夜の伊予市行き・伊予大洲行き)
    dict(JR_LOCAL, id="yawatahama_iyoshi", name="予讃線 普通", line="jr_yosan_uchiko", both=True, cars=1,
         route=[("jr_yosan_uchiko", "伊予市", "八幡浜")], departures=[], departuresReturn=clk("20:30")),
    dict(JR_LOCAL, id="yawatahama_ozu", name="予讃線 普通", line="jr_yosan_uchiko", both=True, cars=1,
         route=[("jr_yosan_uchiko", "伊予大洲", "八幡浜")], departures=[], departuresReturn=clk("21:26")),
    dict(JR_LOCAL, id="nagahama_ozu", name="予讃線 普通 (伊予灘線経由)", line="jr_yosan_nagahama", both=True,
         cars=1, route=[("jr_yosan_uchiko", "松山", "向井原"), ("jr_yosan_nagahama", "向井原", "伊予大洲")],
         departures=clk("21:45"), departuresReturn=clk("06:20")),
    # 八幡浜〜宇和島 (八幡浜発 宇和島行き 8 本、宇和島発 7 本)
    dict(JR_LOCAL, id="yosan_uwajima", name="予讃線 普通", line="jr_yosan_uchiko", both=True, cars=1,
         route=[("jr_yosan_uchiko", "八幡浜", "宇和島")],
         departures=clk("06:17", "07:12", "08:20", "12:34", "14:34", "16:55", "18:34", "21:00"),
         departuresReturn=clk("06:10", "06:47", "12:11", "14:11", "16:11", "18:11", "20:18")),
    # -- 土讃線 (高知発 西へ: 毎時06分ごろ須崎・窪川・伊野行き。東へ: 毎時45分 土佐山田行き)
    dict(JR_LOCAL, id="dosan_ikeda", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "琴平", "阿波池田")], departures=clk("11:39", "13:58", "15:58", "06:58", "18:43", "08:41"),
         departuresReturn=spread(6, "05:45", "20:00")),
    dict(JR_LOCAL, id="dosan_otoyo", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "阿波池田", "大歩危")], **daily(4, "07:20", "20:10", "06:30", "19:20")),
    dict(JR_LOCAL, id="dosan_sanchu", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "阿波池田", "高知")], departures=spread(4, "06:05", "18:40"),
         departuresReturn=clk("06:00", "12:45", "16:15", "19:10")),
    dict(JR_LOCAL, id="dosan_kochi", name="土讃線 普通", line="jr_dosan", both=True, cars=1, rushCars=2,
         route=[("jr_dosan", "土佐山田", "高知")], departures=spread(19, "05:40", "22:40"),
         departuresReturn=clk("05:41", "06:03", "06:27", "07:02", "07:32", "08:10", (9, 11, 45), (13, 16, 45),
                              "17:49", "18:18", "18:52", "19:36", "20:42", "22:01")),
    dict(JR_LOCAL, id="dosan_ino", name="土讃線 普通", line="jr_dosan", both=True, cars=1, rushCars=2,
         route=[("jr_dosan", "高知", "伊野")],
         departures=clk("07:45", "10:27", "12:27", "15:27", "16:50", "18:36", "21:06", "22:52"),
         departuresReturn=spread(8, "06:10", "21:20")),
    dict(JR_LOCAL, id="dosan_susaki", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "高知", "須崎")],
         departures=clk("06:31", "07:07", "08:25", "09:34", "11:06", "13:06", "14:06", "15:55", "16:27", "18:15",
                        "20:06", "22:06"),
         departuresReturn=spread(13, "05:20", "21:50")),
    dict(JR_LOCAL, id="dosan_kubokawa", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "高知", "窪川")], departures=clk("05:39", "12:06", "15:06", "17:27", "19:06"),
         departuresReturn=spread(5, "05:10", "18:40")),
    # -- 高徳線 (高松発: 引田行き 毎時42分、オレンジタウン行き 偶数時14分。徳島発: 板野行き 毎時26分)
    dict(JR_LOCAL, id="kotoku_orange", name="高徳線 普通", line="jr_kotoku", both=True, cars=1, rushCars=2,
         route=[("jr_kotoku", "高松", "オレンジタウン")],
         departures=clk("07:51", (10, 16, 14, 2), "20:14", "22:50"), departuresReturn=spread(7, "06:20", "22:10", peak=3.0)),
    dict(JR_LOCAL, id="kotoku_sanbonmatsu", name="高徳線 普通", line="jr_kotoku", both=True, cars=1,
         route=[("jr_kotoku", "高松", "三本松")], departures=clk("12:42", "18:42"), departuresReturn=clk("06:30", "13:50")),
    dict(JR_LOCAL, id="kotoku_local", name="高徳線 普通", line="jr_kotoku", both=True, cars=1, rushCars=2,
         route=[("jr_kotoku", "高松", "引田")],
         departures=clk("06:21", "07:17", "08:33", "09:42", "10:42", "13:42", "14:42", "16:42", "18:14", "19:14",
                        "19:42", "21:42"),
         departuresReturn=spread(15, "05:20", "22:20")),
    dict(JR_LOCAL, id="kotoku_through", name="高徳線 普通", line="jr_kotoku", both=True, cars=1,
         route=[("jr_kotoku", "高松", "徳島")], departures=clk("05:39", "06:41", "11:42", "15:42", "17:42", "20:42"),
         departuresReturn=clk("05:51", "06:09", "12:26", "16:26")),
    dict(JR_LOCAL, id="kotoku_south", name="高徳線 普通", line="jr_kotoku", both=True, cars=1,
         route=[("jr_kotoku", "引田", "徳島")], departures=[], departuresReturn=clk("18:26")),
    dict(JR_LOCAL, id="kotoku_itano", name="高徳線 普通", line="jr_kotoku", both=True, cars=1, rushCars=2,
         route=[("jr_kotoku", "板野", "徳島")], departures=spread(10, "05:40", "22:00"),
         departuresReturn=clk("06:45", "08:45", "10:26", "11:26", "14:26", "15:26", "17:26", "19:27", "20:58", "22:26")),
    dict(JR_LOCAL, id="naruto_local", name="鳴門線 普通", line="jr_naruto", both=True, cars=1, rushCars=2,
         route=[("jr_kotoku", "徳島", "池谷"), ("jr_naruto", "池谷", "鳴門")],
         departures=clk("07:30", "08:27", "09:05", (9, 19, 58), "21:26", "22:58"), departuresReturn=spread(17, "05:40", "22:00")),
    # -- 徳島線 (徳島発: 阿波池田行き 毎時22分、穴吹・阿波川島行き 毎時52分)
    dict(JR_LOCAL, id="tokushima_local", name="徳島線 普通", line="jr_tokushima", both=True, cars=1,
         route=[("jr_tokushima", "徳島", "阿波池田")], departures=clk("06:23", "07:35", (9, 16, 22)),
         departuresReturn=spread(11, "05:30", "20:50")),
    dict(JR_LOCAL, id="tokushima_anabuki", name="徳島線 普通", line="jr_tokushima", both=True, cars=1, rushCars=2,
         route=[("jr_tokushima", "徳島", "穴吹")],
         departures=clk("08:12", "09:52", "10:52", "12:52", "13:52", "17:22", "18:22", "19:22", "19:52", "21:52", "22:52"),
         departuresReturn=spread(11, "05:40", "22:00")),
    dict(JR_LOCAL, id="tokushima_kawashima", name="徳島線 普通", line="jr_tokushima", both=True, cars=1, rushCars=2,
         route=[("jr_tokushima", "徳島", "阿波川島")],
         departures=clk("06:54", "11:52", "14:52", "15:52", "16:52", "17:52", "18:52", "20:52"),
         departuresReturn=spread(8, "06:10", "22:40", peak=3.0)),
    # -- 牟岐線 (徳島発: 毎時00分・30分)
    dict(JR_LOCAL, id="mugi_local", name="牟岐線 普通", line="jr_mugi", both=True, cars=1, rushCars=2,
         route=[("jr_mugi", "徳島", "阿南")],
         departures=clk("07:51", "08:24", "10:00", "10:30", "11:00", "12:00", "12:30", "13:00", "14:00", "14:30",
                        "16:00", "17:00", "18:00", "18:30", "19:30", "20:00", "20:30", "22:55"),
         departuresReturn=spread(18, "05:30", "22:30")),
    dict(JR_LOCAL, id="mugi_kuwano", name="牟岐線 普通", line="jr_mugi", both=True, cars=1,
         route=[("jr_mugi", "徳島", "桑野")], departures=clk("07:17", "15:00"), departuresReturn=spread(3, "06:10", "20:10")),
    dict(JR_LOCAL, id="mugi_mugi", name="牟岐線 普通", line="jr_mugi", both=True, cars=1,
         route=[("jr_mugi", "徳島", "牟岐")], departures=clk("06:46", "16:30", "17:30", "19:00", "21:30"),
         departuresReturn=spread(5, "05:40", "18:30")),
    dict(JR_LOCAL, id="mugi_south", name="牟岐線 普通", line="jr_mugi", both=True, cars=1,
         route=[("jr_mugi", "徳島", "阿波海南")], departures=clk("05:45", (9, 15, 30, 2)),
         departuresReturn=spread(5, "05:00", "18:20")),
    dict(JR_LOCAL, id="mugi_kainan", name="牟岐線 普通", line="jr_mugi", both=True, cars=1,
         route=[("jr_mugi", "牟岐", "阿波海南")], **daily(3, "07:40", "21:10", "06:20", "20:00")),
    # -- 予土線 (宇和島発: 江川崎行き 奇数時27分ごろ、窪川行き 4 時間おき)
    dict(JR_LOCAL, id="yodo_local", name="予土線 普通", line="jr_yodo", both=True, cars=1,
         route=[("jr_yodo", "窪川", "宇和島")], departures=spread(4, "06:50", "17:50"),
         departuresReturn=clk("09:34", "13:27", "17:27", "05:10")),
    dict(JR_LOCAL, id="yodo_ekawasaki", name="予土線 普通", line="jr_yodo", both=True, cars=1,
         route=[("jr_yodo", "江川崎", "宇和島")], departures=spread(4, "06:10", "19:20"),
         departuresReturn=clk("05:46", "07:27", "11:27", "15:27", "19:27")),
    # ======== JR四国 特急 ========
    # 始発駅 (または途中駅: departuresAt) の発車時刻は、JR四国の駅時刻表を参照して「始発・終発・毎時◯分」を合わせた推計。
    # 両数は JR四国「列車編成のご案内」から (宇和海 2両・朝夕 3両、うずしお 2両 など)
    # しおかぜ (岡山方面〜松山) と いしづち (高松〜松山) は、宇多津〜松山を 1 本の列車 (5 + 3 両) で走る。
    # 松山行き: しおかぜ が先に宇多津に着き、2 分半後に いしづち が後ろに着いて連結 (併結) してから発車。
    # 岡山・高松行き: 松山からの 8 両が宇多津に着いた時点で切り離し、前 5 両が岡山へ、後ろ 3 両が 2 分後に高松へ。
    # いしづち の発車時刻は、しおかぜ の宇多津の発着時刻から計算する (coupleWith)。
    # 松山行きの宇多津発は、いしづち の高松発 (7:37, 8:45, 9:42, 10:47, 11〜20 時の毎時50分, 22:20) + 23 分
    dict(JR_LTD, id="shiokaze", name="特急 しおかぜ", line="jr_yosan", both=True,
         route=[("jr_seto_ohashi", "児島", "宇多津"), ("jr_yosan", "宇多津", "松山")],
         stops=["児島", "宇多津", "丸亀", "多度津", "観音寺", "川之江", "伊予三島", "新居浜",
                "伊予西条", "壬生川", "今治", "伊予北条", "松山"],
         departures=clk("08:00", "09:08", "10:05", "11:10", (12, 21, 13), "22:43"), departuresAt="宇多津",
         departuresReturn=clk("05:05", "06:13", "07:20", "08:10", (9, 16, 23), "17:37", "18:39"),
         stopDwell={"宇多津": 300}, color="#FFFFFF",
         couple=dict(station="宇多津", cars=3, color=ISHIZUCHI_COLOR, partner="ishizuchi", partnerName="いしづち")),
    dict(JR_LTD, id="ishizuchi", name="特急 いしづち", line="jr_yosan", both=True, cars=3,
         route=[("jr_yosan", "高松", "宇多津")], stops=["高松", "坂出", "宇多津"],
         coupleWith=dict(partner="shiokaze", partnerName="しおかぜ", station="宇多津", lead=150, split=420),
         color=ISHIZUCHI_COLOR),
    # 高松〜松山を単独で走る いしづち (朝の松山行き、夜の高松行き)
    dict(JR_LTD, id="ishizuchi_solo", name="特急 いしづち", line="jr_yosan", both=True, cars=4,
         route=[("jr_yosan", "高松", "松山")],
         stops=["高松", "坂出", "宇多津", "丸亀", "多度津", "観音寺", "川之江", "伊予三島", "新居浜",
                "伊予西条", "壬生川", "今治", "伊予北条", "松山"],
         departures=clk("05:17", "06:00"), departuresReturn=clk("19:32", "20:38"), color=ISHIZUCHI_COLOR),
    dict(JR_LTD, id="ishizuchi_niihama", name="特急 いしづち", line="jr_yosan", both=True, cars=3,
         route=[("jr_yosan", "新居浜", "松山")], stops=["新居浜", "伊予西条", "壬生川", "今治", "伊予北条", "松山"],
         departures=[], departuresReturn=clk("21:49"), color=ISHIZUCHI_COLOR),
    # 快速 マリンライナー (岡山〜高松)。四国側の児島から表示し、瀬戸大橋から坂出へ直接入る。
    # 高松発は日中 毎時10分・40分
    dict(JR_LOCAL, id="marine", name="快速 マリンライナー", line="jr_seto_ohashi_sakaide", both=True, cars=5,
         route=[("jr_seto_ohashi_sakaide", "児島", "坂出"), ("jr_yosan", "坂出", "高松")],
         stops=["児島", "坂出", "高松"], speed=90, dwell=45, color="#29B6F6", rushCars=7,
         departures=spread(37, "05:30", "23:58", peak=1.5),
         departuresReturn=clk("04:35", "05:35", "06:08", "06:46", "07:08", "07:48", "08:22", "08:55", "09:23", "09:52",
                              (10, 20, 10), (10, 19, 40), "20:43", "21:13", "21:43", "22:27")),
    # 宇和海: 松山発 10〜20 時の毎時30分、宇和島発 9〜19 時の毎時46分
    dict(JR_LTD, id="uwakai", name="特急 宇和海", line="jr_yosan_uchiko", both=True,
         route=[("jr_yosan_uchiko", "松山", "宇和島")],
         stops=["松山", "伊予市", "内子", "伊予大洲", "八幡浜", "卯之町", "宇和島"],
         departures=clk("05:48", "06:49", "08:11", "09:07", (10, 20, 30), "22:00"),
         departuresReturn=clk("05:24", "06:37", "07:37", "08:47", (9, 19, 46), "21:25"),
         color="#B3E5FC", cars=2, rushCars=3, speed=80),
    # 南風: 高知行きは多度津発 11〜16 時の毎時47分、岡山行きは高知発 9〜17 時の毎時13分
    dict(JR_LTD, id="nanpu", name="特急 南風", line="jr_dosan", both=True,
         route=[("jr_seto_ohashi", "児島", "宇多津"), ("jr_yosan", "宇多津", "多度津"), ("jr_dosan", "多度津", "高知")],
         stops=["児島", "宇多津", "丸亀", "多度津", "善通寺", "琴平", "阿波池田", "大歩危", "土佐山田", "後免", "高知"],
         departures=clk("07:56", "09:44", "10:48", (11, 16, 47), "17:55", "18:51", "19:51", "20:59", "22:23"),
         departuresAt="多度津",
         departuresReturn=clk("06:00", "07:00", "08:01", (9, 17, 13), "18:38", "19:31"),
         color="#FFCDD2", cars=3, speed=84),
    dict(JR_LTD, id="shimanto", name="特急 しまんと", line="jr_dosan", both=True, cars=2,
         route=[("jr_yosan", "高松", "多度津"), ("jr_dosan", "多度津", "高知")],
         stops=["高松", "坂出", "宇多津", "丸亀", "多度津", "善通寺", "琴平", "阿波池田", "大歩危", "土佐山田", "後免", "高知"],
         departures=clk("06:04", "08:25"), departuresReturn=clk("04:51", "20:32"), color="#FFCDD2"),
    # うずしお: 高松発 9〜20 時の毎時10分、徳島発 9〜19 時の毎時24分
    dict(JR_LTD, id="uzushio", name="特急 うずしお", line="jr_kotoku", both=True,
         route=[("jr_kotoku", "高松", "徳島")],
         stops=["高松", "栗林", "屋島", "志度", "三本松", "引田", "板野", "池谷", "勝瑞", "徳島"],
         departures=clk("06:10", "07:05", "08:24", (9, 20, 10), "21:14", "22:22"),
         departuresReturn=clk("05:41", "06:58", "08:24", (9, 19, 24), "20:27"),
         color="#E1BEE7", cars=2),
    dict(JR_LTD, id="tsurugisan", name="特急 剣山", line="jr_tokushima", both=True, cars=2,
         route=[("jr_tokushima", "徳島", "阿波池田")],
         stops=["徳島", "蔵本", "石井", "鴨島", "阿波川島", "阿波山川", "穴吹", "貞光", "阿波半田", "阿波加茂", "阿波池田"],
         departures=clk("09:00", "12:00", "18:00", "20:17"), departuresReturn=spread(4, "06:40", "16:40"),
         color="#C8E6C9"),
    # あしずり: 高知発 (しまんと1号の続きを含む)
    dict(JR_LTD, id="ashizuri", name="特急 あしずり", line="jr_dosan", both=True, cars=2,
         route=[("jr_dosan", "高知", "窪川"), ("tkr_nakamura", "窪川", "中村")],
         stops=["高知", "朝倉", "伊野", "日下", "佐川", "須崎", "土佐久礼", "窪川", "土佐佐賀", "土佐入野", "中村"],
         departures=clk("08:20", "09:51", "11:49", "13:49", "15:49", "17:11", "19:01", "21:18"),
         departuresReturn=spread(8, "05:50", "19:30"), color="#FFE0B2"),
    # ======== 四国のその他の鉄道 ========
    dict(IYO_RAIL, id="kotoden_kotohira", name="ことでん 琴平線", line="kotoden_kotohira", both=True, cars=2,
         route=[("kotoden_kotohira", "高松築港", "琴電琴平")], bands=[("06:00", "23:00", 15)]),
    dict(IYO_RAIL, id="kotoden_nagao", name="ことでん 長尾線", line="kotoden_nagao", both=True, cars=2,
         route=[("kotoden_nagao", "高松築港", "長尾")], bands=[("06:00", "23:00", 20)], offset=7),
    dict(IYO_RAIL, id="kotoden_shido", name="ことでん 志度線", line="kotoden_shido", both=True, cars=2,
         route=[("kotoden_shido", "瓦町", "琴電志度")], bands=[("06:00", "23:00", 20)], offset=3),
    dict(TRAM, id="tosaden_sanbashi", name="とさでん 桟橋線", line="tosaden_sanbashi", both=True,
         route=[("tosaden_sanbashi", "高知駅前", "桟橋通五丁目")], bands=bands(DAY, 10)),
    dict(TRAM, id="tosaden_east", name="とさでん 後免町〜鏡川橋", line="tosaden_gomen", both=True,
         route=[("tosaden_gomen", "後免町", "はりまや橋"), ("tosaden_ino", "はりまや橋", "鏡川橋")],
         bands=bands(DAY, 12), offset=4),
    dict(TRAM, id="tosaden_ino", name="とさでん 伊野線", line="tosaden_ino", both=True,
         route=[("tosaden_ino", "はりまや橋", "伊野")], bands=bands(DAY, 30), offset=9),
    # ごめん・なはり線 (高知発 奈半利行き 9〜16 時の毎時15分。JR四国 高知駅の時刻表を参照。土休日だけの列車は除く)
    dict(JR_LOCAL, id="gomen_nahari", name="ごめん・なはり線", line="tkr_asa", both=True, cars=1, rushCars=2,
         route=[("jr_dosan", "高知", "後免"), ("tkr_asa", "後免", "奈半利")],
         departures=clk((9, 16, 15), "17:29", "20:15", "21:25"), departuresReturn=spread(12, "05:10", "21:20")),
    dict(JR_LOCAL, id="gomen_nahari_g", name="ごめん・なはり線", line="tkr_asa", both=True, cars=1,
         route=[("tkr_asa", "後免", "奈半利")], **daily(8, "06:10", "23:00", "06:00", "22:20")),
    dict(JR_LOCAL, id="gomen_aki", name="ごめん・なはり線", line="tkr_asa", both=True, cars=1,
         route=[("jr_dosan", "高知", "後免"), ("tkr_asa", "後免", "安芸")], departures=clk("19:47", "22:36"),
         departuresReturn=spread(3, "06:50", "18:40")),
    dict(JR_LOCAL, id="gomen_aki_g", name="ごめん・なはり線", line="tkr_asa", both=True, cars=1,
         route=[("tkr_asa", "後免", "安芸")], **daily(3, "08:10", "21:40", "07:10", "20:30")),
    dict(JR_LOCAL, id="tkr_nakamura", name="中村線 普通", line="tkr_nakamura", both=True, cars=1,
         route=[("tkr_nakamura", "窪川", "中村")], **daily(9, "06:10", "21:50", "05:30", "21:00")),
    dict(JR_LOCAL, id="tkr_sukumo", name="宿毛線 普通", line="tkr_sukumo", both=True, cars=1,
         route=[("tkr_sukumo", "中村", "宿毛")], **daily(13, "05:40", "22:30", "05:20", "22:00")),
    dict(JR_LOCAL, id="dmv", name="阿佐海岸鉄道 DMV", line="asa_kaigan", both=True, cars=1, carLength=9,
         speed=40, route=[("asa_kaigan", "海部", "甲浦")], bands=[("08:00", "17:00", 120)]),
]


def dist_km(a, b):
    return math.hypot((a[1] - b[1]) * 111.0,
                      (a[0] - b[0]) * 111.0 * math.cos(math.radians((a[1] + b[1]) / 2)))


def load_stations(path):
    if path is None:
        path = os.path.join(HERE, "stations.json")
        if not os.path.exists(path):
            print("downloading", SRC_URL, file=sys.stderr)
            urllib.request.urlretrieve(SRC_URL, path)
    data = json.load(open(path, encoding="utf-8"))
    by_line = {}
    for group in data:
        for st in group["stations"]:
            by_line.setdefault(st["ekidata_line_id"], []).append(
                (st["ekidata_id"], st["name_kanji"], round(st["lon"], 6), round(st["lat"], 6)))
    return by_line


def order_by_code(stations):
    """駅コード順に並べ、後から追加された駅 (コードが末尾) は最も近い区間に挿入する。"""
    ordered = sorted(stations)
    fixed = list(ordered)
    while len(fixed) > 2 and dist_km(fixed[-1][2:], fixed[-2][2:]) > 10:
        st = fixed.pop()
        best, best_i = None, None
        for i in range(len(fixed) - 1):
            a, b = fixed[i][2:], fixed[i + 1][2:]
            cost = dist_km(a, st[2:]) + dist_km(st[2:], b) - dist_km(a, b)
            if best is None or cost < best:
                best, best_i = cost, i + 1
        fixed.insert(best_i, st)
    return fixed


N02_STATIONS = os.path.join(HERE, "n02_stations.json")
N02_OPERATOR = {"JR四国": "四国旅客鉄道"}
# 駅データ.jp と国土数値情報で名前の違う駅
N02_ALIAS = {"松山市駅前": "松山市駅", "松山駅前": "JR松山駅前", "綾川（イオンモール綾川）": "綾川", "西ケ方": "西ヶ方"}


def n02_coords(lines):
    """駅の座標を国土数値情報 (N02) の駅の位置に置き換える。見つからない駅はそのまま。"""
    if not os.path.exists(N02_STATIONS):
        return 0, []
    table = {}
    for op, _line, name, lon, lat in json.load(open(N02_STATIONS, encoding="utf-8")):
        table.setdefault((op, name), []).append([lon, lat])
        table.setdefault((None, name), []).append([lon, lat])
    replaced, missing = 0, []
    for line in lines.values():
        op = N02_OPERATOR.get(line["operator"], line["operator"])
        new = []
        for name, c in line["stations"]:
            n02name = N02_ALIAS.get(name, name)
            # 同じ事業者の同名駅を優先し、無ければ他社の同名駅 (例: 他社線に乗り入れる区間の駅)
            cands = table.get((op, n02name)) or table.get((None, n02name)) or []
            best = min(cands, key=lambda x: dist_km(x, c), default=None)
            if best is not None and dist_km(best, c) < 1.0:
                new.append((name, best))
                replaced += 1
            else:
                new.append((name, c))
                missing.append(f"{line['name']} {name}")
        line["stations"] = new
    return replaced, missing


def build_lines(by_line):
    lines = {}
    for key, ln in LINES.items():
        if ln.get("manual"):
            lines[key] = dict(ln, key=key, stations=[(n, list(c)) for n, c in ln["manual"]])
            continue
        stations = by_line[ln["ekidata"]]
        lookup = {s[1]: s for s in stations}
        if "seq" in ln:
            seq = [lookup[n] for n in ln["seq"]]
        else:
            seq = order_by_code(stations)
            if ln.get("reverse"):
                seq.reverse()
        lines[key] = dict(ln, key=key, stations=[(s[1], [s[2], s[3]]) for s in seq])
    replaced, missing = n02_coords(lines)
    if replaced:
        print(f"station coords from N02: {replaced} replaced, {len(missing)} kept {missing[:5]}", file=sys.stderr)
    shapes = load_shapes()
    for line in lines.values():
        line["points"] = expand_line(line, shapes)
    return lines


SHAPES_FILE = os.path.join(HERE, "track_shapes.json")


def load_shapes():
    """build_tracks.py が作った駅間の線路形状 (無ければ空)。"""
    if not os.path.exists(SHAPES_FILE):
        return {}
    return json.load(open(SHAPES_FILE, encoding="utf-8"))


def expand_line(line, shapes):
    """駅の並びに、駅間の線路形状の中間点 (名前 None) を差し込んだ点列。"""
    segs = shapes.get(line["key"])
    if not segs or len(segs) != len(line["stations"]) - 1:
        return [(n, c) for n, c in line["stations"]]
    out = []
    for i, (n, c) in enumerate(line["stations"]):
        out.append((n, c))
        if i < len(segs):
            out.extend((None, p) for p in segs[i])
    return out


def slice_line(line, a, b):
    pts = line["points"]
    if a is None:
        return list(pts)
    # 駅名は路線内で一意 (環状線のように同じ駅を 2 度通る路線は a=None で使う)
    idx = {n: k for k, (n, _) in enumerate(pts) if n is not None}
    i, j = idx[a], idx[b]
    if i <= j:
        return pts[i:j + 1]
    return list(reversed(pts[j:i + 1]))


def build_services(lines):
    out = []
    for sv in SERVICES:
        path = []
        for (lk, a, b) in sv["route"]:
            part = slice_line(lines[lk], a, b)
            if path and part[0][0] is not None and path[-1][0] == part[0][0]:
                part = part[1:]
            path.extend(part)
        if sv.get("reverse"):
            path.reverse()
        stops = set(sv.get("stops") or [p[0] for p in path if p[0] is not None])
        missing = stops - {p[0] for p in path}
        if missing:
            raise SystemExit(f"{sv['id']}: stops not on route: {missing}")
        line = lines[sv["line"]]
        o = dict(
            id=sv["id"], name=sv["name"], group=sv.get("group", line["group"]),
            line=sv["line"], color=sv.get("color", line["color"]), kind=sv["kind"],
            cars=sv["cars"], carLength=sv["carLength"], width=sv["width"], height=sv["height"],
            speed=sv["speed"], dwell=sv["dwell"], accel=sv["accel"],
            loop=bool(sv.get("loop")), both=bool(sv.get("both")), offset=sv.get("offset", 0),
            path=[[RENAME.get(n, n) if n else "", c, 1 if n in stops else 0] for n, c in path],
        )
        for k in ("bands", "bandsByDay", "bandsByDayReturn", "departures", "departuresReturn", "note",
                  "stopDwell", "couple", "coupleWith", "rushCars", "departuresAt", "departuresReturnAt"):
            if k in sv:
                o[k] = sv[k]
        out.append(o)
    return out


GTFS_DIR = os.path.join(HERE, "gtfs")
EXTRA_DIR = os.path.join(HERE, "extra")  # build_ferries.py などが作る追加の路線


def merge_gtfs(net):
    """import_gtfs.py の出力 (tools/gtfs/*.json) を取り込み、指定路線の推計ダイヤを置き換える。"""
    files = [os.path.join(d, n) for d in (GTFS_DIR, EXTRA_DIR) if os.path.isdir(d)
             for n in sorted(os.listdir(d)) if n.endswith(".json")]
    if not files:
        return
    holidays, credits = set(), []
    for path in files:
        name = os.path.basename(path)
        g = json.load(open(path, encoding="utf-8"))
        replaced = set(g.get("replaces", []))
        net["lines"] = [l for l in net["lines"] if l["id"] not in replaced] + g["lines"]
        net["services"] = [s for s in net["services"] if s["line"] not in replaced] + g["services"]
        known = {x["id"] for x in net["groups"]}
        net["groups"] += [x for x in g["groups"] if x["id"] not in known]
        holidays.update(g.get("holidays", []))
        if g.get("airports"):
            net.setdefault("airports", []).extend(g["airports"])
        if g.get("credit"):
            credits.append(g["credit"])
        print(f"merged {name}: {len(g['services'])} patterns, replaced {sorted(replaced)}", file=sys.stderr)
    used = {s["group"] for s in net["services"]} | {l["group"] for l in net["lines"]}
    net["groups"] = [x for x in net["groups"] if x["id"] in used]
    net["calendar"] = {"holidays": sorted(holidays)}
    net["credits"] = credits


def main():
    by_line = load_stations(sys.argv[1] if len(sys.argv) > 1 else None)
    lines = build_lines(by_line)
    services = build_services(lines)
    net = dict(
        source=("駅座標: 国土数値情報（鉄道データ）、駅の並び: 駅データ.jp" if os.path.exists(N02_STATIONS)
                else "駅座標: 駅データ.jp (via piuccio/open-data-jp-railway-stations)"),
        groups=GROUPS,
        lines=[dict(id=k, name=v["name"], operator=v["operator"], group=v["group"], kind=v["kind"],
                    color=v["color"],
                    stations=[[RENAME.get(n, n), c] for n, c in v["stations"]],
                    **({"shape": [c for _, c in v["points"]]} if len(v["points"]) > len(v["stations"]) else {}))
               for k, v in lines.items()],
        services=services,
    )
    merge_gtfs(net)
    net["trackSource"] = load_shapes().get("_source")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// 路線・駅・運行パターンのデータ (自動生成)\n")
        f.write("window.NETWORK = ")
        json.dump(net, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"wrote {OUT}: {len(net['lines'])} lines, {len(net['services'])} services", file=sys.stderr)


if __name__ == "__main__":
    main()
