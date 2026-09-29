#!/usr/bin/env python3
"""四国に発着する主な旅客船・フェリーの航路と運航パターンを作るスクリプト。

  python3 tools/build_ferries.py            # tools/osm_ferry.json が無ければ Overpass API から取得

出力: tools/extra/ferries.json   (build_network.py が自動で取り込む)

- 航路の形: OpenStreetMap の route=ferry (© OpenStreetMap contributors, ODbL)
- 運航パターン (便数・運航時間帯・所要時間): 各社の公表情報を参考にした**推計**。実際の時刻ではない
"""
import json
import math
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "osm_ferry.json")
OUT_DIR = os.path.join(HERE, "extra")
OVERPASS = os.environ.get(
    "OVERPASS_URL",
    "https://overpass-api.de/api/interpreter,https://overpass.private.coffee/api/interpreter,"
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter").split(",")
QUERY = '[out:json][timeout:120];way["route"="ferry"](32.7,131.6,34.8,135.3);out geom;'

# 船の大きさ (見た目) と基本の速さ
SHIP = {
    "fast": dict(cars=1, carLength=32, width=8, height=7, dwell=300, accel=60),    # 高速船
    "ferry": dict(cars=1, carLength=70, width=14, height=12, dwell=600, accel=120),  # 中型フェリー
    "large": dict(cars=1, carLength=180, width=27, height=22, dwell=1800, accel=300),  # 長距離フェリー
}

# 航路: OSM の way (つなげる順不同)、寄港地 (名前と、おおよその位置 = 緯度, 経度)、運航パターン
FERRIES = [
    dict(id="ferry_sj", name="スーパージェット（高速船）", operator="石崎汽船・瀬戸内海汽船", ship="fast",
         ways=[47907712, 1002003207], speed=60,
         ports=[("松山観光港", (33.889, 132.704)), ("呉港", (34.240, 132.555)), ("広島港（宇品）", (34.351, 132.455))],
         bands=[("07:00", "20:40", 70)]),
    dict(id="ferry_cf", name="クルーズフェリー", operator="石崎汽船・瀬戸内海汽船", ship="ferry",
         ways=[1002003222, 1002003221], speed=26,
         ports=[("松山観光港", (33.889, 132.705)), ("呉港", (34.240, 132.556)), ("広島港（宇品）", (34.351, 132.458))],
         bands=[("05:40", "20:00", 100)]),
    dict(id="ferry_boyo", name="防予フェリー", operator="防予フェリー", ship="ferry",
         ways=[439841626], speed=25,
         ports=[("三津浜港", (33.866, 132.709)), ("柳井港", (33.957, 132.133))],
         bands=[("01:00", "22:00", 160)]),
    dict(id="ferry_94", name="国道九四フェリー", operator="国道九四フェリー", ship="ferry",
         ways=[79686419], speed=30,
         ports=[("三崎港", (33.390, 132.117)), ("佐賀関港", (33.250, 131.865))],
         bands=[("00:30", "23:40", 90)]),
    dict(id="ferry_orange", name="オレンジフェリー（東予〜大阪南港）", operator="四国開発フェリー", ship="large",
         ways=[1141572801], speed=30,
         ports=[("東予港", (33.929, 133.118)), ("大阪南港", (34.620, 135.431))],
         departures=["22:00"], departuresReturn=["22:00"]),
    dict(id="ferry_jumbo", name="ジャンボフェリー（高松〜神戸）", operator="ジャンボフェリー", ship="large",
         ways=[550415132], speed=29,
         ports=[("高松東港", (34.354, 134.074)), ("神戸三宮", (34.683, 135.198))],
         bands=[("01:00", "20:00", 300)]),
    dict(id="ferry_tonosho", name="高松〜土庄（小豆島）", operator="四国フェリー・国際両備フェリー", ship="ferry",
         ways=[185758141], speed=22,
         ports=[("高松港", (34.354, 134.049)), ("土庄港", (34.489, 134.173))],
         bands=[("06:25", "20:30", 60)]),
    dict(id="ferry_ikeda", name="高松〜池田（小豆島）", operator="国際フェリー", ship="ferry",
         ways=[185758149], speed=22,
         ports=[("高松港", (34.354, 134.048)), ("池田港", (34.479, 134.226))],
         bands=[("06:40", "19:40", 120)]),
    dict(id="ferry_naoshima", name="高松〜直島（宮浦）", operator="四国汽船", ship="ferry",
         ways=[185758159], speed=20,
         ports=[("高松港", (34.354, 134.048)), ("宮浦港（直島）", (34.457, 133.974))],
         bands=[("08:10", "18:20", 150)]),
    dict(id="ferry_megi", name="めおん（高松〜女木島〜男木島）", operator="雌雄島海運", ship="fast",
         ways=[139321984, 139321986, 139321985], speed=16,
         ports=[("高松港", (34.353, 134.050)), ("女木島", (34.388, 134.053)), ("男木島", (34.422, 134.054))],
         bands=[("08:00", "18:10", 120)]),
]

GROUP = dict(id="ferry", name="フェリー・旅客船")
COLOR = "#e8eef5"


def meters(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(lat), (a[1] - b[1]) * 110540)


def fetch():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    for url in OVERPASS:
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "mini-shikoku-3d/1.0"})
            with urllib.request.urlopen(req, timeout=200) as res:
                osm = json.load(res)
            json.dump(osm, open(CACHE, "w", encoding="utf-8"))
            return osm
        except Exception as e:  # noqa: BLE001
            print(f"  {url}: {e}", file=sys.stderr)
    raise SystemExit("Overpass API に接続できません")


def chain(ways, start):
    """複数の way を端点でつないで 1 本の点列にする (start に近い端から)。"""
    segs = [[(p["lon"], p["lat"]) for p in w["geometry"]] for w in ways]
    cur = start
    out = []
    while segs:
        # いまの位置に最も近い端をもつ way を選び、向きをそろえる
        best = min(((min(meters(cur, s[0]), meters(cur, s[-1])), i) for i, s in enumerate(segs)))
        s = segs.pop(best[1])
        if meters(cur, s[-1]) < meters(cur, s[0]):
            s = s[::-1]
        out.extend(s if not out else s[1:])
        cur = out[-1]
    return out


def build():
    osm = fetch()
    by_id = {e["id"]: e for e in osm["elements"] if e["type"] == "way"}
    lines, services = [], []
    for f in FERRIES:
        start = (f["ports"][0][1][1], f["ports"][0][1][0])
        pts = chain([by_id[i] for i in f["ways"]], start)
        # 寄港地を点列上の最も近い点に対応づけ、その前後で区切る
        idx = []
        for name, (lat, lon) in f["ports"]:
            k = min(range(len(pts)), key=lambda i: meters(pts[i], (lon, lat)))
            idx.append(k)
        if idx != sorted(idx):
            raise SystemExit(f"{f['id']}: 寄港地の順序が航路と合いません {idx}")
        path = []
        for n, (name, _) in enumerate(f["ports"]):
            path.append([name, [round(pts[idx[n]][0], 6), round(pts[idx[n]][1], 6)], 1])
            if n + 1 < len(idx):
                path.extend(["", [round(x, 6), round(y, 6)], 0] for x, y in pts[idx[n] + 1:idx[n + 1]])
        ship = SHIP[f["ship"]]
        lines.append(dict(id=f["id"], name=f["name"], operator=f["operator"], group=GROUP["id"], kind="ship",
                          color=COLOR, stations=[[p[0], p[1]] for p in path if p[2]],
                          shape=[p[1] for p in path]))
        svc = dict(ship, id=f["id"], name=f["name"], group=GROUP["id"], line=f["id"], color=COLOR,
                   kind="ship", speed=f["speed"], loop=False, both=True, offset=0, path=path,
                   note="運航パターンは推計")
        for k in ("bands", "departures", "departuresReturn"):
            if k in f:
                svc[k] = f[k]
        services.append(svc)
        km = sum(meters(a[1], b[1]) for a, b in zip(path, path[1:])) / 1000
        print(f"{f['name']}: {km:.1f} km, {len(path)} 点", file=sys.stderr)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = dict(groups=[GROUP], replaces=[], lines=lines, services=services,
               credit=None, note="航路の形: © OpenStreetMap contributors")
    with open(os.path.join(OUT_DIR, "ferries.json"), "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    build()
