"""서버측 YOLO 추론 (설계 §S3 / D6).

degrade 된 5fps RGB 프레임을 받아 사람/동물 bbox 를 낸다.
ultralytics 미설치 시 graceful 비활성(탐지 없음, 서버는 정상 동작).
"""
import logging

import config

log = logging.getLogger("c2.yolo")


class YoloInfer:
    def __init__(self):
        self._model = None
        try:
            from ultralytics import YOLO
            self._model = YOLO(config.YOLO_MODEL)
            log.info("YOLO loaded: %s", config.YOLO_MODEL)
        except Exception as e:
            log.warning("YOLO 비활성 (ultralytics 미설치/로드 실패): %s", e)

    @property
    def enabled(self) -> bool:
        return self._model is not None

    def infer(self, bgr) -> list[dict]:
        if self._model is None:
            return []
        try:
            r = self._model.predict(bgr, verbose=False, conf=0.35)[0]
        except Exception as e:
            log.warning("YOLO infer 실패: %s", e)
            return []
        out = []
        for b in r.boxes:
            cls = int(b.cls[0])
            name = config.YOLO_CLASSES.get(cls)
            if name is None:                       # 관심 클래스만(person 등)
                continue
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            out.append({"class_name": name, "conf": float(b.conf[0]),
                        "bbox": [x1, y1, x2 - x1, y2 - y1]})
        return out
