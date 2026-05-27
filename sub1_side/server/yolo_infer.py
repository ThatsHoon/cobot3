"""서버측 YOLO 추론 (설계 §S3 / D6).

degrade 된 5fps RGB 프레임을 받아 사람/동물 bbox 를 낸다.
ultralytics 미설치 시 graceful 비활성(탐지 없음, 서버는 정상 동작).

DMZ Sentry M5: alert 정책(conf >= ALERT_CONF + cooldown) 추가.
"""
import logging
import time

import config

log = logging.getLogger("c2.yolo")


# 4-class 모델 침입자 그룹: person + soldier + drone → intruder alert 트리거
_INTRUDER_CLASSES = {"person", "soldier", "drone"}
# animal 그룹 — 4-class 모델에서 "animal" 단일 클래스
_ANIMAL_CLASSES = {"animal", "bird", "cat", "dog", "horse", "sheep",
                   "cow", "elephant", "bear", "zebra", "giraffe", "deer"}


class YoloInfer:
    def __init__(self):
        self._model = None
        self._last_person_alert_ts = 0.0
        self._last_animal_alert_ts = 0.0
        # 안정 감지 트래커: {label: {first_ts, last_ts, frame_count, bbox_cx, bbox_cy}}
        self._stable: dict[str, dict] = {}
        self._auto_fire_cooldown_until: float = 0.0
        self._auto_fire_cb = None

        if config.C2_YOLO_LOCAL != "0":
            try:
                from ultralytics import YOLO
                self._model = YOLO(config.YOLO_MODEL)
                log.info("YOLO loaded (local): %s", config.YOLO_MODEL)
            except Exception as e:
                log.warning("YOLO 비활성 (ultralytics 미설치/로드 실패): %s", e)
        else:
            log.info("C2_YOLO_LOCAL=0 — stable-tracker 전용 (추론은 main_side yolo_node)")

    @property
    def enabled(self) -> bool:
        # WHY: stable-tracker는 C2_YOLO_LOCAL=0 (main_side 추론) 에서도 작동해야 하므로
        # 항상 True → auto_fire_cb 등록이 항상 이루어진다.
        return True

    def set_auto_fire_cb(self, cb):
        """ros_bridge 에서 주입: cb(label, bbox_cx, bbox_cy)"""
        self._auto_fire_cb = cb

    # 자동사격 프레임 카운트 기준: {label: (window_초, 최소_프레임)}
    _STABLE_THRESHOLDS: dict[str, tuple[float, int]] = {
        "soldier": (5.0, 3),   # 5초 window 내 3프레임 → 공포탄
        "person":  (5.0, 3),
        "drone":   (3.0, 2),   # 3초 window 내 2프레임 → 정밀사격
    }

    def _update_stable(self, dets: list[dict]) -> None:
        """매 프레임 호출. window 내 프레임 카운트 기준 충족 시 자동사격 cb 호출.

        WHY: 단발 오탐 방지 — window 시간 내 충분한 프레임이 감지될 때만 트리거.
        - soldier/person: 5초 window 내 3프레임 이상 → 공포탄
        - drone: 3초 window 내 2프레임 이상 → 정밀사격
        """
        now = time.monotonic()
        seen: set[str] = set()

        for d in dets:
            label = d.get("class_name", "")
            if label not in self._STABLE_THRESHOLDS:
                continue
            if d.get("conf", 0) < config.YOLO_ALERT_CONF:
                continue

            # bbox는 [x1, y1, w, h] 형식 (infer() 참조)
            bbox = d.get("bbox", [0, 0, 0, 0])
            cx = bbox[0] + bbox[2] / 2.0
            cy = bbox[1] + bbox[3] / 2.0
            seen.add(label)

            window_s, min_frames = self._STABLE_THRESHOLDS[label]

            if label not in self._stable:
                self._stable[label] = {
                    "first_ts": now, "last_ts": now,
                    "frame_count": 1,
                    "bbox_cx": cx, "bbox_cy": cy,
                }
            else:
                entry = self._stable[label]
                # WHY: window 만료 시 새 window 로 리셋 — 오래된 카운트 누적 방지
                if now - entry["first_ts"] > window_s:
                    self._stable[label] = {
                        "first_ts": now, "last_ts": now,
                        "frame_count": 1,
                        "bbox_cx": cx, "bbox_cy": cy,
                    }
                else:
                    entry["last_ts"] = now
                    entry["frame_count"] += 1
                    entry["bbox_cx"] = cx
                    entry["bbox_cy"] = cy

            entry = self._stable[label]
            if (entry["frame_count"] >= min_frames
                    and now >= self._auto_fire_cooldown_until
                    and self._auto_fire_cb is not None):
                log.info(
                    "자동사격 트리거: label=%s cx=%.1f cy=%.1f "
                    "frames=%d window=%.1fs/%.1fs",
                    label, cx, cy, entry["frame_count"],
                    now - entry["first_ts"], window_s)
                self._auto_fire_cooldown_until = now + getattr(
                    config, "AUTO_FIRE_COOLDOWN_S", 30.0)
                cb = self._auto_fire_cb
                self._stable.clear()
                cb(label, cx, cy)
                return

        # 0.5초 이상 미감지 항목 제거
        for k in list(self._stable.keys()):
            if k not in seen and now - self._stable[k]["last_ts"] > 0.5:
                del self._stable[k]

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
        # _update_stable 은 빈 dets 로도 호출해야 stale 항목 정리가 동작한다
        self._update_stable(dets)
        if not dets:
            return dets, None, None
        now = time.monotonic()

        # intruder (person / soldier / drone) — 4-class 모델 침입자 그룹
        person_alert = None
        persons = [d for d in dets if d["class_name"] in _INTRUDER_CLASSES
                   and d["conf"] >= config.YOLO_ALERT_CONF]
        if persons and (now - self._last_person_alert_ts) >= config.YOLO_ALERT_COOLDOWN:
            self._last_person_alert_ts = now
            top = max(persons, key=lambda d: d["conf"])
            x, y, w, h = top["bbox"]
            person_alert = {
                "level": "ALERT",
                "event": "intruder_detected",
                "label": top["class_name"],
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
