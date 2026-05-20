"""서버측 YOLO 추론 (설계 §S3 / D6).

degrade 된 5fps RGB 프레임을 받아 사람/동물 bbox 를 낸다.
ultralytics 미설치 시 graceful 비활성(탐지 없음, 서버는 정상 동작).

DMZ Sentry M5: alert 정책(conf >= ALERT_CONF + cooldown) 추가.
"""
import logging
import time

import config

log = logging.getLogger("c2.yolo")


_ANIMAL_CLASSES = {"animal", "bird", "cat", "dog", "horse", "sheep",
                   "cow", "elephant", "bear", "zebra", "giraffe", "deer"}


class YoloInfer:
    def __init__(self):
        self._model = None
        self._last_person_alert_ts = 0.0
        self._last_animal_alert_ts = 0.0
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
        # WHY conf=YOLO_ALERT_CONF (0.7): 사용자 사양 #8 — bbox 표시도 0.7 이상만.
        if self._model is None:
            return []
        try:
            r = self._model.predict(
                bgr, verbose=False, conf=config.YOLO_ALERT_CONF)[0]
        except Exception as e:
            log.warning("YOLO infer 실패: %s", e)
            return []
        out = []
        for b in r.boxes:
            cls = int(b.cls[0])
            name = config.YOLO_CLASSES.get(cls)
            if name is None:
                continue
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            out.append({"class_name": name, "conf": float(b.conf[0]),
                        "bbox": [x1, y1, x2 - x1, y2 - y1]})
        return out

    def infer_with_alerts(self, bgr):
        """detection 리스트 + (person_alert | None) + (animal_alert | None) 반환.

        person/animal alert 는 독립 cooldown.
        - person: conf >= YOLO_ALERT_CONF, cooldown YOLO_ALERT_COOLDOWN
        - animal: conf >= YOLO_ANIMAL_ALERT_CONF, cooldown YOLO_ANIMAL_ALERT_COOLDOWN
        """
        dets = self.infer(bgr)
        if not dets:
            return dets, None, None
        now = time.monotonic()

        # person
        person_alert = None
        persons = [d for d in dets if d["class_name"] == "person"
                   and d["conf"] >= config.YOLO_ALERT_CONF]
        if persons and (now - self._last_person_alert_ts) >= config.YOLO_ALERT_COOLDOWN:
            self._last_person_alert_ts = now
            top = max(persons, key=lambda d: d["conf"])
            x, y, w, h = top["bbox"]
            person_alert = {
                "level": "ALERT",
                "event": "person_detected_near_fence",
                "label": "person",
                "confidence": float(top["conf"]),
                "bbox_xyxy": [x, y, x + w, y + h],
                "count": len(persons),
                "action": "report_and_track",
            }

        # animal
        animal_alert = None
        animals = [d for d in dets if d["class_name"] in _ANIMAL_CLASSES
                   and d["conf"] >= config.YOLO_ANIMAL_ALERT_CONF]
        if animals and (now - self._last_animal_alert_ts) >= config.YOLO_ANIMAL_ALERT_COOLDOWN:
            self._last_animal_alert_ts = now
            top = max(animals, key=lambda d: d["conf"])
            x, y, w, h = top["bbox"]
            animal_alert = {
                "level": "ALERT",
                "event": "animal_detected",
                "label": top["class_name"],
                "confidence": float(top["conf"]),
                "bbox_xyxy": [x, y, x + w, y + h],
                "count": len(animals),
                "action": "monitor",
            }

        return dets, person_alert, animal_alert
