#!/usr/bin/env python3
"""国土数値情報「鉄道データ (N02)」の駅 (Station.geojson) から、四国付近の駅を取り出す。

  python3 tools/extract_n02_stations.py N02-24_Station.geojson

出力: tools/n02_stations.json   [[運営会社, 路線名, 駅名, 経度, 緯度], ...]
build_network.py はこのファイルがあれば、駅の座標をこちらに置き換えます。
出典: 「国土数値情報（鉄道データ）」（国土交通省）を加工して作成 (CC BY 4.0)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "n02_stations.json")
BBOX = (32.6, 132.0, 34.6, 134.9)  # 四国 (南, 西, 北, 東)


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    out = []
    for f in data["features"]:
        p = f["properties"]
        coords = f["geometry"]["coordinates"]  # 駅はホームの範囲を表す線。中点を駅の位置とする
        lon = sum(c[0] for c in coords) / len(coords)
        lat = sum(c[1] for c in coords) / len(coords)
        if BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]:
            out.append([p["N02_004"], p["N02_003"], p["N02_005"], round(lon, 6), round(lat, 6)])
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT}: {len(out)} stations", file=sys.stderr)


if __name__ == "__main__":
    main()
