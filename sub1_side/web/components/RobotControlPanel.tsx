"use client";
import InspectorCameraPanel from "./InspectorCameraPanel";
import BaseMovementPanel from "./BaseMovementPanel";

/** ROBOT CONTROL 컨테이너 — INSPECT(EO turret) 와 MOVE(DPad) 를 좌우 병렬로 배치.
 *  각 sub 의 ⚙ popover 는 자체 보유. */
export default function RobotControlPanel() {
  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>ROBOT CONTROL</span>
        <span className="panel-idx">ROB/03</span>
      </div>
      <div className="grid grid-cols-2 divide-x divide-line flex-1">
        <InspectorCameraPanel bare />
        <BaseMovementPanel bare />
      </div>
    </div>
  );
}
