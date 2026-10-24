"""The ONNX model files this service uses, where they live, and their checksums.

Shared by the detector, the recognizer and ``download_models.py`` so the file
list and the SHA-256 pins exist in exactly one place.
"""
import hashlib
import logging
import os

from config import MODEL_DIR

logger = logging.getLogger('attendance.models')

# (pack, filename) -> SHA-256 of the official InsightFace v0.7 release file.
SHA256 = {
    ('buffalo_sc', 'det_500m.onnx'): '5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a',
    ('buffalo_sc', 'w600k_mbf.onnx'): '9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f',
    ('buffalo_l', 'w600k_r50.onnx'): '4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43',
}

DETECTOR = ('buffalo_sc', 'det_500m.onnx')
# mode -> recognition model file. The file stem is stored with every embedding
# so vectors from different models are never compared.
RECOGNIZERS = {
    'heavy': ('buffalo_l', 'w600k_r50.onnx'),
    'lite': ('buffalo_sc', 'w600k_mbf.onnx'),
}


def path(model: tuple[str, str]) -> str:
    return os.path.join(MODEL_DIR, *model)


def embedding_model_name(mode: str) -> str:
    """Name recorded in the DB for embeddings made in `mode` (e.g. 'w600k_r50')."""
    return os.path.splitext(RECOGNIZERS[mode][1])[0]


def sha256_of(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(model: tuple[str, str]) -> str:
    """Return the model's path; raise if missing, warn if its checksum is unexpected."""
    p = path(model)
    if not os.path.exists(p):
        raise FileNotFoundError(
            f'Model not found at {p}. Run "python download_models.py" or set MODEL_DIR in your .env.'
        )
    expected = SHA256.get(model)
    if expected and sha256_of(p) != expected:
        logger.warning('checksum mismatch for %s — file is not the official release', p)
    return p
