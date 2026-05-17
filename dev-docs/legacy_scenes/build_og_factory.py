"""M2 §2: OmniGraph ROS 2 bridge factory.

로봇당 1 그래프. M2 는 r0 만. M6 에서 r1-r3 확장.

그래프 노드 (per robot):
  OnPlaybackTick → ROS2Context
  IsaacArticulationState → ROS2PublishJointState  (/{rid}/joint_states)
  ROS2SubscribeJointState → IsaacArticulationController (/{rid}/joint_command)
  ROS2PublishTransformTree (/tf)
  IsaacCreateRenderProduct → ROS2CameraHelper (/{rid}/cam/conveyor/image_raw)

ROS_DOMAIN_ID = 130 (cobot3 표준)
"""
import omni.graph.core as og


ROS_DOMAIN_ID = 130

# M2: r0 만. M6 에서 ["r0","r1","r2","r3"]
ROBOT_IDS = ["r0"]


def run() -> str:
    keys = og.Controller.Keys
    built = []

    for rid in ROBOT_IDS:
        robot_prim = f"/World/Robots/{rid}/m0609"
        camera_prim = f"/World/Cameras/{rid}_overhead"
        graph_path = f"/World/Graphs/{rid}_bridge"

        og.Controller.edit(
            {"graph_path": graph_path, "evaluator_name": "execution"},
            {
                keys.CREATE_NODES: [
                    ("Tick", "omni.graph.action.OnPlaybackTick"),
                    ("Ctx", "isaacsim.ros2.bridge.ROS2Context"),
                    ("ArtState", "isaacsim.core.nodes.IsaacArticulationState"),
                    ("PubJoint", "isaacsim.ros2.bridge.ROS2PublishJointState"),
                    ("SubJointCmd", "isaacsim.ros2.bridge.ROS2SubscribeJointState"),
                    ("ArtCtrl", "isaacsim.core.nodes.IsaacArticulationController"),
                    ("PubTF", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                    ("CreateRP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                    ("CamHelper", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                ],
                keys.SET_VALUES: [
                    ("Ctx.inputs:domain_id", ROS_DOMAIN_ID),
                    ("ArtState.inputs:targetPrim", robot_prim),
                    ("PubJoint.inputs:topicName", f"/{rid}/joint_states"),
                    ("PubJoint.inputs:targetPrim", robot_prim),
                    ("SubJointCmd.inputs:topicName", f"/{rid}/joint_command"),
                    ("ArtCtrl.inputs:targetPrim", robot_prim),
                    ("PubTF.inputs:parentPrim", f"{robot_prim}/base_link"),
                    ("PubTF.inputs:targetPrims", [robot_prim]),
                    ("CreateRP.inputs:cameraPrim", camera_prim),
                    ("CreateRP.inputs:width", 1280),
                    ("CreateRP.inputs:height", 720),
                    ("CamHelper.inputs:topicName", f"/{rid}/cam/conveyor/image_raw"),
                    ("CamHelper.inputs:frameId", f"{rid}_camera"),
                    ("CamHelper.inputs:type", "rgb"),
                ],
                keys.CONNECT: [
                    ("Tick.outputs:tick", "ArtState.inputs:execIn"),
                    ("Tick.outputs:tick", "PubJoint.inputs:execIn"),
                    ("Tick.outputs:tick", "SubJointCmd.inputs:execIn"),
                    ("Tick.outputs:tick", "PubTF.inputs:execIn"),
                    ("Tick.outputs:tick", "CreateRP.inputs:execIn"),
                    ("Ctx.outputs:context", "PubJoint.inputs:context"),
                    ("Ctx.outputs:context", "SubJointCmd.inputs:context"),
                    ("Ctx.outputs:context", "PubTF.inputs:context"),
                    ("Ctx.outputs:context", "CamHelper.inputs:context"),
                    ("ArtState.outputs:jointPositions", "PubJoint.inputs:jointPositions"),
                    ("ArtState.outputs:jointVelocities", "PubJoint.inputs:jointVelocities"),
                    ("ArtState.outputs:jointNames", "PubJoint.inputs:jointNames"),
                    ("SubJointCmd.outputs:positionCommand", "ArtCtrl.inputs:positionCommand"),
                    ("SubJointCmd.outputs:jointNames", "ArtCtrl.inputs:jointNames"),
                    ("CreateRP.outputs:execOut", "CamHelper.inputs:execIn"),
                    ("CreateRP.outputs:renderProductPath", "CamHelper.inputs:renderProductPath"),
                ],
            },
        )
        built.append(rid)

    return f"OG bridges built: {built}"


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run())
    app.close()
