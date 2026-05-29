import numpy as np

from pipeline.align import ARCFACE_DST, _umeyama, norm_crop


def test_umeyama_identity():
    M = _umeyama(ARCFACE_DST.copy(), ARCFACE_DST)
    np.testing.assert_allclose(M[:2, :2], np.eye(2), atol=1e-6)
    np.testing.assert_allclose(M[:2, 2], np.zeros(2), atol=1e-6)


def test_umeyama_recovers_known_similarity():
    theta = np.deg2rad(30.0)
    scale = 2.0
    R = scale * np.array([[np.cos(theta), -np.sin(theta)],
                          [np.sin(theta),  np.cos(theta)]])
    t = np.array([10.0, -5.0])

    src = ARCFACE_DST.copy()
    dst = src @ R.T + t

    M = _umeyama(src, dst)
    recovered = src @ M[:2, :2].T + M[:2, 2]
    np.testing.assert_allclose(recovered, dst, atol=1e-6)


def test_norm_crop_output_shape():
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    crop = norm_crop(img, ARCFACE_DST.copy())
    assert crop.shape == (112, 112, 3)
