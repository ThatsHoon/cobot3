"""P3 단위: YOLO 동물 클래스 + animal alert 정책 + person/animal cooldown 독립."""
import time
import types

import pytest


@pytest.fixture
def yolo(mock_yolo_box):
    import config  # noqa
    import yolo_infer

    inst = yolo_infer.YoloInfer()

    class FakeModel:
        def __init__(self):
            self.boxes = []
        def predict(self, bgr, **kw):
            r = types.SimpleNamespace()
            r.boxes = list(self.boxes)
            return [r]

    fake = FakeModel()
    inst._model = fake
    return inst, fake


def test_animal_class_emits_animal_alert(yolo, fake_bgr, mock_yolo_box):
    """COCO id 23(bear) → animal alert (event="animal_detected"), person alert 없음."""
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=23, conf=0.85)]
    dets, person_alert, animal_alert = inst.infer_with_alerts(fake_bgr)
    assert len(dets) == 1 and dets[0]["class_name"] == "bear"
    assert person_alert is None
    assert animal_alert is not None
    assert animal_alert["event"] == "animal_detected"
    assert animal_alert["label"] == "bear"
    assert animal_alert["confidence"] >= 0.5


def test_animal_class1_label_matches(yolo, fake_bgr, mock_yolo_box):
    """jsy 학습 모델 호환 — class 1 = animal (custom 라벨)."""
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=1, conf=0.78)]
    dets, person_alert, animal_alert = inst.infer_with_alerts(fake_bgr)
    assert dets[0]["class_name"] == "animal"
    assert animal_alert is not None and animal_alert["label"] == "animal"
    assert person_alert is None


def test_person_and_animal_cooldown_independent(yolo, fake_bgr, mock_yolo_box):
    """person alert 직후 animal 발견 시 animal 은 즉시 alert (cooldown 분리)."""
    inst, fake = yolo
    # 1. person alert 발생 → person cooldown 활성
    fake.boxes = [mock_yolo_box(cls=0, conf=0.85)]
    _, p1, a1 = inst.infer_with_alerts(fake_bgr)
    assert p1 is not None and a1 is None

    # 2. 즉시 animal 만 등장 → animal alert 발생 가능
    fake.boxes = [mock_yolo_box(cls=21, conf=0.85)]   # cow
    _, p2, a2 = inst.infer_with_alerts(fake_bgr)
    assert p2 is None    # person cooldown 활성, 그러나 person 안 보임
    assert a2 is not None    # animal cooldown 미활성


def test_unknown_class_ignored(yolo, fake_bgr, mock_yolo_box):
    """YOLO_CLASSES 미등록 ID (예: 80) → 감지 결과 빈 리스트."""
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=80, conf=0.95)]
    dets, p, a = inst.infer_with_alerts(fake_bgr)
    assert dets == []
    assert p is None and a is None
