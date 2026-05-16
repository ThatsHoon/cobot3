"""WebRTC 영상 트랙 (설계 D7 / §9.1 — aiortc).

ros_bridge 가 갱신하는 최신 RGB 프레임(YOLO 오버레이 포함)을
aiortc VideoStreamTrack 으로 송출. LAN 내부라 STUN/TURN 불필요.
"""
import asyncio
import fractions
import time

import numpy as np
from aiortc import VideoStreamTrack
from av import VideoFrame

VIDEO_FPS = 5  # 설계 D8 — 5fps degrade


class BridgeVideoTrack(VideoStreamTrack):
    def __init__(self, ros_bridge):
        super().__init__()
        self._br = ros_bridge
        self._t0 = time.time()

    async def recv(self):
        # 5fps 페이싱
        await asyncio.sleep(1.0 / VIDEO_FPS)
        frame = self._br.get_video_frame()
        if frame is None:
            frame = np.zeros((360, 640, 3), dtype=np.uint8)  # 무신호 검정 화면
        vf = VideoFrame.from_ndarray(frame, format="bgr24")
        pts = int((time.time() - self._t0) * 90000)
        vf.pts = pts
        vf.time_base = fractions.Fraction(1, 90000)
        return vf
