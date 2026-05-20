#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to data.yaml")
    parser.add_argument("--output", required=True, help="Destination path for best.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--base-model", default="yolov8n.pt")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics가 설치되지 않았습니다. 다음 명령으로 설치하세요:")
        print("  pip install ultralytics")
        sys.exit(1)

    data_yaml = Path(args.data)
    if not data_yaml.exists():
        print(f"data.yaml 파일을 찾을 수 없습니다: {data_yaml}")
        sys.exit(1)

    model = YOLO(args.base_model)
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name="deer_v1",
        exist_ok=True,
        patience=20,
        augment=True,
        amp=False,
    )

    best = Path("runs/detect/deer_v1/weights/best.pt")
    if not best.exists():
        # 같은 이름으로 두 번째 실행 시 deer_v12, deer_v13... 으로 생성됨
        candidates = sorted(Path("runs/detect").glob("deer_v1*/weights/best.pt"))
        if candidates:
            best = candidates[-1]

    if best.exists():
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best, output)
        print(f"\n모델 저장 완료: {output}")
    else:
        print("\nbest.pt를 찾을 수 없습니다. runs/detect/ 폴더를 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
