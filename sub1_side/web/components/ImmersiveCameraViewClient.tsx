"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { getApiBase } from "@/lib/api";

/**
 * Spot SDK fisheye sphere wrapping 패턴 차용 (2026-05-20).
 * 핵심 구조:
 *   1. SphereGeometry 안쪽 면 (THREE.BackSide) 에 video texture 매핑
 *   2. 카메라 영상마다 sphere 의 sector face 분담 (rear/inspect/overhead)
 *   3. 중앙 Go2 silhouette mesh (노란색 box+legs)
 *   4. OrbitControls — 마우스 회전·줌
 *   5. ambient + point lighting + scanline overlay
 */

type CamConfig = {
  id: "inspect" | "rear" | "overhead";
  yawDeg: number;
  pitchDeg: number;
  spanDeg: number;
  spanVDeg: number;
};

const CAMS: CamConfig[] = [
  { id: "inspect",  yawDeg:   0, pitchDeg:   0, spanDeg: 70, spanVDeg: 40 },
  { id: "rear",     yawDeg: 180, pitchDeg:   0, spanDeg: 70, spanVDeg: 40 },
  { id: "overhead", yawDeg:   0, pitchDeg:  88, spanDeg: 80, spanVDeg: 80 },
];

const SPHERE_RADIUS = 4.2;

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
    const pitch = (cam.pitchDeg * Math.PI) / 180;
    const span = (cam.spanDeg * Math.PI) / 180;
    const spanV = (cam.spanVDeg * Math.PI) / 180;
    const phiStart = yaw - span / 2 + Math.PI / 2;
    const phiLength = span;
    const thetaStart = Math.PI / 2 - pitch - spanV / 2;
    const thetaLength = spanV;
    return new THREE.SphereGeometry(
      SPHERE_RADIUS, 32, 16,
      phiStart, phiLength, thetaStart, thetaLength,
    );
  }, [cam]);
  if (!tex) return null;
  return (
    <mesh geometry={geom}>
      <meshBasicMaterial map={tex} side={THREE.BackSide} transparent opacity={0.95} toneMapped={false} />
    </mesh>
  );
}

function Go2Silhouette() {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * 0.05; });
  return (
    <group ref={ref}>
      <mesh position={[0, 0.30, 0]}>
        <boxGeometry args={[0.65, 0.18, 0.32]} />
        <meshStandardMaterial color="#ffd040" metalness={0.4} roughness={0.3}
                              emissive="#664400" emissiveIntensity={0.3} />
      </mesh>
      <mesh position={[0.32, 0.35, 0]}>
        <boxGeometry args={[0.18, 0.12, 0.20]} />
        <meshStandardMaterial color="#ffe060" metalness={0.4} roughness={0.4} />
      </mesh>
      {([
        [ 0.20,  0.15,  0.13],
        [ 0.20,  0.15, -0.13],
        [-0.20,  0.15,  0.13],
        [-0.20,  0.15, -0.13],
      ] as [number, number, number][]).map((p, i) => (
        <mesh key={i} position={p}>
          <cylinderGeometry args={[0.025, 0.025, 0.30, 12]} />
          <meshStandardMaterial color="#ffaa20" metalness={0.5} roughness={0.3} />
        </mesh>
      ))}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <ringGeometry args={[0.45, 0.55, 64]} />
        <meshBasicMaterial color="#00ff88" transparent opacity={0.35} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function SphereWireframe() {
  return (
    <mesh>
      <sphereGeometry args={[SPHERE_RADIUS + 0.05, 32, 16]} />
      <meshBasicMaterial color="#00ff88" wireframe transparent opacity={0.08} side={THREE.BackSide} />
    </mesh>
  );
}

export default function ImmersiveCameraViewClient() {
  return (
    <div className="relative w-full h-full bg-black">
      <Canvas
        camera={{ position: [3.5, 2.2, 3.5], fov: 55, near: 0.05, far: 60 }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: "#000" }}
      >
        <ambientLight intensity={0.4} />
        <pointLight position={[3, 4, 3]} intensity={1.5} color="#ffffff" />
        <pointLight position={[-3, 2, -3]} intensity={0.6} color="#00ff88" />
        {CAMS.map((c) => <CameraSector key={c.id} cam={c} />)}
        <SphereWireframe />
        <Go2Silhouette />
        <OrbitControls enableDamping dampingFactor={0.08}
                       minDistance={1.2} maxDistance={9} target={[0, 0.3, 0]} />
      </Canvas>
      <div className="absolute inset-0 pointer-events-none opacity-15"
           style={{
             background: "repeating-linear-gradient(0deg, rgba(0,255,128,0) 0px, rgba(0,255,128,0) 2px, rgba(0,255,128,0.06) 3px, rgba(0,255,128,0) 4px)",
           }} />
    </div>
  );
}
