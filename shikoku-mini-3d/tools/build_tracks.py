#!/usr/bin/env python3
"""OpenStreetMap の線路データから、駅と駅の間の実際の線路形状を作るスクリプト。

  python3 tools/build_tracks.py                 # Overpass API から取得 (結果は tools/osm_rail.json に保存)
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
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_network  # noqa: E402  (路線定義と駅座標の読み込みを共有する)

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "osm_rail.json")
OUT = os.path.join(HERE, "track_shapes.json")
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = (32.6, 132.0, 34.6, 134.9)  # 四国 (南, 西, 北, 東)

QUERY = f"""
[out:json][timeout:300];
way["railway"~"^(rail|light_rail|tram|narrow_gauge)$"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
out body;
>;
out skel qt;
"""

SNAP_RADIUS = 350      # 駅から線路へ吸着させる最大距離 [m]
SNAP_CANDIDATES = 3    # 各駅で試す線路上の候補点の数
MAX_DETOUR = 3.0       # 直線距離に対する経路長の上限 (倍)
SIMPLIFY = {"tram": 2.0, "rail": 4.0}  # 形状の間引き許容誤差 [m]


def fetch_osm(path):
    if path and os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    print("querying Overpass API ...", file=sys.stderr)
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "mini-shikoku-3d/1.0"})
    with urllib.request.urlopen(req, timeout=600) as res:
        osm = json.load(res)
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
        self.adj = {}  # node -> [(neighbor, length, railway, is_service)]
        for el in osm["elements"]:
            if el["type"] != "way":
                continue
            tags = el.get("tags", {})
            railway = tags.get("railway")
            service = "service" in tags
            nodes = [n for n in el["nodes"] if n in self.coord]
            for a, b in zip(nodes, nodes[1:]):
                d = meters(self.coord[a], self.coord[b])
                self.adj.setdefault(a, []).append((b, d, railway, service))
                self.adj.setdefault(b, []).append((a, d, railway, service))
        # 近傍探索用の格子 (約 500m 四方)
        self.grid = {}
        for n in self.adj:
            self.grid.setdefault(self._cell(self.coord[n]), []).append(n)

    @staticmethod
    def _cell(c):
        return (int(c[0] / 0.005), int(c[1] / 0.005))

    @staticmethod
    def allowed(kind, railway):
        if kind == "tram":
            return railway == "tram"
        return railway in ("rail", "light_rail", "narrow_gauge")

    def nearest(self, c, kind, k=SNAP_CANDIDATES):
        cx, cy = self._cell(c)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in self.grid.get((cx + dx, cy + dy), []):
                    if not any(self.allowed(kind, e[2]) for e in self.adj[n]):
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

    def shortest(self, src, dst, kind, limit):
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
            for m, length, railway, service in self.adj[n]:
                if not self.allowed(kind, railway):
                    continue
                cost = d + length * (4.0 if service else 1.0)  # 側線・渡り線は避ける
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


def segment_shape(graph, a, b, kind):
    """駅 a から駅 b への線路形状 (中間点のみ)。見つからなければ None。"""
    straight = meters(a, b)
    limit = straight * MAX_DETOUR + 1000
    best = None
    for da, na in graph.nearest(a, kind):
        for db, nb in graph.nearest(b, kind):
            res = graph.shortest(na, nb, kind, limit)
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


def main():
    osm = fetch_osm(sys.argv[1] if len(sys.argv) > 1 else None)
    graph = RailGraph(osm)
    print(f"graph: {len(graph.adj)} nodes", file=sys.stderr)
    by_line = build_network.load_stations(None)
    lines = build_network.build_lines(by_line)
    shapes, report = {}, []
    for key, line in lines.items():
        segs = []
        ok = 0
        for (na, ca), (nb, cb) in zip(line["stations"], line["stations"][1:]):
            shape = segment_shape(graph, ca, cb, line["kind"])
            if shape is None:
                report.append(f"  {line['name']}: {na} - {nb} は直線のまま")
                segs.append([])
            else:
                ok += 1
                segs.append(shape)
        shapes[key] = segs
        print(f"{line['name']}: {ok}/{len(segs)} 区間", file=sys.stderr)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(shapes, f, ensure_ascii=False, separators=(",", ":"))
    if report:
        print("経路が見つからなかった区間:", file=sys.stderr)
        print("\n".join(report), file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
