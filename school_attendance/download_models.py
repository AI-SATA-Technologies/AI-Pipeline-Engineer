"""Download the ONNX models this service needs into MODEL_DIR.

Replaces insightface's auto-download. Fetches the InsightFace 'buffalo' model
packs and keeps only the files the pipeline actually uses:

    buffalo_sc/det_500m.onnx     detector (both modes)
    buffalo_sc/w600k_mbf.onnx    recognizer (lite mode)
    buffalo_l/w600k_r50.onnx     recognizer (heavy mode)

Every kept file is checked against a pinned SHA-256 (pipeline/model_files.py);
a file that doesn't match is deleted and the run fails, so a tampered or
corrupted download is never used. Unused buffalo_l models (det_10g, 1k3d68,
2d106det, genderage) are deleted to save several hundred MB. Run once:

    python download_models.py
"""
import os
import sys
import urllib.request
import zipfile

from config import MODEL_DIR
from pipeline import model_files

BASE_URL = 'https://github.com/deepinsight/insightface/releases/download/v0.7'

# pack -> the .onnx files to KEEP after extraction (all other .onnx are removed)
KEEP: dict[str, set[str]] = {}
for _pack, _name in model_files.SHA256:
    KEEP.setdefault(_pack, set()).add(_name)


def _verify(pack: str) -> list[str]:
    """Return the kept files of `pack` that are missing or fail their checksum."""
    bad = []
    for name in sorted(KEEP[pack]):
        p = os.path.join(MODEL_DIR, pack, name)
        if not os.path.exists(p) or model_files.sha256_of(p) != model_files.SHA256[(pack, name)]:
            bad.append(name)
    return bad


def _download_pack(pack: str) -> None:
    pack_dir = os.path.join(MODEL_DIR, pack)
    os.makedirs(pack_dir, exist_ok=True)
    zip_path = os.path.join(MODEL_DIR, f'{pack}.zip')
    url = f'{BASE_URL}/{pack}.zip'

    print(f'[models] downloading {url}')
    urllib.request.urlretrieve(url, zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        # Some packs nest files under "<pack>/", others store them at the root.
        nested = all(n.replace('\\', '/').startswith(f'{pack}/') for n in names if n.strip())
        zf.extractall(MODEL_DIR if nested else pack_dir)
    os.remove(zip_path)

    for name in os.listdir(pack_dir):
        if name.endswith('.onnx') and name not in KEEP[pack]:
            os.remove(os.path.join(pack_dir, name))
            print(f'[models] removed unused {pack}/{name}')


def main() -> int:
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f'[models] target dir: {MODEL_DIR}')
    for pack in sorted(KEEP):
        if not _verify(pack):
            print(f'[models] {pack}: already present and verified, skipping')
            continue
        try:
            _download_pack(pack)
        except Exception as exc:
            print(f'[models] ERROR downloading {pack}: {exc}', file=sys.stderr)
            print(f'[models] manually place {sorted(KEEP[pack])} under '
                  f'{os.path.join(MODEL_DIR, pack)}', file=sys.stderr)
            return 1
        bad = _verify(pack)
        if bad:
            for name in bad:
                p = os.path.join(MODEL_DIR, pack, name)
                if os.path.exists(p):
                    os.remove(p)
            print(f'[models] ERROR {pack}: checksum mismatch for {bad} — files deleted. '
                  f'The download may be corrupted or tampered with.', file=sys.stderr)
            return 1
        print(f'[models] {pack}: downloaded and verified')
    print('[models] done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
