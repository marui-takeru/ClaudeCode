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
JR_LTD = dict(kind="rail", cars=5, carLength=21, width=2.9, height=4.0,
              speed=95, dwell=60, accel=40, group="jr_ltd", color="#FFFFFF")

DAY = [("06:30", "22:30")]


def bands(spec, headway):
    return [(a, b, headway) for a, b in spec]


SUBURBAN = [("05:30", "07:00", 20), ("07:00", "21:30", 15), ("21:30", "23:30", 30)]

SERVICES = [
    # ======== 松山 市内電車 ========
    dict(TRAM, id="iyo1", name="1系統 環状線 右回り", line="iyo_loop", loop=True,
         route=[("iyo_loop", None, None)], bands=bands(DAY, 15)),
    dict(TRAM, id="iyo2", name="2系統 環状線 左回り", line="iyo_loop", loop=True, reverse=True,
         route=[("iyo_loop", None, None)], bands=bands(DAY, 15), offset=7),
    dict(TRAM, id="iyo3", name="3系統 松山市駅前〜道後温泉", line="iyo_shieki", both=True,
         route=[("iyo_shieki", "松山市駅前", "道後温泉")], bands=bands(DAY, 10)),
    dict(TRAM, id="iyo5", name="5系統 JR松山駅前〜道後温泉", line="iyo_ekimae", both=True,
         route=[("iyo_ekimae", "松山駅前", "道後温泉")], bands=bands(DAY, 12), offset=3),
    dict(TRAM, id="iyo6", name="6系統 本町六丁目〜松山市駅前", line="iyo_honmachi", both=True,
         route=[("iyo_honmachi", "本町六丁目", "松山市駅前")], bands=bands(DAY, 30), offset=5),
    dict(TRAM, id="botchan", name="坊っちゃん列車", line="iyo_shieki", both=True,
         color="#6D3B1F", cars=2, carLength=9, height=3.4, speed=12, dwell=30,
         route=[("iyo_shieki", "道後温泉", "松山市駅前")],
         stops=["道後温泉", "大街道", "松山市駅前"],
         departures=["09:30", "11:30", "13:30", "15:30"], departuresReturn=["10:30", "12:30", "14:30", "16:30"],
         note="運行日・時刻は季節により異なります (土日祝中心)"),
    # ======== 松山 郊外電車 ========
    dict(IYO_RAIL, id="takahama", name="高浜線", line="iyo_takahama", both=True,
         route=[("iyo_takahama", "松山市", "高浜")], bands=SUBURBAN),
    dict(IYO_RAIL, id="yokogawara", name="横河原線", line="iyo_yokogawara", both=True,
         route=[("iyo_yokogawara", "松山市", "横河原")], bands=SUBURBAN, offset=5),
    dict(IYO_RAIL, id="gunchu", name="郡中線", line="iyo_gunchu", both=True, cars=2,
         route=[("iyo_gunchu", "松山市", "郡中港")], bands=SUBURBAN, offset=10),
    # ======== JR四国 普通 ========
    dict(JR_LOCAL, id="yosan_takamatsu", name="予讃線 普通", line="jr_yosan", both=True,
         route=[("jr_yosan", "高松", "多度津")], bands=[("05:30", "23:00", 30)]),
    dict(JR_LOCAL, id="yosan_kanonji", name="予讃線 普通", line="jr_yosan", both=True,
         route=[("jr_yosan", "多度津", "伊予西条")], bands=[("05:30", "22:00", 60)], offset=15),
    dict(JR_LOCAL, id="yosan_imabari", name="予讃線 普通", line="jr_yosan", both=True,
         route=[("jr_yosan", "伊予西条", "松山")], bands=[("05:30", "22:30", 60)], offset=25),
    dict(JR_LOCAL, id="yosan_iyoshi", name="予讃線 普通", line="jr_yosan_uchiko", both=True,
         route=[("jr_yosan_uchiko", "松山", "伊予市")], bands=[("05:30", "23:00", 60)], offset=40),
    dict(JR_LOCAL, id="uchiko_local", name="内子線 普通", line="jr_yosan_uchiko", both=True,
         route=[("jr_yosan_uchiko", "松山", "内子")], bands=[("06:00", "21:00", 120)], offset=10),
    dict(JR_LOCAL, id="nagahama_local", name="予讃線 普通 (伊予灘経由)", line="jr_yosan_nagahama", both=True,
         cars=1, route=[("jr_yosan_uchiko", "松山", "向井原"), ("jr_yosan_nagahama", "向井原", "伊予大洲")],
         bands=[("06:00", "20:00", 120)], offset=50),
    dict(JR_LOCAL, id="yosan_uwajima", name="予讃線 普通", line="jr_yosan_uchiko", both=True,
         route=[("jr_yosan_uchiko", "伊予大洲", "宇和島")], bands=[("06:00", "21:30", 90)], offset=20),
    dict(JR_LOCAL, id="dosan_kotohira", name="土讃線 普通", line="jr_dosan", both=True,
         route=[("jr_dosan", "多度津", "琴平")], bands=[("06:00", "22:30", 30)], offset=12),
    dict(JR_LOCAL, id="dosan_ikeda", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "琴平", "阿波池田")], bands=[("06:00", "20:00", 120)], offset=30),
    dict(JR_LOCAL, id="dosan_otoyo", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "阿波池田", "土佐山田")], bands=[("06:00", "20:00", 120)], offset=50),
    dict(JR_LOCAL, id="dosan_kochi", name="土讃線 普通", line="jr_dosan", both=True,
         route=[("jr_dosan", "土佐山田", "伊野")], bands=[("05:30", "23:00", 30)], offset=5),
    dict(JR_LOCAL, id="dosan_susaki", name="土讃線 普通", line="jr_dosan", both=True, cars=1,
         route=[("jr_dosan", "伊野", "窪川")], bands=[("06:00", "21:00", 90)], offset=35),
    dict(JR_LOCAL, id="kotoku_local", name="高徳線 普通", line="jr_kotoku", both=True,
         route=[("jr_kotoku", "高松", "三本松")], bands=[("05:30", "23:00", 60)], offset=20),
    dict(JR_LOCAL, id="kotoku_south", name="高徳線 普通", line="jr_kotoku", both=True, cars=1,
         route=[("jr_kotoku", "三本松", "徳島")], bands=[("06:00", "21:30", 90)], offset=40),
    dict(JR_LOCAL, id="tokushima_local", name="徳島線 普通", line="jr_tokushima", both=True,
         route=[("jr_tokushima", "徳島", "阿波池田")], bands=[("06:00", "21:30", 60)], offset=8),
    dict(JR_LOCAL, id="mugi_local", name="牟岐線 普通", line="jr_mugi", both=True,
         route=[("jr_mugi", "徳島", "阿南")], bands=[("05:30", "23:00", 30)], offset=17),
    dict(JR_LOCAL, id="mugi_south", name="牟岐線 普通", line="jr_mugi", both=True, cars=1,
         route=[("jr_mugi", "阿南", "阿波海南")], bands=[("06:00", "20:00", 120)], offset=45),
    dict(JR_LOCAL, id="naruto_local", name="鳴門線 普通", line="jr_naruto", both=True,
         route=[("jr_kotoku", "徳島", "池谷"), ("jr_naruto", "池谷", "鳴門")],
         bands=[("06:00", "22:30", 60)], offset=28),
    dict(JR_LOCAL, id="yodo_local", name="予土線 普通", line="jr_yodo", both=True, cars=1,
         route=[("jr_yodo", "窪川", "宇和島")], bands=[("06:00", "18:00", 180)], offset=0),
    # ======== JR四国 特急 ========
    dict(JR_LTD, id="ishizuchi", name="特急 しおかぜ・いしづち", line="jr_yosan", both=True,
         route=[("jr_yosan", "高松", "松山")],
         stops=["高松", "坂出", "宇多津", "丸亀", "多度津", "観音寺", "川之江", "伊予三島", "新居浜",
                "伊予西条", "壬生川", "今治", "伊予北条", "松山"],
         bands=[("06:00", "20:30", 60)], color="#FFFFFF"),
    dict(JR_LTD, id="uwakai", name="特急 宇和海", line="jr_yosan_uchiko", both=True,
         route=[("jr_yosan_uchiko", "松山", "宇和島")],
         stops=["松山", "伊予市", "内子", "伊予大洲", "八幡浜", "卯之町", "宇和島"],
         bands=[("05:30", "22:00", 60)], color="#B3E5FC", offset=20),
    dict(JR_LTD, id="nanpu", name="特急 南風", line="jr_dosan", both=True,
         route=[("jr_yosan", "宇多津", "多度津"), ("jr_dosan", "多度津", "高知")],
         stops=["宇多津", "丸亀", "多度津", "善通寺", "琴平", "阿波池田", "大歩危", "土佐山田", "後免", "高知"],
         bands=[("06:30", "20:30", 60)], color="#FFCDD2", offset=10),
    dict(JR_LTD, id="uzushio", name="特急 うずしお", line="jr_kotoku", both=True,
         route=[("jr_kotoku", "高松", "徳島")],
         stops=["高松", "栗林", "屋島", "志度", "三本松", "引田", "板野", "池谷", "勝瑞", "徳島"],
         bands=[("06:00", "22:00", 60)], color="#E1BEE7", offset=30),
    dict(JR_LTD, id="tsurugisan", name="特急 剣山", line="jr_tokushima", both=True, cars=2,
         route=[("jr_tokushima", "徳島", "阿波池田")],
         stops=["徳島", "蔵本", "石井", "鴨島", "阿波川島", "阿波山川", "穴吹", "貞光", "阿波半田", "阿波加茂", "阿波池田"],
         bands=[("07:00", "19:00", 150)], color="#C8E6C9", offset=0),
    dict(JR_LTD, id="ashizuri", name="特急 あしずり", line="jr_dosan", both=True, cars=2,
         route=[("jr_dosan", "高知", "窪川"), ("tkr_nakamura", "窪川", "中村")],
         stops=["高知", "朝倉", "伊野", "日下", "佐川", "須崎", "土佐久礼", "窪川", "土佐佐賀", "土佐入野", "中村"],
         bands=[("06:00", "20:00", 120)], color="#FFE0B2", offset=40),
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
    dict(JR_LOCAL, id="gomen_nahari", name="ごめん・なはり線", line="tkr_asa", both=True, cars=1,
         route=[("tkr_asa", "後免", "奈半利")], bands=[("06:00", "22:00", 60)], offset=15),
    dict(JR_LOCAL, id="tkr_nakamura", name="中村線 普通", line="tkr_nakamura", both=True, cars=1,
         route=[("tkr_nakamura", "窪川", "中村")], bands=[("06:00", "21:00", 120)], offset=70),
    dict(JR_LOCAL, id="tkr_sukumo", name="宿毛線 普通", line="tkr_sukumo", both=True, cars=1,
         route=[("tkr_sukumo", "中村", "宿毛")], bands=[("06:00", "21:00", 120)], offset=20),
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


def build_lines(by_line):
    lines = {}
    for key, ln in LINES.items():
        stations = by_line[ln["ekidata"]]
        lookup = {s[1]: s for s in stations}
        if "seq" in ln:
            seq = [lookup[n] for n in ln["seq"]]
        else:
            seq = order_by_code(stations)
            if ln.get("reverse"):
                seq.reverse()
        lines[key] = dict(ln, key=key, stations=[(s[1], [s[2], s[3]]) for s in seq])
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
        for k in ("bands", "departures", "departuresReturn", "note"):
            if k in sv:
                o[k] = sv[k]
        out.append(o)
    return out


GTFS_FILE = os.path.join(HERE, "gtfs_services.json")


def merge_gtfs(net):
    """import_gtfs.py の出力があれば、指定路線の推計ダイヤを時刻表データで置き換える。"""
    if not os.path.exists(GTFS_FILE):
        return
    g = json.load(open(GTFS_FILE, encoding="utf-8"))
    replaced = set(g.get("replaces", []))
    net["lines"] = [l for l in net["lines"] if l["id"] not in replaced] + g["lines"]
    net["services"] = [s for s in net["services"] if s["line"] not in replaced] + g["services"]
    used = {s["group"] for s in net["services"]} | {l["group"] for l in net["lines"]}
    net["groups"] = [x for x in net["groups"] + g["groups"] if x["id"] in used]
    net["source"] += " / 時刻表: GTFS"
    print(f"merged GTFS: {len(g['services'])} patterns, replaced {sorted(replaced)}", file=sys.stderr)


def main():
    by_line = load_stations(sys.argv[1] if len(sys.argv) > 1 else None)
    lines = build_lines(by_line)
    services = build_services(lines)
    net = dict(
        source="駅座標: 駅データ.jp (via piuccio/open-data-jp-railway-stations)",
        groups=GROUPS,
        lines=[dict(id=k, name=v["name"], operator=v["operator"], group=v["group"], kind=v["kind"],
                    color=v["color"],
                    stations=[[RENAME.get(n, n), c] for n, c in v["stations"]],
                    **({"shape": [c for _, c in v["points"]]} if len(v["points"]) > len(v["stations"]) else {}))
               for k, v in lines.items()],
        services=services,
    )
    merge_gtfs(net)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// 路線・駅・運行パターンのデータ (自動生成)\n")
        f.write("window.NETWORK = ")
        json.dump(net, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"wrote {OUT}: {len(net['lines'])} lines, {len(services)} services", file=sys.stderr)


if __name__ == "__main__":
    main()
