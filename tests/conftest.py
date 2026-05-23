"""pytest 공용 fixture — cobot3 통합 테스트.

sub1_side/server 모듈 import 를 위해 sys.path 추가. yolo_infer/nav2_patrol
등은 config 모듈에 의존하므로 server 디렉토리를 path 에 넣어야 한다.
"""
import os
import sys
import types

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(_REPO, "sub1_side", "server")
MAIN_DIR = os.path.join(_REPO, "main_side")

for p in (SERVER_DIR, MAIN_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def repo_root():
    return _REPO


@pytest.fixture
def fake_bgr():
    """OpenCV 호환 더미 BGR 이미지 (480x640 RGB→BGR 무작위 array)."""
    import numpy as np
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_yolo_box():
    """Ultralytics YOLO box 객체와 호환되는 mock 박스 팩토리."""
    def make(cls=0, conf=0.7, xyxy=(10.0, 20.0, 110.0, 220.0)):
        b = types.SimpleNamespace()
        b.cls = [cls]
        b.conf = [conf]
        b.xyxy = [xyxy]
        return b
    return make
