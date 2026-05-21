"""
fire_turret.py — weapon/fire ROS2 서비스 서버 + 총알 스폰 (Isaac Sim 내부 실행)

실행: camera_publisher.py 와 동일 환경(Isaac Sim python.sh)에서
      import 또는 직접 실행.

웹 → POST /robots/{rid}/fire → ros_bridge.fire() → weapon/fire 서비스 호출
→ 이 서버가 수신 → fire_bullet() → Bullet_N 스폰 + PhysX velocity
"""

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

from pxr import UsdGeom, UsdPhysics, Gf, Sdf
import omni.usd
import omni.timeline


TURRET_PATH  = '/World/go2/base/Go2_turret'
BULLET_RADIUS = 0.15   # m — 육안 식별용 큰 구체
BULLET_SPEED  = 20.0   # m/s
BULLET_MASS   = 0.5    # kg


def _next_bullet_path(stage) -> str:
    i = 0
    while stage.GetPrimAtPath(f'/World/Bullet_{i}').IsValid():
        i += 1
    return f'/World/Bullet_{i}'


def fire_bullet():
    """터렛 총구 방향으로 구체 1발 스폰. 시뮬레이션이 정지 상태면 자동 Play."""
    stage = omni.usd.get_context().get_stage()
    xform_cache = UsdGeom.XformCache(0)

    turret = stage.GetPrimAtPath(TURRET_PATH)
    if not turret.IsValid():
        print(f"[fire_turret] turret not found at {TURRET_PATH}")
        return False

    # 터렛 월드 행렬 → 총구 방향 (로컬 -X = Go2 전방)
    mat = xform_cache.GetLocalToWorldTransform(turret)
    turret_pos  = Gf.Vec3d(mat[3][0], mat[3][1], mat[3][2])
    local_x     = Gf.Vec3d(mat[0][0], mat[0][1], mat[0][2])
    barrel_dir  = (-local_x).GetNormalized()

    spawn_pos   = turret_pos + barrel_dir * (BULLET_RADIUS + 0.4)

    bullet_path = _next_bullet_path(stage)

    sphere = UsdGeom.Sphere.Define(stage, bullet_path)
    sphere.GetRadiusAttr().Set(BULLET_RADIUS)
    sphere.GetDisplayColorAttr().Set([Gf.Vec3f(1.0, 0.15, 0.15)])

    prim = sphere.GetPrim()
    xfm  = UsdGeom.Xformable(prim)
    xfm.AddTranslateOp().Set(spawn_pos)

    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.CollisionAPI.Apply(prim)
    mass_api = UsdPhysics.MassAPI.Apply(prim)
    mass_api.GetMassAttr().Set(BULLET_MASS)

    vel = prim.CreateAttribute('physics:velocity',
                               Sdf.ValueTypeNames.Vector3f, False)
    vel.Set(Gf.Vec3f(*(barrel_dir * BULLET_SPEED)))

    # 시뮬레이션이 정지 상태면 Play
    tl = omni.timeline.get_timeline_interface()
    if not tl.is_playing():
        tl.play()

    print(f"[fire_turret] fired {bullet_path}  pos={spawn_pos}  dir={barrel_dir}")
    return True


class FireTurretNode(Node):
    """weapon/fire Trigger 서비스 서버."""

    def __init__(self):
        super().__init__('fire_turret_node')
        self._srv = self.create_service(
            Trigger, 'weapon/fire', self._on_fire)
        self.get_logger().info('weapon/fire 서비스 준비 완료')

    def _on_fire(self, request, response):
        ok = fire_bullet()
        response.success = ok
        response.message = 'fired' if ok else 'turret not found'
        return response


def main():
    rclpy.init()
    node = FireTurretNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
