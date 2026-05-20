const WORLD_MIN = -40;
const WORLD_MAX = 40;
const WORLD_SIZE = WORLD_MAX - WORLD_MIN;
// 로봇 스폰 위치 world y=-12.0 이지만 odom은 스폰 기준 (0,0) 시작.
// 지도 표시 시 odom y + SPAWN_Y_OFFSET = world y 로 변환.
const SPAWN_Y_OFFSET = -12;
const ROSBRIDGE_URL = "ws://localhost:9090";

const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");
const connectionBadge = document.getElementById("connectionBadge");
const modeText = document.getElementById("modeText");
const positionText = document.getElementById("positionText");
const yawText = document.getElementById("yawText");
const waypointText = document.getElementById("waypointText");
const alertBlock = document.getElementById("alertBlock");
const alertText = document.getElementById("alertText");
const eventLog = document.getElementById("eventLog");

const state = {
  connected: false,
  robot: { x: 0, y: 0, yaw: 0 },
  home: { x: 0, y: 0 },
  waypoint: null,
  mode: "IDLE",
  trail: [],
  route: [],
  intruders: [],
  selectedTargetId: null,
  confirmedTargetIds: new Set(),
  lastTargetPositions: new Map(),
  lastDetection: null,
  lastIntruderStateTime: 0,
  lastAlert: null,
  lastAlertTime: 0,
  lastDeerAlert: null,
  lastDeerAlertTime: 0,
  deerDots: [],
  selectedDeerDotId: null,
  intruderDots: [],
  selectedIntruderDotId: null,
  personDots: [],
  selectedPersonDotId: null,
};

let socket = null;
let inspectionZoom = 1.0;
const INSPECTION_ZOOM_STEP = 1.4;
const INSPECTION_ZOOM_MAX = 6.0;
const INSPECTION_ZOOM_MIN = 1.0;

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function worldToCanvas(x, y) {
  const rect = canvas.getBoundingClientRect();
  const padding = 28;
  const usableW = rect.width - padding * 2;
  const usableH = rect.height - padding * 2;
  return {
    x: padding + ((x - WORLD_MIN) / WORLD_SIZE) * usableW,
    y: padding + (1 - (y - WORLD_MIN) / WORLD_SIZE) * usableH,
  };
}

function logEvent(text) {
  const item = document.createElement("li");
  const time = new Date().toLocaleTimeString();
  item.textContent = `[${time}] ${text}`;
  eventLog.appendChild(item);
  while (eventLog.children.length > 14) {
    eventLog.removeChild(eventLog.firstChild);
  }
}

function setConnection(connected) {
  state.connected = connected;
  connectionBadge.textContent = connected ? "ROSBRIDGE ONLINE" : "ROSBRIDGE OFFLINE";
  connectionBadge.className = `badge ${connected ? "online" : "offline"}`;
}

function connectRosbridge() {
  socket = new WebSocket(ROSBRIDGE_URL);

  socket.addEventListener("open", () => {
    setConnection(true);
    logEvent("rosbridge connected");
    subscribe("/odom", "nav_msgs/Odometry");
    subscribe("/alerts", "std_msgs/String");
    subscribe("/deer_alerts", "std_msgs/String");
    subscribe("/patrol_state", "std_msgs/String");
    subscribe("/intruder_states", "std_msgs/String");
    advertise("/mission_command", "std_msgs/String");
    advertise("/inspection_camera/command", "std_msgs/String");
    sendPacket({ op: "subscribe", topic: "/camera/image_raw/compressed", type: "sensor_msgs/CompressedImage", throttle_rate: 150 });
    sendPacket({ op: "subscribe", topic: "/inspection_camera/image_raw/compressed", type: "sensor_msgs/CompressedImage", throttle_rate: 150 });
  });

  socket.addEventListener("close", () => {
    setConnection(false);
    logEvent("rosbridge disconnected; retrying");
    setTimeout(connectRosbridge, 1600);
  });

  socket.addEventListener("error", () => {
    setConnection(false);
  });

  socket.addEventListener("message", (event) => {
    const packet = JSON.parse(event.data);
    if (packet.op !== "publish") {
      return;
    }
    if (packet.topic === "/odom") {
      handleOdom(packet.msg);
    } else if (packet.topic === "/alerts") {
      handleAlert(packet.msg);
    } else if (packet.topic === "/deer_alerts") {
      handleDeerAlert(packet.msg);
    } else if (packet.topic === "/patrol_state") {
      handlePatrolState(packet.msg);
    } else if (packet.topic === "/intruder_states") {
      handleIntruderStates(packet.msg);
    } else if (packet.topic === "/camera/image_raw/compressed") {
      handleCameraImage(packet.msg, "cameraFeed", "cameraStatus");
    } else if (packet.topic === "/inspection_camera/image_raw/compressed") {
      handleCameraImage(packet.msg, "inspectionFeed", "inspectionStatus");
    }
  });
}

function sendPacket(packet) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    logEvent("rosbridge is not connected");
    return;
  }
  socket.send(JSON.stringify(packet));
}

function subscribe(topic, type) {
  sendPacket({ op: "subscribe", topic, type });
}

function advertise(topic, type) {
  sendPacket({ op: "advertise", topic, type });
}

function publishMission(command) {
  sendPacket({
    op: "publish",
    topic: "/mission_command",
    msg: { data: command },
  });
  logEvent(`mission command: ${command}`);
}

function publishInspectionCommand(payload) {
  sendPacket({
    op: "publish",
    topic: "/inspection_camera/command",
    msg: { data: JSON.stringify(payload) },
  });
}

const INSPECTION_TARGET_FOCAL = 70.0; // mm — auto-zoom when a target is selected (~2x)

function selectTarget(intruder) {
  state.selectedDeerDotId = null;
  state.selectedIntruderDotId = null;
  state.selectedPersonDotId = null;
  const id = intruder.id ?? 0;
  state.selectedTargetId = id;
  const x = Number(intruder.x || 0);
  const y = Number(intruder.y || 0);
  const z = Number(intruder.z || 0) + 1.35;
  publishInspectionCommand({
    action: "look_at",
    target_id: id,
    label: `unidentified target ${Number(id) + 1}`,
    x, y, z,
    focal_length: INSPECTION_TARGET_FOCAL,
  });
  logEvent(`inspection camera → intruder x=${x.toFixed(1)} y=${y.toFixed(1)}`);
}

function selectIntruderDot(dot) {
  state.selectedTargetId = null;
  state.selectedDeerDotId = null;
  state.selectedPersonDotId = null;
  state.selectedIntruderDotId = dot.id;
  publishInspectionCommand({
    action: "look_at",
    target_id: `intruder_dot_${dot.id}`,
    label: "intruder (last known)",
    x: dot.x,
    y: dot.y,
    z: 1.5,
    focal_length: INSPECTION_TARGET_FOCAL,
  });
  logEvent(`inspection camera → intruder(dot) x=${dot.x.toFixed(1)} y=${dot.y.toFixed(1)}`);
}

function selectDeerTarget(dot) {
  state.selectedTargetId = null;
  state.selectedIntruderDotId = null;
  state.selectedPersonDotId = null;
  state.selectedDeerDotId = dot.id;
  publishInspectionCommand({
    action: "look_at",
    target_id: `deer_${dot.id}`,
    label: "deer",
    x: Number(dot.x),
    y: Number(dot.y),
    z: 1.0,
    focal_length: INSPECTION_TARGET_FOCAL,
  });
  logEvent(`inspection camera → 사슴 x=${dot.x.toFixed(1)} y=${dot.y.toFixed(1)}`);
}

function selectPersonDot(dot) {
  state.selectedTargetId = null;
  state.selectedDeerDotId = null;
  state.selectedIntruderDotId = null;
  state.selectedPersonDotId = dot.id;
  publishInspectionCommand({
    action: "look_at",
    target_id: `person_${dot.id}`,
    label: "person (YOLO)",
    x: dot.x,
    y: dot.y,
    z: 1.5,
    focal_length: INSPECTION_TARGET_FOCAL,
  });
  logEvent(`inspection camera → 사람 x=${dot.x.toFixed(1)} y=${dot.y.toFixed(1)}`);
}

function applyInspectionZoom() {
  const feed = document.getElementById("inspectionFeed");
  if (!feed) return;
  feed.style.transform = inspectionZoom === 1.0 ? "" : `scale(${inspectionZoom})`;
  feed.style.transformOrigin = "center center";
}

function publishZoom(action) {
  if (action === "zoom_in") {
    inspectionZoom = Math.min(INSPECTION_ZOOM_MAX, inspectionZoom * INSPECTION_ZOOM_STEP);
  } else if (action === "zoom_out") {
    inspectionZoom = Math.max(INSPECTION_ZOOM_MIN, inspectionZoom / INSPECTION_ZOOM_STEP);
  } else if (action === "zoom_reset" || action === "clear") {
    inspectionZoom = 1.0;
  }
  applyInspectionZoom();
  publishInspectionCommand({ action });
  logEvent(`inspection camera: ${action} (x${inspectionZoom.toFixed(1)})`);
}

function publishInspectionMove(action) {
  publishInspectionCommand({ action });
  state.selectedTargetId = null;
  logEvent(`inspection camera manual: ${action}`);
}

function yawFromQuaternion(q) {
  const sinyCosp = 2 * (q.w * q.z + q.x * q.y);
  const cosyCosp = 1 - 2 * (q.y * q.y + q.z * q.z);
  return Math.atan2(sinyCosp, cosyCosp);
}

// Front camera is fixed facing world +Y (toward fence, north direction).
// FRONT_CAMERA_ORIENTATION_IJKR = (0.7071,0,0,0.7071) → always points along robot body +Y = world +Y.
// Camera params: focal_length=18mm, horizontal_aperture=21mm → HFOV = 2*atan(21/36) ≈ 60.5°
// Objects spawn near the fence: fence_y-1.5 ~ fence_y+2.8 = world Y 14.5~18.8
const FENCE_WORLD_Y = 16.0;
const CAMERA_HFOV_RAD = 2 * Math.atan(21 / (2 * 18)); // ≈ 1.057 rad (60.5°)

function estimateDetectionWorldPos(payload) {
  const robotX = payload ? Number(payload.robot_x ?? state.robot.x) : state.robot.x;
  const robotY = (payload ? Number(payload.robot_y ?? state.robot.y) : state.robot.y) + SPAWN_Y_OFFSET;

  // camera always faces +Y; project to ~1.5 m inside the fence
  const depth = Math.max(1.0, FENCE_WORLD_Y - robotY - 1.5);
  let detX = robotX;
  let detY = robotY + depth; // ≈ FENCE_WORLD_Y - 1.5 = 14.5

  if (payload) {
    const bbox = payload.bbox_xyxy;
    const imgW = Number(payload.image_width);
    if (Array.isArray(bbox) && bbox.length >= 4 && imgW > 0) {
      const bboxCenterNorm = (bbox[0] + bbox[2]) / 2 / imgW - 0.5;
      // camera faces +Y → lateral direction is +X
      detX += depth * Math.tan(bboxCenterNorm * CAMERA_HFOV_RAD);
    }
  }

  return { x: detX, y: detY };
}

function handleOdom(msg) {
  const pose = msg.pose.pose;
  state.robot.x = pose.position.x;
  state.robot.y = pose.position.y;
  state.robot.yaw = yawFromQuaternion(pose.orientation);
  state.trail.push({ x: state.robot.x, y: state.robot.y });
  if (state.trail.length > 160) {
    state.trail.shift();
  }
}

const _lastCameraTs = { cameraFeed: 0, inspectionFeed: 0 };
function handleCameraImage(msg, feedId, statusId) {
  const now = Date.now();
  if (now - (_lastCameraTs[feedId] || 0) < 100) return;
  _lastCameraTs[feedId] = now;
  const feed = document.getElementById(feedId);
  const status = document.getElementById(statusId);
  if (!feed || !status) return;
  feed.src = "data:image/jpeg;base64," + msg.data;
  status.textContent = "LIVE";
  status.classList.add("live");
}

function handleAlert(msg) {
  let summary = msg.data;
  let confidence = 0;
  let payload = null;
  try {
    payload = JSON.parse(msg.data);
    confidence = Number(payload.confidence || 0);
    state.lastDetection = {
      confidence,
      count: Number(payload.count || 1),
      time: Date.now(),
    };
    summary = `${payload.event || "person_detected"} confidence=${confidence.toFixed(2)} count=${payload.count || 1}`;
  } catch (error) {}
  state.lastAlert = summary;
  state.lastAlertTime = Date.now();
  logEvent(`ALERT ${summary}`);

  if (confidence >= 0.50) {
    const { x: detX, y: detY } = estimateDetectionWorldPos(payload);
    const MERGE_RADIUS = 4.0;
    const existing = state.personDots.find(
      (d) => Math.hypot(d.x - detX, d.y - detY) < MERGE_RADIUS
    );
    if (existing) {
      existing.x = detX;
      existing.y = detY;
      existing.time = Date.now();
      existing.confidence = confidence;
    } else {
      const t = Date.now();
      state.personDots.push({ id: t, x: detX, y: detY, time: t, confidence });
      logEvent(`🧍 사람 감지 conf=${confidence.toFixed(2)}`);
    }
  }
}

function handleDeerAlert(msg) {
  let confidence = 0;
  let payload = null;
  try {
    payload = JSON.parse(msg.data);
    confidence = Number(payload.confidence || 0);
  } catch (e) {}

  if (confidence < 0.50) return;

  state.lastDeerAlert = `사슴 감지 confidence=${confidence.toFixed(2)}`;
  state.lastDeerAlertTime = Date.now();

  const { x: detX, y: detY } = estimateDetectionWorldPos(payload);
  const MERGE_RADIUS = 4.0;
  const existing = state.deerDots.find(
    (d) => Math.hypot(d.x - detX, d.y - detY) < MERGE_RADIUS
  );
  if (existing) {
    existing.x = detX;
    existing.y = detY;
    existing.time = Date.now();
  } else {
    const t = Date.now();
    state.deerDots.push({ id: t, x: detX, y: detY, time: t });
    logEvent(`🦌 사슴 감지 conf=${confidence.toFixed(2)}`);
  }
}

function handleIntruderStates(msg) {
  try {
    const payload = JSON.parse(msg.data);
    const nextIntruders = Array.isArray(payload.intruders) ? payload.intruders : [];
    const seenIds = new Set();
    nextIntruders.forEach((intruder) => {
      const id = Number(intruder.id ?? 0);
      seenIds.add(id);
      const x = Number(intruder.x || 0);
      const y = Number(intruder.y || 0);
      const previous = state.lastTargetPositions.get(id);
      if (previous) {
        const movedDistance = Math.hypot(x - previous.x, y - previous.y);
        if (movedDistance > 6.0) {
          state.confirmedTargetIds.delete(id);
          if (state.selectedTargetId === id) {
            state.selectedTargetId = null;
          }
          logEvent(`target respawned: unidentified target ${id + 1}`);
        }
      }
      state.lastTargetPositions.set(id, { x, y });
    });
    Array.from(state.lastTargetPositions.keys()).forEach((id) => {
      if (!seenIds.has(id)) {
        state.lastTargetPositions.delete(id);
        state.confirmedTargetIds.delete(id);
      }
    });
    // 침입자 persistent dot 갱신 (5m 이내 기존 dot 업데이트, 없으면 신규 생성)
    const INTRUDER_MERGE_RADIUS = 5.0;
    nextIntruders.forEach((intruder) => {
      const x = Number(intruder.x || 0);
      const y = Number(intruder.y || 0);
      const existing = state.intruderDots.find(d => Math.hypot(d.x - x, d.y - y) < INTRUDER_MERGE_RADIUS);
      if (existing) {
        existing.x = x;
        existing.y = y;
        existing.time = Date.now();
      } else {
        const t = Date.now();
        state.intruderDots.push({ id: t, x, y, time: t });
        logEvent(`⚠ intruder dot: x=${x.toFixed(1)} y=${y.toFixed(1)}`);
      }
    });

    state.intruders = nextIntruders;
    if (
      state.selectedTargetId !== null &&
      !state.intruders.some((intruder) => intruder.id === state.selectedTargetId)
    ) {
      state.selectedTargetId = null;
    }
    state.lastIntruderStateTime = Date.now();
  } catch (error) {
    logEvent("failed to parse intruder states");
  }
}

function handlePatrolState(msg) {
  try {
    const payload = JSON.parse(msg.data);
    state.mode = payload.mode || state.mode;
    state.waypoint = payload.waypoint || payload.target || state.waypoint;
    state.home = payload.home || state.home;
    state.route = Array.isArray(payload.route) ? payload.route : [];
    if (payload.pose) {
      state.robot.x = payload.pose.x;
      state.robot.y = payload.pose.y;
      state.robot.yaw = payload.pose.yaw;
    }
  } catch (error) {
    state.mode = msg.data;
  }
}

function drawGrid(rect) {
  ctx.strokeStyle = "rgba(54, 244, 154, 0.13)";
  ctx.lineWidth = 1;
  for (let meter = WORLD_MIN; meter <= WORLD_MAX; meter += 10) {
    const a = worldToCanvas(meter, WORLD_MIN);
    const b = worldToCanvas(meter, WORLD_MAX);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();

    const c = worldToCanvas(WORLD_MIN, meter);
    const d = worldToCanvas(WORLD_MAX, meter);
    ctx.beginPath();
    ctx.moveTo(c.x, c.y);
    ctx.lineTo(d.x, d.y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(54, 244, 154, 0.42)";
  ctx.strokeRect(28, 28, rect.width - 56, rect.height - 56);
}

function drawWorldLine(points, color, width = 2, dash = []) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.beginPath();
  points.forEach((point, index) => {
    const px = worldToCanvas(point.x, point.y);
    if (index === 0) {
      ctx.moveTo(px.x, px.y);
    } else {
      ctx.lineTo(px.x, px.y);
    }
  });
  ctx.stroke();
  ctx.restore();
}

function drawWorldRect(xMin, yMin, xMax, yMax, fill, stroke) {
  const a = worldToCanvas(xMin, yMax);
  const b = worldToCanvas(xMax, yMin);
  ctx.fillStyle = fill;
  ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
  }
}

function drawMarker(x, y, label, color) {
  const p = worldToCanvas(x, y);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(200, 246, 223, 0.86)";
  ctx.font = "12px monospace";
  ctx.fillText(label, p.x + 9, p.y - 8);
}

function drawIntruderMarker(intruder) {
  const p = worldToCanvas(Number(intruder.x || 0), Number(intruder.y || 0));
  const id = Number(intruder.id ?? 0);
  const label = `Unidentified target ${id + 1}`;
  const selected = state.selectedTargetId === intruder.id;
  const confirmed = state.confirmedTargetIds.has(id);
  const detectionFresh = state.lastDetection && Date.now() - state.lastDetection.time < 4500;
  ctx.save();
  ctx.fillStyle = confirmed
    ? "rgba(54, 244, 154, 0.92)"
    : detectionFresh
      ? "rgba(255, 82, 82, 0.95)"
      : "rgba(255, 141, 58, 0.9)";
  ctx.strokeStyle = selected ? "rgba(58, 216, 255, 0.95)" : "rgba(255, 214, 128, 0.88)";
  ctx.lineWidth = selected ? 3 : 2;
  ctx.beginPath();
  ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  if (detectionFresh || selected) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 15 + 3 * Math.sin(Date.now() / 220), 0, Math.PI * 2);
    ctx.strokeStyle = selected ? "rgba(58, 216, 255, 0.32)" : "rgba(255, 82, 82, 0.28)";
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(255, 214, 128, 0.94)";
  ctx.font = "12px monospace";
  ctx.fillText(label, p.x + 11, p.y - 10);
  ctx.fillStyle = "rgba(200, 246, 223, 0.76)";
  ctx.fillText(`x ${Number(intruder.x || 0).toFixed(1)} / y ${Number(intruder.y || 0).toFixed(1)}`, p.x + 11, p.y + 4);
  if (confirmed) {
    ctx.fillStyle = "rgba(54, 244, 154, 0.92)";
    ctx.fillText("CONFIRMED", p.x + 11, p.y + 18);
  }
  if (selected) {
    ctx.fillStyle = "rgba(58, 216, 255, 0.92)";
    ctx.fillText("INSPECTION CAMERA", p.x + 11, p.y + (confirmed ? 32 : 18));
  }
  ctx.restore();
}

function drawMap() {
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#020706";
  ctx.fillRect(0, 0, rect.width, rect.height);

  drawGrid(rect);
  drawWorldRect(WORLD_MIN, 21, WORLD_MAX, WORLD_MAX, "rgba(30, 104, 142, 0.24)", "rgba(58, 216, 255, 0.22)");
  drawWorldLine([{ x: WORLD_MIN, y: 16 }, { x: WORLD_MAX, y: 16 }], "rgba(230, 198, 75, 0.88)", 3);
  drawWorldLine([{ x: WORLD_MIN + 5, y: 10 }, { x: WORLD_MAX - 5, y: 10 }], "rgba(140, 105, 52, 0.88)", 4, [10, 7]);

  const homeWorldY = state.home.y + SPAWN_Y_OFFSET;
  drawWorldLine([{ x: state.home.x, y: homeWorldY }, { x: state.home.x, y: homeWorldY }], "rgba(58, 216, 255, 0.35)", 2, [5, 8]);

  drawMarker(state.home.x, homeWorldY, "HOME", "rgba(58, 216, 255, 0.95)");
  drawMarker(-24.8, 10, "Tower W", "rgba(230, 198, 75, 0.95)");
  drawMarker(24.8, 10, "Tower E", "rgba(230, 198, 75, 0.95)");
  drawMarker(-12.8, 8.8, "Bunker", "rgba(150, 180, 150, 0.95)");
  drawMarker(6.4, 7.8, "Bunker", "rgba(150, 180, 150, 0.95)");

  if (state.trail.length > 1) {
    const trailW = state.trail.map(p => ({ x: p.x, y: p.y + SPAWN_Y_OFFSET }));
    drawWorldLine(trailW, "rgba(58, 216, 255, 0.52)", 2);
  }

  if (state.waypoint) {
    const wpW = { x: state.waypoint.x, y: state.waypoint.y + SPAWN_Y_OFFSET };
    drawMarker(wpW.x, wpW.y, "Patrol WP", "rgba(255, 141, 58, 0.95)");
    if (state.route.length > 0) {
      const routeW = state.route.map(p => ({ x: p.x, y: p.y + SPAWN_Y_OFFSET }));
      drawWorldLine([wpW, ...routeW], "rgba(255, 141, 58, 0.55)", 2, [7, 7]);
    }
  }

  const nowMs = Date.now();

  // 침입자 persistent dot (live intruder 없는 위치만 표시, 120초 유지)
  state.intruderDots = state.intruderDots.filter(d => nowMs - d.time < 120000);
  if (state.selectedIntruderDotId !== null && !state.intruderDots.some(d => d.id === state.selectedIntruderDotId)) {
    state.selectedIntruderDotId = null;
    publishZoom("clear");
  }
  state.intruderDots.forEach(dot => {
    const hasLive = state.intruders.some(i => Math.hypot(Number(i.x) - dot.x, Number(i.y) - dot.y) < 3.0);
    if (hasLive) return;
    const age = (nowMs - dot.time) / 120000;
    const alpha = Math.max(0.12, 1 - age * 0.88);
    const p = worldToCanvas(dot.x, dot.y);
    const selected = state.selectedIntruderDotId === dot.id;
    ctx.save();
    ctx.fillStyle = `rgba(255, 141, 58, ${alpha * 0.75})`;
    ctx.strokeStyle = selected ? "rgba(58, 216, 255, 0.95)" : `rgba(255, 141, 58, ${alpha})`;
    ctx.lineWidth = selected ? 2.5 : 1.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, selected ? 8 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (selected) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 16 + 3 * Math.sin(nowMs / 220), 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(58, 216, 255, 0.32)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    ctx.fillStyle = `rgba(255, 214, 128, ${alpha * 0.9})`;
    ctx.font = "12px monospace";
    ctx.fillText("⚠", p.x + 9, p.y + 4);
    if (selected) {
      ctx.fillStyle = "rgba(58, 216, 255, 0.92)";
      ctx.font = "11px monospace";
      ctx.fillText("INSPECTION CAMERA", p.x + 11, p.y + 18);
    }
    ctx.restore();
  });

  // 사슴 감지 이력 — 초록 점으로 표시 (120초 유지)
  state.deerDots = state.deerDots.filter(d => nowMs - d.time < 120000);
  if (state.selectedDeerDotId !== null && !state.deerDots.some(d => d.id === state.selectedDeerDotId)) {
    state.selectedDeerDotId = null;
    publishZoom("clear");
  }
  state.deerDots.forEach(dot => {
    const age = (nowMs - dot.time) / 120000;
    const alpha = Math.max(0.15, 1 - age * 0.85);
    const p = worldToCanvas(dot.x, dot.y);
    const selected = state.selectedDeerDotId === dot.id;
    ctx.save();
    ctx.fillStyle = `rgba(80, 220, 100, ${alpha})`;
    ctx.strokeStyle = selected ? "rgba(58, 216, 255, 0.95)" : "rgba(80, 220, 100, 0.6)";
    ctx.lineWidth = selected ? 2.5 : 1.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, selected ? 8 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (selected) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 16 + 3 * Math.sin(nowMs / 220), 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(58, 216, 255, 0.32)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    ctx.fillStyle = `rgba(180, 255, 180, ${alpha * 0.9})`;
    ctx.font = "11px monospace";
    ctx.fillText("🦌", p.x + 9, p.y + 4);
    if (selected) {
      ctx.fillStyle = "rgba(58, 216, 255, 0.92)";
      ctx.font = "11px monospace";
      ctx.fillText("INSPECTION CAMERA", p.x + 11, p.y + 18);
    }
    ctx.restore();
  });

  // YOLO 사람 감지 이력 — 빨간 점으로 표시 (120초 유지)
  state.personDots = state.personDots.filter((d) => nowMs - d.time < 120000);
  if (state.selectedPersonDotId !== null && !state.personDots.some((d) => d.id === state.selectedPersonDotId)) {
    state.selectedPersonDotId = null;
    publishZoom("clear");
  }
  state.personDots.forEach((dot) => {
    const age = (nowMs - dot.time) / 120000;
    const alpha = Math.max(0.15, 1 - age * 0.85);
    const p = worldToCanvas(dot.x, dot.y);
    const selected = state.selectedPersonDotId === dot.id;
    ctx.save();
    ctx.fillStyle = `rgba(255, 82, 82, ${alpha * 0.8})`;
    ctx.strokeStyle = selected ? "rgba(58, 216, 255, 0.95)" : `rgba(255, 82, 82, ${alpha})`;
    ctx.lineWidth = selected ? 2.5 : 1.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, selected ? 8 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (selected) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 16 + 3 * Math.sin(nowMs / 220), 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(58, 216, 255, 0.32)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    ctx.fillStyle = `rgba(255, 180, 180, ${alpha * 0.9})`;
    ctx.font = "14px monospace";
    ctx.fillText("🧍", p.x + 9, p.y + 5);
    if (selected) {
      ctx.fillStyle = "rgba(58, 216, 255, 0.92)";
      ctx.font = "11px monospace";
      ctx.fillText("INSPECTION CAMERA", p.x + 11, p.y + 20);
    }
    ctx.restore();
  });

  state.intruders.forEach(drawIntruderMarker);

  const robot = worldToCanvas(state.robot.x, state.robot.y + SPAWN_Y_OFFSET);
  const isAlert = Date.now() - state.lastAlertTime < 4500;
  ctx.save();
  ctx.translate(robot.x, robot.y);
  ctx.rotate(-state.robot.yaw);
  ctx.fillStyle = isAlert ? "#ff3b45" : "#3ad8ff";
  ctx.strokeStyle = "rgba(200, 246, 223, 0.85)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(13, 0);
  ctx.lineTo(-9, -8);
  ctx.lineTo(-6, 0);
  ctx.lineTo(-9, 8);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();

  if (isAlert) {
    ctx.strokeStyle = "rgba(255, 59, 69, 0.4)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(robot.x, robot.y, 22 + 8 * Math.sin(Date.now() / 160), 0, Math.PI * 2);
    ctx.stroke();
  }
}

function updateText() {
  modeText.textContent = state.mode;
  positionText.textContent = `x ${state.robot.x.toFixed(2)} / y ${state.robot.y.toFixed(2)}`;
  yawText.textContent = `${(state.robot.yaw * 180 / Math.PI).toFixed(1)} deg`;
  waypointText.textContent = state.waypoint
    ? `x ${state.waypoint.x.toFixed(1)} / y ${state.waypoint.y.toFixed(1)}`
    : "none";

  const alertActive = Date.now() - state.lastAlertTime < 4500;
  const deerActive = Date.now() - state.lastDeerAlertTime < 4500;

  if (alertActive) {
    alertBlock.classList.add("active");
    alertBlock.style.borderColor = "";
    alertBlock.style.backgroundColor = "";
    if (state.lastAlert) {
      const targetSummary = state.intruders.length
        ? ` | ${state.intruders.length} target(s) on map`
        : "";
      alertText.textContent = `⚠ 침입자 감지! ${state.lastAlert}${targetSummary}`;
    }
  } else if (deerActive && state.lastDeerAlert) {
    alertBlock.classList.add("active");
    alertBlock.style.borderColor = "#50dc64";
    alertBlock.style.backgroundColor = "rgba(80, 220, 100, 0.12)";
    alertText.textContent = `🦌 사슴 감지! ${state.lastDeerAlert}`;
  } else {
    alertBlock.classList.remove("active");
    alertBlock.style.borderColor = "";
    alertBlock.style.backgroundColor = "";
    if (state.intruders.length) {
      const confirmedCount = state.intruders.filter((intruder) => state.confirmedTargetIds.has(Number(intruder.id ?? 0))).length;
      alertText.textContent = `${state.intruders.length} target(s) available / ${confirmedCount} confirmed`;
    } else if (Date.now() - state.lastIntruderStateTime >= 3000) {
      alertText.textContent = "No target telemetry";
    } else {
      alertText.textContent = "No active alert";
    }
  }
}

function handleMapClick(event) {
  const rect = canvas.getBoundingClientRect();
  const click = {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
  const CLICK_RADIUS = 28;

  let bestIntruder = null;
  let bestIntruderDist = Infinity;
  state.intruders.forEach((intruder) => {
    const p = worldToCanvas(Number(intruder.x || 0), Number(intruder.y || 0));
    const d = Math.hypot(click.x - p.x, click.y - p.y);
    if (d < bestIntruderDist) { bestIntruderDist = d; bestIntruder = intruder; }
  });

  let bestIntruderDot = null;
  let bestIntruderDotDist = Infinity;
  state.intruderDots.forEach((dot) => {
    const hasLive = state.intruders.some(i => Math.hypot(Number(i.x) - dot.x, Number(i.y) - dot.y) < 3.0);
    if (hasLive) return;
    const p = worldToCanvas(dot.x, dot.y);
    const d = Math.hypot(click.x - p.x, click.y - p.y);
    if (d < bestIntruderDotDist) { bestIntruderDotDist = d; bestIntruderDot = dot; }
  });

  let bestDeer = null;
  let bestDeerDist = Infinity;
  state.deerDots.forEach((dot) => {
    const p = worldToCanvas(dot.x, dot.y);
    const d = Math.hypot(click.x - p.x, click.y - p.y);
    if (d < bestDeerDist) { bestDeerDist = d; bestDeer = dot; }
  });

  let bestPerson = null;
  let bestPersonDist = Infinity;
  state.personDots.forEach((dot) => {
    const p = worldToCanvas(dot.x, dot.y);
    const d = Math.hypot(click.x - p.x, click.y - p.y);
    if (d < bestPersonDist) { bestPersonDist = d; bestPerson = dot; }
  });

  const minDist = Math.min(bestIntruderDist, bestIntruderDotDist, bestDeerDist, bestPersonDist);
  if (minDist > CLICK_RADIUS) return;

  if (bestIntruderDist === minDist) {
    selectTarget(bestIntruder);
  } else if (bestIntruderDotDist === minDist) {
    selectIntruderDot(bestIntruderDot);
  } else if (bestDeerDist <= bestPersonDist) {
    selectDeerTarget(bestDeer);
  } else {
    selectPersonDot(bestPerson);
  }
}

function animate() {
  drawMap();
  updateText();
  requestAnimationFrame(animate);
}

document.getElementById("launchBtn").addEventListener("click", () => publishMission("start_patrol"));
document.getElementById("homeBtn").addEventListener("click", () => publishMission("go_home"));
document.getElementById("stopBtn").addEventListener("click", () => publishMission("stop"));
document.getElementById("resumeBtn").addEventListener("click", () => publishMission("resume"));
document.getElementById("zoomInBtn").addEventListener("click", () => publishZoom("zoom_in"));
document.getElementById("zoomOutBtn").addEventListener("click", () => publishZoom("zoom_out"));
document.getElementById("zoomResetBtn").addEventListener("click", () => publishZoom("zoom_reset"));
document.getElementById("panLeftBtn").addEventListener("click", () => publishInspectionMove("pan_left"));
document.getElementById("panRightBtn").addEventListener("click", () => publishInspectionMove("pan_right"));
document.getElementById("tiltUpBtn").addEventListener("click", () => publishInspectionMove("tilt_up"));
document.getElementById("tiltDownBtn").addEventListener("click", () => publishInspectionMove("tilt_down"));
document.getElementById("centerCameraBtn").addEventListener("click", () => publishInspectionMove("center"));
document.getElementById("clearTargetBtn").addEventListener("click", () => {
  if (state.selectedTargetId !== null) {
    state.confirmedTargetIds.add(Number(state.selectedTargetId));
    logEvent(`target confirmed: unidentified target ${Number(state.selectedTargetId) + 1}`);
  }
  state.selectedTargetId = null;
  state.selectedDeerDotId = null;
  state.selectedIntruderDotId = null;
  state.selectedPersonDotId = null;
  inspectionZoom = 1.0;
  applyInspectionZoom();
  publishInspectionCommand({ action: "clear" });
  logEvent("inspection camera: cleared (zoom reset)");
});
canvas.addEventListener("click", handleMapClick);
window.addEventListener("resize", resizeCanvas);

resizeCanvas();
connectRosbridge();
animate();
