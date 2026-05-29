"""Face alignment — ArcFace 5-point ``norm_crop`` without insightface/skimage.

Reimplements ``insightface.utils.face_align.norm_crop`` using a NumPy Umeyama
similarity transform (the same algorithm skimage's ``SimilarityTransform`` uses
internally), so the aligned 112x112 crop is numerically equivalent.
"""
import cv2
import numpy as np

# Standard ArcFace destination landmarks for a 112x112 crop
# (left eye, right eye, nose, left mouth corner, right mouth corner).
ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float64,
)


def _umeyama(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform (rotation + uniform scale + translation)
    mapping ``src`` onto ``dst``. Returns a (dim+1, dim+1) homogeneous matrix.

    Port of ``skimage.transform._geometric._umeyama`` with ``estimate_scale=True``.
    """
    num, dim = src.shape
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    A = dst_demean.T @ src_demean / num
    d = np.ones((dim,), dtype=np.float64)
    if np.linalg.det(A) < 0:
        d[dim - 1] = -1

    T = np.eye(dim + 1, dtype=np.float64)
    U, S, V = np.linalg.svd(A)
    rank = np.linalg.matrix_rank(A)
    if rank == 0:
        return np.full((dim + 1, dim + 1), np.nan)
    if rank == dim - 1:
        if np.linalg.det(U) * np.linalg.det(V) > 0:
            T[:dim, :dim] = U @ V
        else:
            s = d[dim - 1]
            d[dim - 1] = -1
            T[:dim, :dim] = U @ np.diag(d) @ V
            d[dim - 1] = s
    else:
        T[:dim, :dim] = U @ np.diag(d) @ V

    scale = 1.0 / src_demean.var(axis=0).sum() * (S @ d)
    T[:dim, dim] = dst_mean - scale * (T[:dim, :dim] @ src_mean)
    T[:dim, :dim] *= scale
    return T


def norm_crop(img: np.ndarray, kps: np.ndarray, image_size: int = 112) -> np.ndarray:
    """Return a 112x112 keypoint-aligned face crop (ArcFace/MobileFaceNet input)."""
    src = np.asarray(kps, dtype=np.float64).reshape(5, 2)
    M = _umeyama(src, ARCFACE_DST)[:2, :]
    return cv2.warpAffine(img, M, (image_size, image_size), borderValue=0.0)
