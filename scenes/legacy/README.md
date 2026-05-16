# scenes/legacy — 아카이브 (워크하우스 M1/M2 시절)

이 폴더의 파일들은 cobot3 **초기 "창고 분류(conveyor + bins + m0609×4 sorting)"
스코프**의 씬 빌더로, 현행 **GP 경계근무 4족+m0609** 스코프와 무관하다.
이력·참고용으로만 보존(삭제 안 함). 현행 작업엔 사용하지 않는다.

| 파일 | 용도(레거시) | 현행 대체 |
|---|---|---|
| `build_m1.py` | M1 오케스트레이터(conveyor+bins+r0+spawn) | — (GP 는 `main_side/camera_publisher.py` 가 씬 구성) |
| `build_og_factory.py` | r0~r3 멀티로봇 OG(joint/tf) | GP 단일로봇 OG = camera_publisher 내 fresh OG |
| `setup_conveyor.py` | 키네매틱 벨트 | GP 미사용 |
| `setup_bins.py` | 분류 bin 3종 | GP 미사용 |
| `setup_robot_r0.py` | `/World/Robots/r0/m0609` 배치 | GP prim 규약 `/World/Robot/m0609` 상이 |
| `setup_spawn_box.py` | 테스트 박스 스폰 | GP 미사용 |
| `setup_cameras.py` | 오버헤드 카메라 | GP = m0609 `link_6` 플랜지 RealSense |

**현행(GP) 유지 파일**(상위 `scenes/`):
`__init__.py`, `setup_ground_and_physics.py`(범용 물리, GP 재사용).

권위 설계: `../../dev-docs/gp-quadruped-system-design.md`.
