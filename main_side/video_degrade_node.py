"""video_degrade_node — 발행측 영상 대역 절감 (설계 D8 / §9.1 / sensor-and-comms §4).

Isaac OG 가 발행하는 RealSense rgb 를 받아 해상도↓ + JPEG 화질↓ + 5fps 스로틀 후
`/c2/video/compressed` 로 재발행한다. C2 web_server(aiortc) 가 이를 WebRTC 로 송출.
영상은 어떤 경로로도 DB 저장하지 않는다.

토픽/QoS 는 설계 §12 표 고정. RMW 는 환경(RMW_IMPLEMENTATION=rmw_fastrtps_cpp).
실행: source /opt/ros/humble/setup.bash && python3 video_degrade_node.py
"""
import os
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CompressedImage
import cv2

IN_RGB  = os.environ.get("DEGRADE_IN",  "").strip()   # Isaac OG ROS2CameraHelper
OUT_RGB = os.environ.get("DEGRADE_OUT", "").strip()   # → web_server
if not IN_RGB or not OUT_RGB:
    raise SystemExit("[video_degrade] DEGRADE_IN, DEGRADE_OUT env 필수 "
                     "(run_degrade.sh 참조)")
TARGET_FPS = 5.0
OUT_W, OUT_H = 640, 360
JPEG_Q = 50

# WHY: FRAME_TIMING=1 시에만 타이밍 로그 활성화. 평상시 off 로 로그 과부하 방지.
_TIMING = os.environ.get("FRAME_TIMING", "0") == "1"
_is_inspect = "inspect" in OUT_RGB  # inspect 채널만 타이밍 집중 추적

SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST, depth=5)


class VideoDegrade(Node):
    def __init__(self):
        super().__init__("video_degrade_node")
        self.sub = self.create_subscription(
            Image, IN_RGB, self._on_rgb, SENSOR_QOS)
        self.pub = self.create_publisher(
            CompressedImage, OUT_RGB, SENSOR_QOS)
        self._last = 0.0
        self._n_in = 0
        self._n_out = 0
        self._first_logged = False
        self._prev_pub_t = 0.0   # 직전 발송 wall-clock (프레임 간격 측정용)
        self.create_timer(5.0, self._stats)
        L = self.get_logger()
        L.info("==== video_degrade ENV 점검 ====")
        L.info(f"  ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID','<UNSET>')} "
               f"RMW={os.environ.get('RMW_IMPLEMENTATION','<UNSET>')} "
               f"LOCALHOST_ONLY={os.environ.get('ROS_LOCALHOST_ONLY','<UNSET>')}")
        if os.environ.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp":
            L.warn("  ⚠ RMW != rmw_fastrtps_cpp → Isaac 토픽 디스커버리 실패 위험")
        L.info(f"  pipeline: {IN_RGB} → {OUT_RGB} @ {TARGET_FPS}fps "
               f"{OUT_W}x{OUT_H} q{JPEG_Q}")
        L.info("================================")

    def _on_rgb(self, msg: Image):
        self._n_in += 1
        if not self._first_logged:
            self._first_logged = True
            self.get_logger().info(
                f"✓ 첫 프레임 수신: {msg.width}x{msg.height} enc={msg.encoding} "
                f"— Isaac↔degrade 통신 OK")
        now = time.monotonic()
        if now - self._last < 1.0 / TARGET_FPS:      # 5fps 스로틀
            return
        # WHY: self._last = now 대신 누적 방식 사용.
        # Isaac 이 간헐적으로 늦게 발행하면 self._last=now 로 갱신하면
        # 다음 통과 가능 시점도 함께 밀려 지터가 연쇄된다.
        # += 방식은 이상적인 200ms 주기를 유지해 한 프레임 지연이 다음에 전파되지 않음.
        # 단, 누적 드리프트가 1 주기(200ms) 이상 벌어지면 리셋해 튐 방지.
        self._last += 1.0 / TARGET_FPS
        if now - self._last > 1.0 / TARGET_FPS:
            self._last = now
        # sensor_msgs/Image → ndarray (rgb8/bgr8/rgba8 대응)
        h, w = msg.height, msg.width
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        enc = (msg.encoding or "rgb8").lower()
        try:
            if enc in ("rgb8", "bgr8"):
                img = buf.reshape(h, w, 3)
                if enc == "rgb8":
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif enc in ("rgba8", "bgra8"):
                img = buf.reshape(h, w, 4)
                img = cv2.cvtColor(
                    img, cv2.COLOR_RGBA2BGR if enc == "rgba8"
                    else cv2.COLOR_BGRA2BGR)
            else:
                img = buf.reshape(h, w, -1)[:, :, :3]
        except ValueError:
            self.get_logger().warn(
                f"reshape 실패 enc={enc} {w}x{h} len={buf.size}")
            return
        img = cv2.resize(img, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(
            ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
        if not ok:
            return
        out = CompressedImage()
        out.header = msg.header
        # WHY: header.stamp 을 wall-clock(UNIX ns)으로 덮어씀.
        # Isaac 시뮬레이션 시각은 C2 wall-clock 과 비교 불가 → 네트워크 지연 측정 불가.
        _pub_ns = time.time_ns()
        out.header.stamp.sec      = _pub_ns // 1_000_000_000
        out.header.stamp.nanosec  = _pub_ns %  1_000_000_000
        out.format = "jpeg"
        out.data = jpg.tobytes()
        self.pub.publish(out)
        self._n_out += 1

        if _TIMING and _is_inspect:
            _gap = (_pub_ns / 1e9 - self._prev_pub_t) * 1000
            _flag = f"  ← gap {_gap:.0f}ms !!!" if self._prev_pub_t and _gap > 300 else ""
            self.get_logger().info(
                f"[FT] SEND #{self._n_out:05d} t={_pub_ns/1e9:.3f}{_flag}")
            self._prev_pub_t = _pub_ns / 1e9

    def _stats(self):
        npub = self.count_publishers(IN_RGB)
        L = self.get_logger()
        L.info(f"in={self._n_in} out={self._n_out} "
               f"| {IN_RGB} publishers={npub} (≈{TARGET_FPS}fps 목표)")
        if self._n_in == 0:
            if npub == 0:
                L.warn(f"  ⚠ {IN_RGB} publisher 0 → Isaac 미발행/미재생 또는 "
                       f"RMW·DOMAIN 불일치. camera_publisher 로그 확인")
            else:
                L.warn(f"  ⚠ publisher {npub} 인데 수신 0 → QoS/타입 불일치 "
                       f"또는 Isaac 렌더프로덕트 미생성")


def main():
    import signal, traceback, sys

    _exit_reason = ["unknown"]

    def _sig_handler(signum, frame):
        _exit_reason[0] = f"signal {signal.Signals(signum).name}"
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGHUP,  _sig_handler)
    # SIGINT → KeyboardInterrupt 는 기존 except 에서 처리

    rclpy.init()
    node = VideoDegrade()
    _start = time.monotonic()
    try:
        _exit_reason[0] = "spin_normal_exit"
        rclpy.spin(node)
    except KeyboardInterrupt:
        _exit_reason[0] = "KeyboardInterrupt(SIGINT)"
    except SystemExit:
        pass  # _exit_reason already set by signal handler
    except Exception as exc:
        # WHY: spin()이 예외로 터지면 이전 코드는 이유 없이 종료.
        # 여기서 스택트레이스를 파일에 기록해 재발 시 원인 추적 가능.
        _exit_reason[0] = f"EXCEPTION: {exc!r}"
        tb = traceback.format_exc()
        _crash_path = f"/tmp/degrade_crash_{OUT_RGB.replace('/','_')}.log"
        try:
            with open(_crash_path, "w") as _f:
                _f.write(f"channel: {OUT_RGB}\n")
                _f.write(f"uptime: {time.monotonic()-_start:.1f}s\n")
                _f.write(f"exception: {exc!r}\n\n")
                _f.write(tb)
            print(f"[degrade CRASH] {exc!r} → {_crash_path}", file=sys.stderr, flush=True)
        except Exception:
            pass
    finally:
        _uptime = time.monotonic() - _start
        print(f"[degrade EXIT] channel={OUT_RGB} reason={_exit_reason[0]} "
              f"uptime={_uptime:.1f}s out={getattr(node,'_n_out',0)}frames",
              file=sys.stderr, flush=True)
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
