# main_side/scene — GP 씬 + 동봉 에셋 (이식 가능)

`camera_publisher.py` 가 여는 GP 씬과 그 **로컬화된 의존 에셋 전부**.
다른 PC 에서 cobot3 repo 만 clone 하면 (Isaac Sim 설치 전제 하에)
**추가 외부 파일 없이** 씬을 열어 작업을 이어갈 수 있다.

## 구조

```
scene/
├── gp_scene.usd                 루트 씬 (모든 참조 = 이 폴더 상대경로)
├── assets/
│   ├── terrain.usdz             지형 (구 ~/Downloads BRUMA, 텍스처 usdz 내장)
│   ├── barbed_wire_fence.usdz   철조망 (Fence 124 세그가 참조)
│   └── m0609.usd                m0609 로봇팔 (src/doosan-robot2/usd/m0609.usd)
└── textures/
    ├── Fence003/  *_Color/_NormalGL/_Roughness/_Opacity.png   (철조망 PBR)
    └── Snow010A/  *_Color/_NormalGL/_Roughness.png            (눈 PBR)
```

prim: `/World/Terrain`, `/World/Robot/m0609`, `/World/Robot/anymal`,
`/World/Fence/seg_0..123` — `camera_publisher.py` 의 m0609/anymal prim
규약(`/World/Robot/...`)과 일치.

## 이식성 계약 (다른 PC 에서 이어가기)

- `gp_scene.usd` 의 모든 asset path 는 **이 폴더 기준 상대경로** 로
  재작성됨(절대경로·`~/Downloads` 의존 제거). repo 통째 이동/clone 시
  경로 수정 불필요.
- `camera_publisher.py` 의 `GP_SCENE` 기본값 = 스크립트 상대
  `main_side/scene/gp_scene.usd` (하드코딩 없음). 다른 씬은
  `GP_SCENE=/경로/x.usd` 로 오버라이드.
- **예외 2건(파일 아님 — 정상)**:
  1. `OmniPBR.mdl` 등 코어 MDL: Isaac/RTX 런타임이 이름으로 해석.
     Isaac Sim 이 설치된 PC 면 자동 해결(본 프로젝트 전제).
  2. `/World/Robot/anymal` → Omniverse 공개 S3 URL
     (`…/Isaac/5.1/…/anymal_c/anymal_c.usd`). Isaac 표준 로봇이라
     동봉하지 않음 — **씬 최초 로드시 인터넷 필요**(이후 Isaac 자산
     캐시). 오프라인 필요 시 이 URL 을 로컬 다운로드본으로 교체.

## 재생성 (참고)

원본은 `/home/rokey/dev_ws/gp_scene.usd`(절대/원격 참조) 였고, 의존
폐포를 이 폴더로 로컬화 + `UsdUtils.ModifyAssetPaths` 로 상대경로 재작성해
생성. 자세한 경위: `../../dev-docs/project_requirments.md`,
`../../dev-docs/gp-quadruped-system-design.md` Appendix-D.
