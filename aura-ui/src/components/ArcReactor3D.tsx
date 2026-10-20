import { useEffect, useRef } from "react";
import * as THREE from "three";

type ReactorLevel = "idle" | "thinking" | "executing";

interface ArcReactor3DProps {
  active: boolean;
  level: ReactorLevel;
  size?: number;
}

export default function ArcReactor3D({
  active,
  level,
  size = 320,
}: ArcReactor3DProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const levelRef = useRef(level);
  const activeRef = useRef(active);

  useEffect(() => {
    levelRef.current = level;
    activeRef.current = active;
  }, [level, active]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let frame = 0;
    let dragging = false;
    let previousX = 0;
    let previousY = 0;
    let targetX = 0;
    let targetY = 0;
    let spin = 0;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#020810");

    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 9);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(size, size);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    renderer.domElement.style.cursor = "grab";
    renderer.domElement.setAttribute("aria-label", "Interactive 3D AURA reactor");

    const root = new THREE.Group();
    scene.add(root);

    scene.add(new THREE.AmbientLight(0x4bcfff, 1.8));

    const keyLight = new THREE.PointLight(0x00d9ff, 35, 18);
    keyLight.position.set(3, 3, 5);
    scene.add(keyLight);

    const rimLight = new THREE.PointLight(0x276bff, 24, 18);
    rimLight.position.set(-4, -2, -3);
    scene.add(rimLight);

    const coreMaterial = new THREE.MeshStandardMaterial({
      color: 0x14cfff,
      emissive: 0x007fa8,
      emissiveIntensity: 2.5,
      metalness: 0.55,
      roughness: 0.2,
    });

    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.82, 2),
      coreMaterial,
    );
    root.add(core);

    const innerGlow = new THREE.Mesh(
      new THREE.SphereGeometry(0.52, 32, 32),
      new THREE.MeshBasicMaterial({
        color: 0x7beaff,
        transparent: true,
        opacity: 0.28,
      }),
    );
    root.add(innerGlow);

    const ringMaterials = [
      new THREE.MeshStandardMaterial({
        color: 0x00d9ff,
        emissive: 0x0088bb,
        emissiveIntensity: 2.0,
        metalness: 0.75,
        roughness: 0.25,
      }),
      new THREE.MeshStandardMaterial({
        color: 0x2e72ff,
        emissive: 0x174bff,
        emissiveIntensity: 1.5,
        metalness: 0.65,
        roughness: 0.3,
      }),
      new THREE.MeshStandardMaterial({
        color: 0x9deeff,
        emissive: 0x31bfff,
        emissiveIntensity: 1.2,
        metalness: 0.8,
        roughness: 0.2,
      }),
    ];

    const rings = [
      new THREE.Mesh(new THREE.TorusGeometry(1.25, 0.045, 12, 100), ringMaterials[0]),
      new THREE.Mesh(new THREE.TorusGeometry(1.65, 0.025, 10, 100), ringMaterials[1]),
      new THREE.Mesh(new THREE.TorusGeometry(2.0, 0.016, 8, 120), ringMaterials[2]),
    ];

    rings[0].rotation.x = 0.8;
    rings[1].rotation.x = 1.25;
    rings[1].rotation.y = 0.55;
    rings[2].rotation.x = 0.25;
    rings[2].rotation.y = 0.95;
    rings.forEach((ring) => root.add(ring));

    const nodeGeometry = new THREE.SphereGeometry(0.07, 12, 12);
    const nodeMaterial = new THREE.MeshBasicMaterial({ color: 0x8ceeff });
    const nodes = new THREE.Group();

    for (let i = 0; i < 16; i += 1) {
      const angle = (i / 16) * Math.PI * 2;
      const node = new THREE.Mesh(nodeGeometry, nodeMaterial);
      node.position.set(Math.cos(angle) * 2.2, Math.sin(angle) * 2.2, 0);
      nodes.add(node);
    }
    root.add(nodes);

    const starGeometry = new THREE.BufferGeometry();
    const starPositions = new Float32Array(240 * 3);
    for (let i = 0; i < starPositions.length; i += 3) {
      starPositions[i] = (Math.random() - 0.5) * 12;
      starPositions[i + 1] = (Math.random() - 0.5) * 12;
      starPositions[i + 2] = -2 - Math.random() * 5;
    }
    starGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(starPositions, 3),
    );

    const stars = new THREE.Points(
      starGeometry,
      new THREE.PointsMaterial({
        color: 0x2586a9,
        size: 0.025,
        transparent: true,
        opacity: 0.7,
      }),
    );
    scene.add(stars);

    const resize = () => {
      if (disposed || !host) return;
      const width = Math.max(1, host.clientWidth);
      const height = Math.max(1, host.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };

    const onPointerDown = (event: PointerEvent) => {
      dragging = true;
      previousX = event.clientX;
      previousY = event.clientY;
      renderer.domElement.style.cursor = "grabbing";
      renderer.domElement.setPointerCapture?.(event.pointerId);
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!dragging) return;
      targetY += (event.clientX - previousX) * 0.008;
      targetX += (event.clientY - previousY) * 0.008;
      previousX = event.clientX;
      previousY = event.clientY;
    };

    const onPointerUp = () => {
      dragging = false;
      renderer.domElement.style.cursor = "grab";
    };

    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("pointercancel", onPointerUp);

    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    let previousFrameTime = performance.now();

    const animate = () => {
      if (disposed) return;
      frame = requestAnimationFrame(animate);

      const frameTime = performance.now();
      const delta = Math.min((frameTime - previousFrameTime) / 1000, 0.05);
      previousFrameTime = frameTime;
      const currentLevel = levelRef.current;
      const speed =
        currentLevel === "executing" ? 1.7 :
        currentLevel === "thinking" ? 0.9 : 0.28;

      spin += delta * speed;
      root.rotation.x += (targetX - root.rotation.x) * 0.06;
      root.rotation.y += (targetY - root.rotation.y) * 0.06;
      root.rotation.y += delta * speed * 0.16;

      rings[0].rotation.z += delta * speed * 0.28;
      rings[1].rotation.z -= delta * speed * 0.18;
      rings[2].rotation.z += delta * speed * 0.12;
      core.rotation.x += delta * speed * 0.18;
      core.rotation.y -= delta * speed * 0.25;
      nodes.rotation.z = -spin * 0.12;

      const pulse = 1 + Math.sin(spin * 2.2) * (activeRef.current ? 0.09 : 0.025);
      core.scale.setScalar(pulse);
      coreMaterial.emissiveIntensity = activeRef.current ? 3.2 : 1.8;
      keyLight.intensity = activeRef.current ? 45 : 25;

      renderer.render(scene, camera);
    };

    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();

      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointercancel", onPointerUp);

      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Points) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material)
            ? object.material
            : [object.material];
          materials.forEach((material) => material.dispose());
        }
      });

      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [size]);

  return (
    <div
      ref={hostRef}
      className="aspect-square w-full overflow-hidden rounded-full"
      style={{ maxWidth: size, touchAction: "none" }}
      role="img"
      aria-label={`AURA 3D reactor: ${level}`}
    />
  );
}
