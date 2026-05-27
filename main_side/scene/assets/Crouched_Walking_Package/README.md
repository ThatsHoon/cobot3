# Crouched Walking — Isaac Sim Character Package

Mixamo 캐릭터 (Ch49) + Crouched Walking 애니메이션
Isaac Sim 5.x 용 USD 패키지

---

## 폴더 구조

```
Crouched_Walking_Package/
├── README.md                              ← 이 파일
├── Crouched Walking.usd                   ← 메인 파일 (여기를 Isaac Sim에서 열기)
│
├── props/
│   └── Crouched Walking_props.usd         ← 캐릭터 메시 + 스켈레톤
│
├── animations/
│   ├── Crouched Walking_mixamo_com_anim.usd   ← 실제 애니메이션 데이터
│   └── Crouched Walking_take_001_anim.usd     ← 예비 트랙 (비어있음)
│
└── textures/
    ├── Ch49_1001_Diffuse.png
    ├── Ch49_1001_Glossiness.png
    ├── Ch49_1001_Normal.png
    ├── Ch49_1002_Diffuse.png
    ├── Ch49_1002_Glossiness.png
    └── Ch49_1002_Normal.png
```

> **주의**: 폴더 구조를 변경하면 상대경로가 깨져 텍스처/메시가 로드되지 않습니다.

---

## 사용 방법

1. Isaac Sim 실행
2. `File → Open` 또는 Content Browser에서 `Crouched Walking.usd` 열기
3. 상단 타임라인 **▶ Play** 버튼 클릭

---

## 애니메이션 정보

| 항목 | 값 |
|------|-----|
| 캐릭터 | Mixamo Ch49 |
| 애니메이션 | Crouched Walking |
| 프레임 수 | 31 frames |
| 시간 범위 | 0 – 60 timecodes (60 fps, 약 1초 루프) |
| 조인트 수 | 65 |
