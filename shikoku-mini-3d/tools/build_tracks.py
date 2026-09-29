#!/usr/bin/env python3
"""線路データから、駅と駅の間の実際の線路形状を作るスクリプト。

  python3 tools/build_tracks.py --n02 N02-24_RailroadSection.geojson   # 国土数値情報 鉄道データ (推奨)
  python3 tools/build_tracks.py                 # OpenStreetMap: Overpass API から取得 (tools/osm_rail.json に保存)
  python3 tools/build_tracks.py osm_rail.json   # 保存済みの OSM データを使う

出力: tools/track_shapes.json
  {路線キー: [[[lon, lat], ...], ...]}   # 駅 i と駅 i+1 の間の中間点 (両端の駅は含まない)

build_network.py は track_shapes.json があれば自動で読み込み、駅間を実際の線形でつなぎます。
経路が見つからない区間や、不自然に遠回りになる区間は空リスト (= 直線のまま) になります。

OSM データのライセンスは ODbL です。生成物を公開するときは
「© OpenStreetMap contributors」の表記が必要です。
"""
import heapq
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_network  # noqa: E402  (路線定義と駅座標の読み込みを共有する)

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "osm_rail.json")
OUT = os.path.join(HERE, "track_shapes.json")
# Overpass API のサーバー (カンマ区切りで複数指定すると、失敗時に順に試す)
OVERPASS = os.environ.get(
    "OVERPASS_URL",
    "https://overpass-api.de/api/interpreter,https://overpass.private.coffee/api/interpreter,"
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter").split(",")
BBOX = (32.6, 132.0, 34.6, 134.9)  # 四国 (南, 西, 北, 東)
TILE = 0.1  # 一度に問い合わせる範囲 [度]。大きいとサーバーが時間切れになる

QUERY = """
[out:json][timeout:90];
(
  way["railway"="rail"]({s},{w},{n},{e});
  way["railway"="light_rail"]({s},{w},{n},{e});
  way["railway"="tram"]({s},{w},{n},{e});
  way["railway"="narrow_gauge"]({s},{w},{n},{e});
);
out body;
>;
out skel qt;
"""
TILE_CACHE = os.path.join(HERE, "osm_tiles")  # 取得済みの範囲 (再実行時は続きから)

SNAP_RADIUS = 350      # 駅から線路へ吸着させる最大距離 [m]
SNAP_CANDIDATES = 3    # 各駅で試す線路上の候補点の数
MAX_DETOUR = 3.0       # 直線距離に対する経路長の上限 (倍)
SIMPLIFY = {"tram": 2.0, "rail": 4.0}  # 形状の間引き許容誤差 [m]


def overpass(query):
    """いずれかのサーバーで query を実行する (各サーバー 2 回まで再試行)。"""
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(2):
        for url in OVERPASS:
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "mini-shikoku-3d/1.0"})
                with urllib.request.urlopen(req, timeout=120) as res:
                    return json.load(res)
            except Exception as e:  # noqa: BLE001  (サーバー側の失敗は次を試す)
                last = e
                print(f"  {url}: {e}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass API に接続できません: {last}")


def needed_tiles():
    """路線 (駅と駅を結ぶ線) が通る範囲だけを取得対象にする。海の上などは問い合わせない。"""
    lines = build_network.build_lines(build_network.load_stations(None))
    tiles = set()
    for line in lines.values():
        pts = [c for _, c in line["stations"]]
        for a, b in zip(pts, pts[1:]):
            steps = max(1, int(meters(a, b) / 1000))
            for k in range(steps + 1):
                lon = a[0] + (b[0] - a[0]) * k / steps
                lat = a[1] + (b[1] - a[1]) * k / steps
                tiles.add((math.floor(lat / TILE), math.floor(lon / TILE)))
    # 線路は駅間の直線から少し外れるので、周囲 1 枠も含める
    return sorted({(i + di, j + dj) for i, j in tiles for di in (-1, 0, 1) for dj in (-1, 0, 1)})


def fetch_osm(path):
    if path and os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    os.makedirs(TILE_CACHE, exist_ok=True)
    tiles = needed_tiles()
    elements = {}
    for n, (i, j) in enumerate(tiles):
        cache = os.path.join(TILE_CACHE, f"{i}_{j}.json")
        if os.path.exists(cache):
            res = json.load(open(cache, encoding="utf-8"))
        else:
            s, w = i * TILE, j * TILE
            print(f"[{n + 1}/{len(tiles)}] querying {s:.2f},{w:.2f}", file=sys.stderr)
            res = overpass(QUERY.format(s=s, w=w, n=s + TILE, e=w + TILE))
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(res, f)
        for el in res["elements"]:
            elements[(el["type"], el["id"])] = el
    osm = {"elements": list(elements.values())}
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(osm, f)
    return osm


def meters(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(lat), (a[1] - b[1]) * 110540)


class RailGraph:
    """OSM の way を、ノードを頂点・区間を辺とするグラフにしたもの。"""

    def __init__(self, osm):
        self.coord = {}
        for el in osm["elements"]:
            if el["type"] == "node":
                self.coord[el["id"]] = (el["lon"], el["lat"])
        self.adj = {}  # node -> [(neighbor, length, railway, is_service, operator)]
        for el in osm["elements"]:
            if el["type"] != "way":
                continue
            tags = el.get("tags", {})
            railway = tags.get("railway")
            service = "service" in tags
            op = tags.get("operator")
            nodes = [n for n in el["nodes"] if n in self.coord]
            for a, b in zip(nodes, nodes[1:]):
                d = meters(self.coord[a], self.coord[b])
                self.adj.setdefault(a, []).append((b, d, railway, service, op))
                self.adj.setdefault(b, []).append((a, d, railway, service, op))
        # 近傍探索用の格子 (約 500m 四方)
        self.grid = {}
        for n in self.adj:
            self.grid.setdefault(self._cell(self.coord[n]), []).append(n)

    @staticmethod
    def _cell(c):
        return (int(c[0] / 0.005), int(c[1] / 0.005))

    @staticmethod
    def cost_factor(kind, edge, operator=None):
        """辺を通るときの距離の倍率。通れない辺は None。
        operator を指定すると、事業者が分かっている辺はその事業者のものだけを通る。"""
        _, _, railway, service, op = edge
        if operator and op and op != operator:
            return None
        rail = railway in ("rail", "light_rail", "narrow_gauge")
        if kind == "tram":
            # 伊予鉄の城北線のように、法律上は鉄道でも路面電車が走る区間がある。
            # 同じ事業者の鉄道線は通れるが、路面電車の線路を優先する
            if railway == "tram":
                factor = 1.0
            elif rail and operator and op == operator:
                factor = 3.0
            else:
                return None
        elif rail:
            factor = 1.0
        else:
            return None
        return factor * (4.0 if service else 1.0)  # 側線・渡り線は避ける

    def nearest(self, c, kind, k=SNAP_CANDIDATES, operator=None):
        cx, cy = self._cell(c)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in self.grid.get((cx + dx, cy + dy), []):
                    if not any(self.cost_factor(kind, e, operator) for e in self.adj[n]):
                        continue
                    d = meters(c, self.coord[n])
                    if d <= SNAP_RADIUS:
                        found.append((d, n))
        found.sort()
        # 同じ線路の隣り合うノードばかりにならないよう、20m 以上離れた候補を選ぶ
        picked = []
        for d, n in found:
            if all(meters(self.coord[n], self.coord[m]) > 20 for _, m in picked):
                picked.append((d, n))
            if len(picked) == k:
                break
        return picked

    def shortest(self, src, dst, kind, limit, operator=None):
        """src から dst までの最短経路 (ノード列)。limit [m] を超えたら打ち切る。"""
        dist = {src: 0.0}
        prev = {}
        heap = [(0.0, src)]
        while heap:
            d, n = heapq.heappop(heap)
            if n == dst:
                path = [n]
                while n in prev:
                    n = prev[n]
                    path.append(n)
                return d, path[::-1]
            if d > dist.get(n, math.inf) or d > limit:
                continue
            for edge in self.adj[n]:
                factor = self.cost_factor(kind, edge, operator)
                if not factor:
                    continue
                m, length = edge[0], edge[1]
                cost = d + length * factor
                if cost < dist.get(m, math.inf):
                    dist[m] = cost
                    prev[m] = n
                    heapq.heappush(heap, (cost, m))
        return None


def simplify(points, tol):
    """Douglas-Peucker 法で形状を間引く (tol はメートル)。"""
    if len(points) < 3:
        return points

    def perp(p, a, b):
        ax, ay = 0.0, 0.0
        lat = math.radians(a[1])
        bx, by = (b[0] - a[0]) * 111320 * math.cos(lat), (b[1] - a[1]) * 110540
        px, py = (p[0] - a[0]) * 111320 * math.cos(lat), (p[1] - a[1]) * 110540
        L = math.hypot(bx - ax, by - ay)
        if L == 0:
            return math.hypot(px, py)
        return abs(bx * py - by * px) / L

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = 0.0, None
        for k in range(i + 1, j):
            d = perp(points[k], points[i], points[j])
            if d > best:
                best, idx = d, k
        if idx is not None and best > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, kp in zip(points, keep) if kp]


def segment_shape(graph, a, b, kind, operator=None):
    """駅 a から駅 b への線路形状 (中間点のみ)。見つからなければ None。"""
    straight = meters(a, b)
    limit = straight * MAX_DETOUR + 1000
    best = None
    for da, na in graph.nearest(a, kind, operator=operator):
        for db, nb in graph.nearest(b, kind, operator=operator):
            res = graph.shortest(na, nb, kind, limit, operator)
            if res is None:
                continue
            cost = res[0] + da + db
            if best is None or cost < best[0]:
                best = (cost, res[1])
    if best is None or best[0] > limit:
        return None
    # 駅の座標そのものを両端に置いて間引き、両端 (駅) を除いた中間点を返す
    pts = [tuple(a)] + [graph.coord[n] for n in best[1]] + [tuple(b)]
    pts = simplify(pts, SIMPLIFY[kind])
    return [[round(x, 6), round(y, 6)] for x, y in pts[1:-1]]


# build_network.py の事業者名 -> 国土数値情報 (N02) の運営会社名
N02_OPERATOR = {"JR四国": "四国旅客鉄道"}


def load_n02(path):
    """国土数値情報「鉄道データ (N02)」の RailroadSection (GeoJSON) を OSM 形式に変換する。
    端点の座標が同じ区間どうしをつなぐ。N02_001 = 21 (軌道) は路面電車、11/12 は鉄道。"""
    data = json.load(open(path, encoding="utf-8"))
    ids, elements = {}, []

    def node(c):
        key = (round(c[0], 7), round(c[1], 7))
        if key not in ids:
            ids[key] = len(ids) + 1
            elements.append({"type": "node", "id": ids[key], "lon": key[0], "lat": key[1]})
        return ids[key]

    for k, f in enumerate(data["features"]):
        p = f["properties"]
        kind = {"11": "rail", "12": "rail", "21": "tram"}.get(p["N02_001"])
        coords = f["geometry"]["coordinates"]
        lon, lat = coords[0]
        if not kind or not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
            continue
        elements.append({"type": "way", "id": k + 1, "nodes": [node(c) for c in coords],
                         "tags": {"railway": kind, "operator": p["N02_004"], "name": p["N02_003"]}})
    return {"elements": elements}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("osm", nargs="?", help="保存済みの OSM データ (JSON)。省略時は Overpass API から取得")
    ap.add_argument("--n02", help="国土数値情報 鉄道データの RailroadSection.geojson を使う")
    args = ap.parse_args()
    osm = load_n02(args.n02) if args.n02 else fetch_osm(args.osm)
    graph = RailGraph(osm)
    print(f"graph: {len(graph.adj)} nodes", file=sys.stderr)
    by_line = build_network.load_stations(None)
    lines = build_network.build_lines(by_line)
    shapes, report = {}, []
    for key, line in lines.items():
        segs = []
        ok = 0
        for (na, ca), (nb, cb) in zip(line["stations"], line["stations"][1:]):
            operator = N02_OPERATOR.get(line["operator"], line["operator"]) if args.n02 else None
            shape = segment_shape(graph, ca, cb, line["kind"], operator)
            if shape is None and operator:
                # 他社の線路を走る区間 (例: 予土線の窪川〜若井は土佐くろしお鉄道) は事業者を問わず探す
                shape = segment_shape(graph, ca, cb, line["kind"])
            if shape is None:
                report.append(f"  {line['name']}: {na} - {nb} は直線のまま")
                segs.append([])
            else:
                ok += 1
                segs.append(shape)
        shapes[key] = segs
        print(f"{line['name']}: {ok}/{len(segs)} 区間", file=sys.stderr)
    # 出典 (build_network.py が地図の出典表記に使う)
    shapes["_source"] = ("国土数値情報（鉄道データ）" if args.n02 else "OpenStreetMap")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(shapes, f, ensure_ascii=False, separators=(",", ":"))
    if report:
        print("経路が見つからなかった区間:", file=sys.stderr)
        print("\n".join(report), file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
