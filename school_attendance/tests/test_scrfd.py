import numpy as np

from pipeline.scrfd import distance2bbox, distance2kps


def test_distance2bbox():
    points = np.array([[10.0, 20.0]])
    distance = np.array([[1.0, 2.0, 3.0, 4.0]])  # left, top, right, bottom
    out = distance2bbox(points, distance)
    np.testing.assert_allclose(out, [[9.0, 18.0, 13.0, 24.0]])


def test_distance2kps():
    points = np.array([[10.0, 20.0]])
    distance = np.array([[1.0, 2.0, 3.0, 4.0]])  # two (dx, dy) keypoint offsets
    out = distance2kps(points, distance)
    np.testing.assert_allclose(out, [[11.0, 22.0, 13.0, 24.0]])
