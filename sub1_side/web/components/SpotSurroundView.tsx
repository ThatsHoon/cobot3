"use client";

import { useEffect, useRef } from "react";
import type * as THREE from "three";

export default function SpotSurroundView({ apiBase }: { apiBase: string }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const yawRef = useRef(0);

  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    let animId: number;
    let disposeAll: (() => void) | undefined;

    (async () => {
      const THREE = await import("three");

      // ── Renderer ────────────────────────────────────────────────
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(container.clientWidth, container.clientHeight);
      renderer.setClearColor(0x080c10);
      container.appendChild(renderer.domElement);

      // ── Scene ───────────────────────────────────────────────────
      const scene = new THREE.Scene();
      scene.fog = new THREE.Fog(0x080c10, 10, 22);

      // ── Camera ──────────────────────────────────────────────────
      const camera = new THREE.PerspectiveCamera(
        50, container.clientWidth / container.clientHeight, 0.01, 50
      );
      let spherical = { theta: Math.PI / 4, phi: Math.PI / 4.5, radius: 7 };
      const updateCamera = () => {
        camera.position.set(
          spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta),
          spherical.radius * Math.cos(spherical.phi),
          spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta)
        );
        camera.lookAt(0, 0.4, 0);
      };
      updateCamera();

      // ── Lights ──────────────────────────────────────────────────
      scene.add(new THREE.AmbientLight(0x203040, 3));
      const sun = new THREE.DirectionalLight(0xfff5e0, 2.5);
      sun.position.set(5, 8, 5);
      scene.add(sun);
      const blueLight = new THREE.DirectionalLight(0x0044cc, 0.4);
      blueLight.position.set(-4, 2, -4);
      scene.add(blueLight);

      // ── Grid ────────────────────────────────────────────────────
      scene.add(new THREE.GridHelper(14, 28, 0x1a3a2a, 0x0d1f10));

      // ── 360° coverage torus ──────────────────────────────────────
      const torus = new THREE.Mesh(
        new THREE.TorusGeometry(2.5, 0.04, 16, 64),
        new THREE.MeshBasicMaterial({ color: 0x4ade80, wireframe: true, opacity: 0.3, transparent: true })
      );
      torus.rotation.x = Math.PI / 2;
      torus.position.y = 0.05;
      scene.add(torus);

      // ── Robot group (yaw rotation applied here) ──────────────────
      const robotGroup = new THREE.Group();
      scene.add(robotGroup);

      // Body
      const bodyGeo = new THREE.BoxGeometry(0.9, 0.28, 0.5);
      const body = new THREE.Mesh(bodyGeo, new THREE.MeshLambertMaterial({ color: 0xf97316 }));
      body.position.set(0, 0.44, 0);
      robotGroup.add(body);
      const bodyEdges = new THREE.LineSegments(
        new THREE.EdgesGeometry(bodyGeo),
        new THREE.LineBasicMaterial({ color: 0xfed7aa, opacity: 0.6, transparent: true })
      );
      bodyEdges.position.set(0, 0.44, 0);
      robotGroup.add(bodyEdges);

      // Head
      const head = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, 0.16, 0.22),
        new THREE.MeshLambertMaterial({ color: 0xea580c })
      );
      head.position.set(0.52, 0.5, 0);
      robotGroup.add(head);

      // 4 legs + feet
      const legGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.38, 8);
      const legMat = new THREE.MeshLambertMaterial({ color: 0xc2410c });
      const footMat = new THREE.MeshLambertMaterial({ color: 0x7c2d12 });
      const footGeo = new THREE.SphereGeometry(0.06, 8, 6);
      ([
        [0.28, 0.25, 0.2], [0.28, 0.25, -0.2],
        [-0.28, 0.25, 0.2], [-0.28, 0.25, -0.2],
      ] as [number, number, number][]).forEach(([x, y, z]) => {
        const leg = new THREE.Mesh(legGeo, legMat);
        leg.position.set(x, y, z);
        robotGroup.add(leg);
        const foot = new THREE.Mesh(footGeo, footMat);
        foot.position.set(x, y - 0.19, z);
        robotGroup.add(foot);
      });

      // ── Camera frustum helper ────────────────────────────────────
      const makeFrustum = (color: number, forward: boolean) => {
        const dir = forward ? 1 : -1;
        const dist = 1.8;
        const hw = dist * Math.tan((75 * Math.PI) / 180 / 2);
        const hh = hw * (9 / 16);
        const apex = new THREE.Vector3(0, 0, 0);
        const corners = [
          new THREE.Vector3(dir * dist,  hh,  hw),
          new THREE.Vector3(dir * dist,  hh, -hw),
          new THREE.Vector3(dir * dist, -hh, -hw),
          new THREE.Vector3(dir * dist, -hh,  hw),
        ];
        const pts: THREE.Vector3[] = [];
        corners.forEach(c => pts.push(apex.clone(), c.clone()));
        for (let i = 0; i < 4; i++) pts.push(corners[i], corners[(i + 1) % 4]);
        return new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color, opacity: 0.75, transparent: true })
        );
      };

      // Front camera
      const frontGroup = new THREE.Group();
      frontGroup.position.set(0.62, 0.5, 0);
      robotGroup.add(frontGroup);
      frontGroup.add(new THREE.Mesh(
        new THREE.BoxGeometry(0.06, 0.04, 0.09),
        new THREE.MeshLambertMaterial({ color: 0x1e3a8a })
      ));
      frontGroup.add(makeFrustum(0xfbbf24, true));

      // Rear camera
      const rearGroup = new THREE.Group();
      rearGroup.position.set(-0.55, 0.44, 0);
      robotGroup.add(rearGroup);
      rearGroup.add(new THREE.Mesh(
        new THREE.BoxGeometry(0.06, 0.04, 0.09),
        new THREE.MeshLambertMaterial({ color: 0x1e3a8a })
      ));
      rearGroup.add(makeFrustum(0x22d3ee, false));

      // ── Coverage sector arcs on ground (in robotGroup = rotate with yaw) ──
      const makeSectorArc = (startAngle: number, endAngle: number, color: number) => {
        const pts: THREE.Vector3[] = [];
        const r = 2.5;
        const N = 32;
        const span = endAngle - startAngle;
        for (let i = 0; i < N; i++) {
          const a1 = startAngle + (i / N) * span;
          const a2 = startAngle + ((i + 1) / N) * span;
          pts.push(
            new THREE.Vector3(r * Math.cos(a1), 0.06, r * Math.sin(a1)),
            new THREE.Vector3(r * Math.cos(a2), 0.06, r * Math.sin(a2))
          );
        }
        return new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color, opacity: 0.7, transparent: true })
        );
      };

      const halfFov = (75 * Math.PI) / 180 / 2;
      // front sector: centered on +X axis (angle=0)
      robotGroup.add(makeSectorArc(-halfFov, halfFov, 0xfbbf24));
      // rear sector: centered on -X axis (angle=π)
      robotGroup.add(makeSectorArc(Math.PI - halfFov, Math.PI + halfFov, 0x22d3ee));

      // Radial lines center → ring edge
      const makeRadial = (angle: number, color: number) => {
        const pts = [
          new THREE.Vector3(0, 0.06, 0),
          new THREE.Vector3(2.5 * Math.cos(angle), 0.06, 2.5 * Math.sin(angle)),
        ];
        return new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color, opacity: 0.3, transparent: true })
        );
      };
      robotGroup.add(makeRadial(0,        0xfbbf24));
      robotGroup.add(makeRadial(Math.PI,  0x22d3ee));

      // ── Mouse orbit controls ─────────────────────────────────────
      let dragging = false;
      let lastX = 0, lastY = 0;
      const el = renderer.domElement;

      const onDown = (e: MouseEvent) => { dragging = true; lastX = e.clientX; lastY = e.clientY; };
      const onUp = () => { dragging = false; };
      const onMove = (e: MouseEvent) => {
        if (!dragging) return;
        spherical.theta -= (e.clientX - lastX) * 0.012;
        spherical.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.05,
          spherical.phi + (e.clientY - lastY) * 0.012));
        lastX = e.clientX; lastY = e.clientY;
        updateCamera();
      };
      const onWheel = (e: WheelEvent) => {
        spherical.radius = Math.max(2.5, Math.min(16, spherical.radius + e.deltaY * 0.01));
        updateCamera();
      };
      el.addEventListener("mousedown", onDown);
      window.addEventListener("mouseup", onUp);
      window.addEventListener("mousemove", onMove);
      el.addEventListener("wheel", onWheel, { passive: true });

      // ── Resize ──────────────────────────────────────────────────
      const obs = new ResizeObserver(() => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
      });
      obs.observe(container);

      // ── Odom polling (yaw) ───────────────────────────────────────
      let pollTimer: ReturnType<typeof setInterval> | undefined;
      if (apiBase) {
        const poll = async () => {
          try {
            const r = await fetch(`${apiBase}/robots/gp0/state`);
            if (!r.ok) return;
            const d = await r.json();
            if (typeof d.odom?.yaw === "number") yawRef.current = d.odom.yaw;
          } catch { /* server not ready */ }
        };
        poll();
        pollTimer = setInterval(poll, 200);
      }

      // ── Animate ─────────────────────────────────────────────────
      const animate = () => {
        animId = requestAnimationFrame(animate);
        robotGroup.rotation.y = yawRef.current;
        renderer.render(scene, camera);
      };
      animate();

      disposeAll = () => {
        cancelAnimationFrame(animId);
        clearInterval(pollTimer);
        obs.disconnect();
        el.removeEventListener("mousedown", onDown);
        window.removeEventListener("mouseup", onUp);
        window.removeEventListener("mousemove", onMove);
        el.removeEventListener("wheel", onWheel);
        renderer.dispose();
        if (container.contains(el)) container.removeChild(el);
      };
    })();

    return () => disposeAll?.();
  }, [apiBase]);

  return (
    <div ref={mountRef} className="relative w-full h-full cursor-grab active:cursor-grabbing select-none">
      <div className="absolute bottom-2 left-2 text-[9px] leading-5 pointer-events-none space-y-0.5">
        <div><span className="text-yellow-400 mr-1">▶</span>FRONT CAM · 75° FOV</div>
        <div><span className="text-cyan-400 mr-1">◀</span>REAR CAM · 75° FOV</div>
        <div><span className="text-green-400 mr-1">○</span>2.5 m COVERAGE RING</div>
      </div>
      <div className="absolute bottom-2 right-2 text-[9px] text-dim pointer-events-none tracking-wider">
        DRAG · SCROLL
      </div>
    </div>
  );
}
