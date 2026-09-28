#!/usr/bin/env python3
"""GTFS / GTFS-JP の時刻表を取り込み、実際のダイヤで列車を走らせるためのスクリプト。

  python3 tools/import_gtfs.py feed.zip --date 20261005 --group iyotetsu_gtfs \\
      --group-name "伊予鉄 (時刻表データ)" --replaces iyo_takahama,iyo_yokogawara,iyo_gunchu

出力: tools/gtfs_services.json
  build_network.py はこのファイルがあれば自動で読み込み、
  --replaces で指定した路線の推計ダイヤを、時刻表データの列車で置き換えます。

- 指定日 (--date) に運行する便だけを取り込みます (calendar.txt / calendar_dates.txt)。
- 対象は路面電車・地下鉄・鉄道 (route_type 0, 1, 2) の路線です (--route-types で変更可)。
- shapes.txt があれば、その線形で駅間をつなぎます。
- 同じ路線・方向・停車駅の並びの便を 1 つの系統にまとめ、便ごとの発着時刻を保持します。

GTFS データの利用条件 (ライセンス・出典表記) は提供元ごとに確認してください。
"""
import argparse
import csv
import datetime
import io
import json
import math
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "gtfs_services.json")

VEHICLE = {
    "tram": dict(kind="tram", cars=1, carLength=12, width=2.3, height=3.6, speed=14, dwell=20, accel=8),
    "rail": dict(kind="rail", cars=2, carLength=20, width=2.9, height=4.0, speed=75, dwell=30, accel=30),
}


def read_table(z, name):
    try:
        raw = z.read(name)
    except KeyError:
        return []
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def seconds(hms):
    h, m, s = (int(x) for x in hms.strip().split(":"))
    return h * 3600 + m * 60 + s


def active_services(z, date):
    """指定日に運行する service_id の集合。"""
    day = datetime.datetime.strptime(date, "%Y%m%d").date()
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    active = set()
    for row in read_table(z, "calendar.txt"):
        if row["start_date"] <= date <= row["end_date"] and row.get(weekday) == "1":
            active.add(row["service_id"])
    for row in read_table(z, "calendar_dates.txt"):
        if row["date"] != date:
            continue
        if row["exception_type"] == "1":
            active.add(row["service_id"])
        elif row["exception_type"] == "2":
            active.discard(row["service_id"])
    return active


def meters(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(lat), (a[1] - b[1]) * 110540)


def shape_between(shape, stops):
    """shape (点列) 上に停車駅を順に対応づけ、駅間の中間点のリストを返す。"""
    out = []
    pos = 0
    idx = []
    for c in stops:
        best, best_i = None, pos
        for i in range(pos, len(shape)):
            d = meters(c, shape[i])
            if best is None or d < best:
                best, best_i = d, i
        idx.append(best_i)
        pos = best_i
    for k in range(len(stops) - 1):
        out.append([list(p) for p in shape[idx[k] + 1:idx[k + 1]]])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feed", help="GTFS の zip ファイル")
    ap.add_argument("--date", required=True, help="取り込む運行日 (YYYYMMDD)")
    ap.add_argument("--group", default="gtfs", help="凡例のグループ ID")
    ap.add_argument("--group-name", default="時刻表データ", help="凡例に表示する名前")
    ap.add_argument("--replaces", default="", help="置き換える推計ダイヤの路線キー (カンマ区切り)")
    ap.add_argument("--route-types", default="0,1,2")
    args = ap.parse_args()

    z = zipfile.ZipFile(args.feed)
    route_types = set(args.route_types.split(","))
    routes = {r["route_id"]: r for r in read_table(z, "routes.txt") if r.get("route_type") in route_types}
    stops = {s["stop_id"]: s for s in read_table(z, "stops.txt")}
    # 乗り場 (stop) が駅 (station) に属していれば、駅名と駅の座標を使う
    def stop_point(sid):
        s = stops[sid]
        parent = s.get("parent_station")
        if parent and parent in stops:
            s = stops[parent]
        return s["stop_name"], [round(float(s["stop_lon"]), 6), round(float(s["stop_lat"]), 6)]

    active = active_services(z, args.date)
    trips = {t["trip_id"]: t for t in read_table(z, "trips.txt")
             if t["route_id"] in routes and t["service_id"] in active}
    shapes = {}
    for row in read_table(z, "shapes.txt"):
        shapes.setdefault(row["shape_id"], []).append(
            (int(row["shape_pt_sequence"]), (float(row["shape_pt_lon"]), float(row["shape_pt_lat"]))))
    shapes = {k: [p for _, p in sorted(v)] for k, v in shapes.items()}

    times = {}
    for row in read_table(z, "stop_times.txt"):
        if row["trip_id"] in trips:
            times.setdefault(row["trip_id"], []).append(row)

    patterns = {}
    for tid, rows in times.items():
        rows.sort(key=lambda r: int(r["stop_sequence"]))
        if len(rows) < 2:
            continue
        trip = trips[tid]
        seq = tuple(r["stop_id"] for r in rows)
        key = (trip["route_id"], trip.get("direction_id", ""), seq)
        dep0 = seconds(rows[0]["departure_time"])
        t = [[seconds(r["arrival_time"]) - dep0, seconds(r["departure_time"]) - dep0] for r in rows]
        pat = patterns.setdefault(key, {"trips": [], "shape": trip.get("shape_id")})
        pat["trips"].append({"dep": dep0, "t": t})

    services, lines = [], {}
    for n, ((route_id, direction, seq), pat) in enumerate(sorted(patterns.items(), key=lambda kv: kv[0])):
        route = routes[route_id]
        kind = "tram" if route["route_type"] == "0" else "rail"
        color = "#" + route["route_color"] if route.get("route_color") else "#6d6d6d"
        name = route.get("route_short_name") or route.get("route_long_name") or route_id
        pts = [stop_point(sid) for sid in seq]
        mids = shape_between(shapes[pat["shape"]], [c for _, c in pts]) if pat["shape"] in shapes else None
        path = []
        for k, (sname, c) in enumerate(pts):
            path.append([sname, c, 1])
            if mids and k < len(mids):
                path.extend(["", [round(x, 6), round(y, 6)], 0] for x, y in mids[k])
        pat["trips"].sort(key=lambda tr: tr["dep"])
        line_key = f"gtfs_{route_id}"
        # 路線の線形は、その路線でいちばん長い系統のものを使う
        if line_key not in lines or len(path) > len(lines[line_key]["shape"]):
            lines[line_key] = dict(
                id=line_key, name=route.get("route_long_name") or name, operator=args.group_name,
                group=args.group, kind=kind, color=color,
                stations=[[s, c] for s, c, stop in path if stop],
                shape=[c for _, c, _ in path])
        services.append(dict(
            VEHICLE[kind], id=f"gtfs{n}", name=name, group=args.group, line=line_key, color=color,
            loop=False, both=False, offset=0, path=path, trips=pat["trips"]))

    out = dict(
        groups=[dict(id=args.group, name=args.group_name)],
        replaces=[x for x in args.replaces.split(",") if x],
        lines=list(lines.values()),
        services=services,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ntrips = sum(len(s["trips"]) for s in services)
    print(f"wrote {OUT}: {len(lines)} routes, {len(services)} patterns, {ntrips} trips on {args.date}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
