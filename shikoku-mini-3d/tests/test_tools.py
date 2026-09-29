"""データ生成スクリプトのテスト:  python3 -m unittest discover tests"""
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import build_tracks  # noqa: E402
import import_gtfs  # noqa: E402


def osm(ways, nodes):
    els = [{"type": "node", "id": i, "lon": c[0], "lat": c[1]} for i, c in nodes.items()]
    els += [{"type": "way", "id": k + 1, "nodes": w, "tags": t} for k, (w, t) in enumerate(ways)]
    return {"elements": els}


class TrackTests(unittest.TestCase):
    def setUp(self):
        # A(0) -- 曲線の本線 (1,2,3) -- B(4)、A-B を直結する側線、別の路面電車線
        self.nodes = {0: (132.70, 33.80), 1: (132.705, 33.803), 2: (132.71, 33.804),
                      3: (132.715, 33.803), 4: (132.72, 33.80), 5: (132.71, 33.80),
                      10: (132.70, 33.81), 11: (132.72, 33.81)}
        self.graph = build_tracks.RailGraph(osm([
            ([0, 1, 2, 3, 4], {"railway": "rail"}),
            ([0, 5, 4], {"railway": "rail", "service": "siding"}),
            ([10, 11], {"railway": "tram"}),
        ], self.nodes))

    def test_shortest_avoids_siding(self):
        _, path = self.graph.shortest(0, 4, "rail", 1e9)
        self.assertEqual(path, [0, 1, 2, 3, 4])

    def test_tram_does_not_use_rail(self):
        self.assertIsNone(self.graph.shortest(0, 4, "tram", 1e9))
        self.assertEqual(self.graph.nearest((132.70, 33.8101), "tram")[0][1], 10)

    def test_segment_shape_follows_curve(self):
        shape = build_tracks.segment_shape(self.graph, (132.70, 33.80), (132.72, 33.80), "rail")
        self.assertTrue(shape)
        self.assertTrue(any(abs(p[1] - 33.804) < 1e-6 for p in shape))

    def test_segment_without_track_falls_back(self):
        self.assertIsNone(build_tracks.segment_shape(self.graph, (133.5, 33.5), (133.6, 33.5), "rail"))

    def test_simplify_keeps_ends_and_drops_collinear(self):
        pts = [(132.70 + i * 0.001, 33.80) for i in range(10)]
        self.assertEqual(build_tracks.simplify(pts, 1.0), [pts[0], pts[-1]])


def feed(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    buf.seek(0)
    return zipfile.ZipFile(buf)


class GtfsTests(unittest.TestCase):
    def test_calendar_and_exceptions(self):
        z = feed({
            "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                            "WD,1,1,1,1,1,0,0,20260101,20261231\nHD,0,0,0,0,0,1,1,20260101,20261231\n",
            "calendar_dates.txt": "service_id,date,exception_type\nWD,20261012,2\nHD,20261012,1\n",
        })
        self.assertEqual(import_gtfs.active_services(z, "20261005"), {"WD"})   # 月曜
        self.assertEqual(import_gtfs.active_services(z, "20261004"), {"HD"})   # 日曜
        self.assertEqual(import_gtfs.active_services(z, "20261012"), {"HD"})   # 祝日 (スポーツの日)

    def test_no_holidays_when_every_day_is_the_same(self):
        # 毎日同じダイヤのフィードから、平日を祝日と誤判定しない
        z = feed({
            "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                            "ALL,1,1,1,1,1,1,1,20260101,20261231\n",
            "calendar_dates.txt": "service_id,date,exception_type\n",
        })
        self.assertEqual(import_gtfs.holiday_dates(z, "20261004", "20261005"), [])

    def test_seconds_over_24h(self):
        self.assertEqual(import_gtfs.seconds("25:10:05"), 25 * 3600 + 10 * 60 + 5)

    def test_shape_between_orders_points(self):
        shape = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0), (0.003, 0.0), (0.004, 0.0)]
        mids = import_gtfs.shape_between(shape, [(0.0, 0.0), (0.002, 0.0), (0.004, 0.0)])
        self.assertEqual(mids, [[[0.001, 0.0]], [[0.003, 0.0]]])


if __name__ == "__main__":
    unittest.main()
