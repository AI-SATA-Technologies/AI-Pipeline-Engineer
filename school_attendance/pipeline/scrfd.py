"""SCRFD face detector on raw ONNX Runtime (no insightface dependency).

Faithful reimplementation of insightface's SCRFD detector for the ``buffalo``
ONNX models (``det_500m.onnx`` / ``det_10g.onnx``): same preprocessing,
anchor-center decoding, and NMS — so detections match the previous pipeline.

Each detection is returned as a lightweight :class:`Face` exposing ``.bbox``
(x1, y1, x2, y2), ``.kps`` (5x2 landmarks) and ``.det_score``.
"""
import cv2
import numpy as np
import onnxruntime as ort

INPUT_MEAN = 127.5
INPUT_STD = 128.0


class Face:
    __slots__ = ('bbox', 'kps', 'det_score')

    def __init__(self, bbox: np.ndarray, kps: np.ndarray, det_score: float):
        self.bbox = bbox
        self.kps = kps
        self.det_score = det_score


def distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """Decode (left, top, right, bottom) distances from anchor centers to boxes."""
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """Decode keypoint offsets from anchor centers."""
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, 0] + distance[:, i]
        py = points[:, 1] + distance[:, i + 1]
        preds.append(px)
        preds.append(py)
    return np.stack(preds, axis=-1)


class SCRFD:
    def __init__(
        self,
        model_path: str,
        providers: list[str],
        det_size: tuple[int, int] = (640, 640),
        det_thresh: float = 0.5,
        nms_thresh: float = 0.4,
    ):
        so = ort.SessionOptions()
        self.session = ort.InferenceSession(model_path, sess_options=so, providers=providers)
        self.det_thresh = det_thresh
        self.nms_thresh = nms_thresh
        self.center_cache: dict = {}

        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.output_names = [o.name for o in self.session.get_outputs()]

        # Respect a fixed input size baked into the model; otherwise use det_size.
        shape = inp.shape
        if isinstance(shape[2], int) and isinstance(shape[3], int):
            self.input_size = (shape[3], shape[2])  # (W, H)
        else:
            self.input_size = det_size

        # Output-count → FPN layout (matches insightface SCRFD variants).
        n_out = len(self.output_names)
        self.use_kps = n_out in (9, 15)
        if n_out in (6, 9):
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
            self.num_anchors = 2
        elif n_out in (10, 15):
            self.fmc = 5
            self.feat_stride_fpn = [8, 16, 32, 64, 128]
            self.num_anchors = 1
        else:
            raise ValueError(f'Unexpected SCRFD output count: {n_out}')

    def _forward(self, det_img: np.ndarray):
        input_size = (det_img.shape[1], det_img.shape[0])  # (W, H)
        blob = cv2.dnn.blobFromImage(
            det_img, 1.0 / INPUT_STD, input_size, (INPUT_MEAN,) * 3, swapRB=True
        )
        net_outs = self.session.run(self.output_names, {self.input_name: blob})

        input_height, input_width = blob.shape[2], blob.shape[3]
        scores_list, bboxes_list, kpss_list = [], [], []
        for idx, stride in enumerate(self.feat_stride_fpn):
            scores = net_outs[idx]
            bbox_preds = net_outs[idx + self.fmc] * stride
            height, width = input_height // stride, input_width // stride
            key = (height, width, stride)
            anchor_centers = self.center_cache.get(key)
            if anchor_centers is None:
                anchor_centers = np.stack(
                    np.mgrid[:height, :width][::-1], axis=-1
                ).astype(np.float32)
                anchor_centers = (anchor_centers * stride).reshape((-1, 2))
                if self.num_anchors > 1:
                    anchor_centers = np.stack(
                        [anchor_centers] * self.num_anchors, axis=1
                    ).reshape((-1, 2))
                if len(self.center_cache) < 100:
                    self.center_cache[key] = anchor_centers

            pos_inds = np.where(scores >= self.det_thresh)[0]
            bboxes = distance2bbox(anchor_centers, bbox_preds)
            scores_list.append(scores[pos_inds])
            bboxes_list.append(bboxes[pos_inds])
            if self.use_kps:
                kps_preds = net_outs[idx + self.fmc * 2] * stride
                kpss = distance2kps(anchor_centers, kps_preds).reshape((-1, 5, 2))
                kpss_list.append(kpss[pos_inds])
        return scores_list, bboxes_list, kpss_list

    def _nms(self, dets: np.ndarray) -> list[int]:
        x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            order = order[np.where(ovr <= self.nms_thresh)[0] + 1]
        return keep

    def detect(self, img: np.ndarray) -> list[Face]:
        """Detect faces in a BGR image. Returns a list of :class:`Face`, score-sorted."""
        in_w, in_h = self.input_size
        im_ratio = float(img.shape[0]) / img.shape[1]
        model_ratio = float(in_h) / in_w
        if im_ratio > model_ratio:
            new_height = in_h
            new_width = int(new_height / im_ratio)
        else:
            new_width = in_w
            new_height = int(new_width * im_ratio)
        det_scale = float(new_height) / img.shape[0]

        resized = cv2.resize(img, (new_width, new_height))
        det_img = np.zeros((in_h, in_w, 3), dtype=np.uint8)
        det_img[:new_height, :new_width, :] = resized

        scores_list, bboxes_list, kpss_list = self._forward(det_img)
        if not scores_list or sum(s.shape[0] for s in scores_list) == 0:
            return []

        scores = np.vstack(scores_list)
        order = scores.ravel().argsort()[::-1]
        bboxes = np.vstack(bboxes_list) / det_scale
        pre_det = np.hstack((bboxes, scores)).astype(np.float32, copy=False)[order]
        keep = self._nms(pre_det)
        det = pre_det[keep]

        kpss = None
        if self.use_kps:
            kpss = (np.vstack(kpss_list) / det_scale)[order][keep]

        faces = []
        for i in range(det.shape[0]):
            kps = kpss[i] if kpss is not None else None
            faces.append(Face(bbox=det[i, :4], kps=kps, det_score=float(det[i, 4])))
        return faces
