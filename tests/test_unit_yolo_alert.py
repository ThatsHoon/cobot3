"""T2 단위: yolo_infer.infer_with_alerts 정책 (alert_conf + cooldown)."""
import time
import types

import pytest


@pytest.fixture
def yolo(mock_yolo_box):
    """ultralytics 미설치 환경 대비 — _model 을 직접 mock 으로 주입한 인스턴스."""
    import config  # noqa
    import yolo_infer

    inst = yolo_infer.YoloInfer()
    # ultralytics 미설치여도 강제로 _model 을 mock 객체로 세팅 (테스트는 단위 로직만 검증)
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


def test_low_confidence_no_alert(yolo, fake_bgr, mock_yolo_box):
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=0, conf=0.40)]    # 0.55 미달
    dets, alert, _animal = inst.infer_with_alerts(fake_bgr)
    assert len(dets) == 1
    assert alert is None


def test_high_confidence_emits_alert(yolo, fake_bgr, mock_yolo_box):
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=0, conf=0.78)]
    dets, alert, _animal = inst.infer_with_alerts(fake_bgr)
    assert alert is not None
    assert alert["level"] == "ALERT"
    assert alert["event"] == "person_detected_near_fence"
    assert alert["confidence"] >= 0.55
    assert alert["count"] == 1
    assert len(alert["bbox_xyxy"]) == 4


def test_cooldown_blocks_subsequent_alert(yolo, fake_bgr, mock_yolo_box):
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=0, conf=0.78)]
    _, a1, _ = inst.infer_with_alerts(fake_bgr)
    assert a1 is not None
    _, a2, _ = inst.infer_with_alerts(fake_bgr)   # 즉시 재호출
    assert a2 is None, "cooldown 안 걸림 — 정책 위배"


def test_cooldown_expiry_allows_alert(yolo, fake_bgr, mock_yolo_box, monkeypatch):
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=0, conf=0.78)]
    _, a1, _ = inst.infer_with_alerts(fake_bgr)
    assert a1 is not None
    # _last_person_alert_ts 를 과거로 돌려 cooldown 통과
    import config
    inst._last_person_alert_ts = time.monotonic() - (config.YOLO_ALERT_COOLDOWN + 1.0)
    _, a3, _ = inst.infer_with_alerts(fake_bgr)
    assert a3 is not None, "cooldown 만료 후 alert 안 옴"


def test_non_person_class_no_alert(yolo, fake_bgr, mock_yolo_box):
    """COCO id 30(skis) — YOLO_CLASSES 미포함이라 filter 통과 못함."""
    inst, fake = yolo
    fake.boxes = [mock_yolo_box(cls=30, conf=0.95)]
    dets, alert, animal = inst.infer_with_alerts(fake_bgr)
    assert dets == []
    assert alert is None
    assert animal is None


def test_multiple_persons_top_conf_used(yolo, fake_bgr, mock_yolo_box):
    inst, fake = yolo
    fake.boxes = [
        mock_yolo_box(cls=0, conf=0.62, xyxy=(0, 0, 50, 50)),
        mock_yolo_box(cls=0, conf=0.88, xyxy=(100, 100, 200, 200)),
        mock_yolo_box(cls=0, conf=0.71, xyxy=(300, 50, 400, 150)),
    ]
    _, alert, _ = inst.infer_with_alerts(fake_bgr)
    assert alert is not None
    assert alert["count"] == 3
    assert abs(alert["confidence"] - 0.88) < 1e-3   # top conf 사용


def test_no_detections_no_alert(yolo, fake_bgr):
    inst, fake = yolo
    fake.boxes = []
    dets, alert, animal = inst.infer_with_alerts(fake_bgr)
    assert dets == []
    assert alert is None
    assert animal is None


def test_disabled_yolo_returns_empty(fake_bgr):
    """ultralytics 자체 import 실패 흉내."""
    import yolo_infer
    inst = yolo_infer.YoloInfer()
    inst._model = None    # 미로드 상태
    assert not inst.enabled
    dets, alert, animal = inst.infer_with_alerts(fake_bgr)
    assert dets == [] and alert is None and animal is None
