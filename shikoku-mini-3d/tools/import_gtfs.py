#!/usr/bin/env python3
"""GTFS / GTFS-JP の時刻表を取り込み、実際のダイヤで列車を走らせるためのスクリプト。

  python3 tools/import_gtfs.py feed.zip --group iyotetsu_gtfs \\
      --group-name "伊予鉄 (時刻表データ)" --replaces iyo_takahama,iyo_yokogawara,iyo_gunchu

出力: tools/gtfs/<フィード名>.json
  build_network.py は tools/gtfs/ のファイルを自動で読み込み、
  --replaces で指定した路線の推計ダイヤを、時刻表データの列車で置き換えます。

- 平日ダイヤ (--weekday の日) と土休日ダイヤ (--holiday の日) の両方を取り込み、
  各便がどちらのダイヤで走るかを記録します。祝日の一覧もフィードの運行日から求めます。
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
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "gtfs")  # 1 フィードにつき 1 ファイル

VEHICLE = {
    "tram": dict(kind="tram", cars=1, carLength=12, width=2.3, height=3.6, speed=14, dwell=20, accel=8),
    "rail": dict(kind="rail", cars=2, carLength=20, width=2.9, height=4.0, speed=75, dwell=30, accel=30),
    # 阿佐海岸鉄道の DMV (線路と道路の両方を走るマイクロバス型の車両)
    "dmv": dict(kind="rail", cars=1, carLength=9, width=2.3, height=3.2, speed=40, dwell=20, accel=10),
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


def feed_range(z):
    """フィードの有効期間 (calendar.txt と calendar_dates.txt から)。"""
    dates = [r["start_date"] for r in read_table(z, "calendar.txt")] + \
            [r["end_date"] for r in read_table(z, "calendar.txt")] + \
            [r["date"] for r in read_table(z, "calendar_dates.txt")]
    return min(dates), max(dates)


def pick_dates(z, today):
    """今日以降でフィード期間内の、最初の月曜 (平日) と日曜 (土休日)。"""
    start, end = feed_range(z)
    day = max(datetime.datetime.strptime(today, "%Y%m%d"), datetime.datetime.strptime(start, "%Y%m%d"))
    weekday = holiday = None
    for _ in range(60):
        ds = day.strftime("%Y%m%d")
        if ds > end:
            break
        if day.weekday() == 0 and not weekday:
            weekday = ds
        if day.weekday() == 6 and not holiday:
            holiday = ds
        day += datetime.timedelta(days=1)
    return weekday, holiday


def holiday_dates(z, holiday_date):
    """平日 (月〜金) なのに土休日と同じ運行になる日 = 祝日・年末年始など。"""
    start, end = feed_range(z)
    ref = active_services(z, holiday_date)
    out = []
    day = datetime.datetime.strptime(start, "%Y%m%d")
    while day.strftime("%Y%m%d") <= end:
        ds = day.strftime("%Y%m%d")
        if day.weekday() < 5 and active_services(z, ds) == ref:
            out.append(ds)
        day += datetime.timedelta(days=1)
    return out


def display_name(route, routes):
    """系統名。短い名前が無く、長い名前が他の路線と同じなら route_id で区別する。"""
    if route.get("route_short_name"):
        return route["route_short_name"]
    long_name = route.get("route_long_name") or route["route_id"]
    if sum(1 for r in routes.values() if r.get("route_long_name") == long_name) > 1:
        # 例: "東西線上り_A" -> "東西線"
        rid = re.sub(r"(上り|下り)?(_[A-Za-z0-9]+)?$", "", route["route_id"])
        base = re.sub(r"(路面電車|電車|鉄道)$", "", long_name).strip()  # 例: "とさでん路面電車" -> "とさでん"
        return f"{base} {rid}"
    return long_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feed", help="GTFS の zip ファイル")
    ap.add_argument("--weekday", help="平日ダイヤとして取り込む日 (YYYYMMDD)。省略時は今日以降の最初の月曜")
    ap.add_argument("--holiday", help="土休日ダイヤとして取り込む日 (YYYYMMDD)。省略時は今日以降の最初の日曜")
    ap.add_argument("--group", default="gtfs", help="凡例のグループ ID (既存のグループ ID も指定可)")
    ap.add_argument("--group-name", default="時刻表データ", help="凡例に表示する名前")
    ap.add_argument("--replaces", default="", help="置き換える推計ダイヤの路線キー (カンマ区切り)")
    ap.add_argument("--route-types", default="0,1,2")
    ap.add_argument("--vehicle", choices=list(VEHICLE), help="車両の見た目 (省略時は route_type から判断)")
    ap.add_argument("--prefix", help="系統 ID の接頭辞 (省略時はファイル名)")
    ap.add_argument("--credit", default="", help="出典表記 (例: とさでん交通 GTFS, CC BY 4.0)")
    args = ap.parse_args()

    z = zipfile.ZipFile(args.feed)
    prefix = args.prefix or re.sub(r"\W", "", os.path.splitext(os.path.basename(args.feed))[0])
    today = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    auto_wd, auto_hd = pick_dates(z, today.strftime("%Y%m%d"))
    days = {"weekday": args.weekday or auto_wd, "holiday": args.holiday or auto_hd}
    days = {k: v for k, v in days.items() if v}

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

    all_trips = {t["trip_id"]: t for t in read_table(z, "trips.txt") if t["route_id"] in routes}
    trip_days = {}
    for label, date in days.items():
        active = active_services(z, date)
        for tid, t in all_trips.items():
            if t["service_id"] in active:
                trip_days.setdefault(tid, []).append(label)

    shapes = {}
    for row in read_table(z, "shapes.txt"):
        shapes.setdefault(row["shape_id"], []).append(
            (int(row["shape_pt_sequence"]), (float(row["shape_pt_lon"]), float(row["shape_pt_lat"]))))
    shapes = {k: [p for _, p in sorted(v)] for k, v in shapes.items()}

    times = {}
    for row in read_table(z, "stop_times.txt"):
        if row["trip_id"] in trip_days:
            times.setdefault(row["trip_id"], []).append(row)

    patterns = {}
    for tid, rows in times.items():
        rows.sort(key=lambda r: int(r["stop_sequence"]))
        if len(rows) < 2:
            continue
        trip = all_trips[tid]
        seq = tuple(r["stop_id"] for r in rows)
        key = (trip["route_id"], trip.get("direction_id", ""), seq)
        dep0 = seconds(rows[0]["departure_time"])
        t = [[seconds(r["arrival_time"]) - dep0, seconds(r["departure_time"]) - dep0] for r in rows]
        pat = patterns.setdefault(key, {"trips": [], "shape": trip.get("shape_id")})
        pat["trips"].append({"dep": dep0, "t": t, "days": trip_days[tid]})

    services, lines = [], {}
    for n, ((route_id, direction, seq), pat) in enumerate(sorted(patterns.items(), key=lambda kv: kv[0])):
        route = routes[route_id]
        kind = args.vehicle or ("tram" if route["route_type"] == "0" else "rail")
        color = "#" + route["route_color"] if route.get("route_color") else "#6d6d6d"
        name = display_name(route, routes)
        pts = [stop_point(sid) for sid in seq]
        mids = shape_between(shapes[pat["shape"]], [c for _, c in pts]) if pat["shape"] in shapes else None
        path = []
        for k, (sname, c) in enumerate(pts):
            path.append([sname, c, 1])
            if mids and k < len(mids):
                path.extend(["", [round(x, 6), round(y, 6)], 0] for x, y in mids[k])
        pat["trips"].sort(key=lambda tr: tr["dep"])
        line_key = f"{prefix}_{route_id}"
        # 路線の線形は、その路線でいちばん長い系統のものを使う
        if line_key not in lines or len(path) > len(lines[line_key]["shape"]):
            lines[line_key] = dict(
                id=line_key, name=name, operator=args.group_name,
                group=args.group, kind=kind, color=color,
                stations=[[s, c] for s, c, stop in path if stop],
                shape=[c for _, c, _ in path])
        services.append(dict(
            VEHICLE[kind], id=f"{prefix}{n}", name=name, group=args.group, line=line_key, color=color,
            loop=False, both=False, offset=0, path=path, trips=pat["trips"]))

    out = dict(
        feed=os.path.basename(args.feed),
        credit=args.credit,
        days=days,
        holidays=holiday_dates(z, days["holiday"]) if "holiday" in days else [],
        groups=[dict(id=args.group, name=args.group_name)],
        replaces=[x for x in args.replaces.split(",") if x],
        lines=list(lines.values()),
        services=services,
    )
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{prefix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ntrips = sum(len(s["trips"]) for s in services)
    print(f"wrote {out_path}: {len(lines)} routes, {len(services)} patterns, {ntrips} trips, days={days}, "
          f"{len(out['holidays'])} holiday-like weekdays", file=sys.stderr)


if __name__ == "__main__":
    main()
