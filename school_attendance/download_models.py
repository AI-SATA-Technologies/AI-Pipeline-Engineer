"""Download the ONNX models this service needs into MODEL_DIR.

Replaces insightface's auto-download. Fetches the InsightFace 'buffalo' model
packs and keeps only the files the pipeline actually uses:

    buffalo_sc/det_500m.onnx     detector (both modes)
    buffalo_sc/w600k_mbf.onnx    recognizer (lite mode)
    buffalo_l/w600k_r50.onnx     recognizer (heavy mode)

Unused buffalo_l models (det_10g, 1k3d68, 2d106det, genderage) are deleted to
save several hundred MB. Run once:

    python download_models.py
"""
import os
import sys
import urllib.request
import zipfile

from config import MODEL_DIR

BASE_URL = 'https://github.com/deepinsight/insightface/releases/download/v0.7'

# pack -> the .onnx files to KEEP after extraction (all other .onnx are removed)
KEEP = {
    'buffalo_sc': {'det_500m.onnx', 'w600k_mbf.onnx'},
    'buffalo_l': {'w600k_r50.onnx'},
}


def _have_all(pack: str) -> bool:
    return all(os.path.exists(os.path.join(MODEL_DIR, pack, f)) for f in KEEP[pack])


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
    for pack in ('buffalo_sc', 'buffalo_l'):
        if _have_all(pack):
            print(f'[models] {pack}: already present, skipping')
            continue
        try:
            _download_pack(pack)
        except Exception as exc:
            print(f'[models] ERROR downloading {pack}: {exc}', file=sys.stderr)
            print(f'[models] manually place {sorted(KEEP[pack])} under '
                  f'{os.path.join(MODEL_DIR, pack)}', file=sys.stderr)
            return 1
    print('[models] done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
