"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import URDFLoader, { URDFRobot } from "urdf-loader";
import { getApiBase } from "@/lib/api";

/**
 * Immersive Camera View — Go2 URDF 메시 + rear/inspect MJPEG sphere wrap.
 *
 * 2026-05-21 변경:
 *   - overhead 카메라 sector 제거 (rear/inspect 만)
 *   - sphere 가까이 + sector 크게 (radius 4.2→2.8, span 70°→90°)
 *   - procedural Go2 → 실제 go2.urdf 메시 로드 (urdf-loader)
 *   - 북향 고정 + Go2 (URDF + sphere group) 가 yaw 만큼 회전 → 카메라
 *     영상도 같이 회전. OrbitControls 는 별개 (운용자 시점 조작).
 */

type CamConfig = {
  id: "inspect" | "rear";
  yawDeg: number;
  spanDeg: number;
  spanVDeg: number;
};

const CAMS: CamConfig[] = [
  { id: "inspect", yawDeg:   0, spanDeg: 90, spanVDeg: 60 },
  { id: "rear",    yawDeg: 180, spanDeg: 90, spanVDeg: 60 },
];

const SPHERE_RADIUS = 2.8;
const URDF_URL_ENV = process.env.NEXT_PUBLIC_GO2_URDF_URL;

function defaultUrdfUrl(): string {
  if (URDF_URL_ENV) return URDF_URL_ENV;
  if (typeof window === "undefined") return "";
  return "http://192.168.10.94:8766/scene/go2_description/urdf/go2.urdf";
}

function useMjpegTexture(cam: CamConfig["id"]): THREE.Texture | null {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = `${getApiBase()}/c2/video/mjpeg?camera=${cam}`;
    const t = new THREE.Texture(img);
    t.colorSpace = THREE.SRGBColorSpace;
    t.minFilter = THREE.LinearFilter;
    t.magFilter = THREE.LinearFilter;
    img.onload = () => { t.needsUpdate = true; setTex(t); };
    const iv = setInterval(() => { t.needsUpdate = true; }, 100);
    return () => { clearInterval(iv); t.dispose(); };
  }, [cam]);
  return tex;
}

function CameraSector({ cam }: { cam: CamConfig }) {
  const tex = useMjpegTexture(cam.id);
  const geom = useMemo(() => {
    const yaw = (cam.yawDeg * Math.PI) / 180;
    const span = (cam.spanDeg * Math.PI) / 180;
    const spanV = (cam.spanVDeg * Math.PI) / 180;
    const phiStart = yaw - span / 2 + Math.PI / 2;
    const phiLength = span;
    const thetaStart = Math.PI / 2 - spanV / 2;
    const thetaLength = spanV;
    return new THREE.SphereGeometry(
      SPHERE_RADIUS, 48, 24,
      phiStart, phiLength, thetaStart, thetaLength,
    );
  }, [cam]);
  if (!tex) return null;
  return (
    <mesh geometry={geom}>
      <meshBasicMaterial map={tex} side={THREE.BackSide}
                         transparent opacity={0.98} toneMapped={false} />
    </mesh>
  );
}

/** Go2 URDF 메시 비동기 로드. mesh resolution: package://go2_description → :8766. */
function Go2Urdf({ url }: { url: string }) {
  const [robot, setRobot] = useState<URDFRobot | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!url) return;
    const loader = new URDFLoader();
    const m = url.match(/^(https?:\/\/[^/]+)/);
    const host = m ? m[1] : "";
    (loader as any).packages = { go2_description: `${host}/scene/go2_description` };
    loader.loadMeshCb = (path, manager, done) => {
      const ext = path.split(".").pop()?.toLowerCase();
      if (ext === "dae") {
        import("three/examples/jsm/loaders/ColladaLoader.js").then(({ ColladaLoader }) => {
          new ColladaLoader(manager).load(path,
            (res: any) => done(res.scene),
            undefined, (e: any) => done(new THREE.Object3D(), e as Error));
        });
      } else if (ext === "stl") {
        import("three/examples/jsm/loaders/STLLoader.js").then(({ STLLoader }) => {
          new STLLoader(manager).load(path,
            (geom: any) => {
              const mat = new THREE.MeshStandardMaterial({ color: 0xb0b0b0 });
              done(new THREE.Mesh(geom, mat));
            },
            undefined, (e: any) => done(new THREE.Object3D(), e as Error));
        });
      } else {
        done(new THREE.Object3D(), new Error(`unsupported mesh: ${ext}`));
      }
    };
    loader.load(url, (r) => setRobot(r), undefined,
      (e: any) => setErr(String(e?.message || e)));
  }, [url]);

  if (err) {
    return (
      <mesh position={[0, 0.3, 0]}>
        <boxGeometry args={[0.6, 0.18, 0.32]} />
        <meshStandardMaterial color="#ff5050" />
      </mesh>
    );
  }
  if (!robot) {
    return (
      <group>
        <mesh position={[0, 0.30, 0]}>
          <boxGeometry args={[0.65, 0.18, 0.32]} />
          <meshStandardMaterial color="#ffd040" wireframe />
        </mesh>
      </group>
    );
  }
  return <primitive object={robot} />;
}

function Ground() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
      <ringGeometry args={[0.5, 0.6, 64]} />
      <meshBasicMaterial color="#00ff88" transparent opacity={0.45}
                         side={THREE.DoubleSide} />
    </mesh>
  );
}

function SphereWireframe() {
  return (
    <mesh>
      <sphereGeometry args={[SPHERE_RADIUS + 0.02, 32, 16]} />
      <meshBasicMaterial color="#00ff88" wireframe transparent
                         opacity={0.06} side={THREE.BackSide} />
    </mesh>
  );
}

/** Robot+sphere group 의 yaw 회전 — yaw 값을 매 프레임 lerp smoothing. */
function YawGroup({ yaw, children }: {
  yaw: number; children: React.ReactNode;
}) {
  const ref = useRef<THREE.Group>(null);
  useFrame(() => {
    if (!ref.current) return;
    const cur = ref.current.rotation.y;
    const diff = ((yaw - cur + Math.PI) % (Math.PI * 2)) - Math.PI;
    ref.current.rotation.y = cur + diff * 0.15;
  });
  return <group ref={ref}>{children}</group>;
}

export default function ImmersiveCameraViewClient({
  yaw = 0,
}: {
  /** Go2 base 의 world yaw (rad). 0=world +X. page.tsx 에서 snap.odom.yaw. */
  yaw?: number;
}) {
  const url = useMemo(() => defaultUrdfUrl(), []);
  return (
    <div className="relative w-full h-full bg-black">
      <Canvas
        camera={{ position: [2.5, 2.0, 2.5], fov: 50, near: 0.05, far: 60 }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: "#000" }}
      >
        <ambientLight intensity={0.55} />
        <pointLight position={[3, 4, 3]} intensity={1.5} color="#ffffff" />
        <pointLight position={[-3, 2, -3]} intensity={0.6} color="#00ff88" />

        <YawGroup yaw={yaw}>
          <Go2Urdf url={url} />
          {CAMS.map((c) => <CameraSector key={c.id} cam={c} />)}
          <SphereWireframe />
        </YawGroup>

        <Ground />

        <OrbitControls enableDamping dampingFactor={0.08}
                       minDistance={1.2} maxDistance={9}
                       target={[0, 0.3, 0]} />
      </Canvas>

      <div className="absolute top-2 left-2 text-[10px] font-mono
                      bg-black/70 text-phos px-2 py-0.5 tracking-wider">
        ⬆ NORTH · URDF + 2-CAM SPHERE
      </div>

      <div className="absolute inset-0 pointer-events-none opacity-15"
           style={{
             background: "repeating-linear-gradient(0deg, rgba(0,255,128,0) 0px, rgba(0,255,128,0) 2px, rgba(0,255,128,0.06) 3px, rgba(0,255,128,0) 4px)",
           }} />
    </div>
  );
}
