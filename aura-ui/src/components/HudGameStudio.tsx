import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

type GameTarget = {
  id: string;
  shape: "sphere";
  position: [number, number, number];
  radius: number;
};
type GameProject = {
  version: 1;
  seed: number;
  arena: [number, number];
  targets: GameTarget[];
  digest: string;
};

function validateProject(value: unknown): GameProject {
  if (!value || typeof value !== "object") throw Error("Missing game project");
  const data = value as Partial<GameProject>;
  if (data.version !== 1 || !Array.isArray(data.targets) ||
      data.targets.length < 1 || data.targets.length > 24 ||
      typeof data.seed !== "number" || !Number.isSafeInteger(data.seed) ||
      typeof data.digest !== "string" || !/^[a-f0-9]{64}$/.test(data.digest)) {
    throw Error("Invalid game blueprint");
  }
  for (const target of data.targets) {
    if (!target || target.shape !== "sphere" || typeof target.id !== "string" ||
        !/^target-[0-9]{1,2}$/.test(target.id) ||
        !Array.isArray(target.position) || target.position.length !== 3 ||
        target.position.some(x => typeof x !== "number" || !Number.isFinite(x) || Math.abs(x) > 10) ||
        typeof target.radius !== "number" || target.radius < 0.1 || target.radius > 1) {
      throw Error("Untrusted game geometry rejected");
    }
  }
  return data as GameProject;
}

export default function HudGameStudio({ interactive }: { interactive: boolean }) {
  const host = useRef<HTMLDivElement | null>(null);
  const [seed, setSeed] = useState(31415);
  const [count, setCount] = useState(6);
  const [project, setProject] = useState<GameProject | null>(null);
  const [score, setScore] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setProject(null);
    setScore(0);
    void fetch("/api/hud/game/project?seed=" + seed + "&target_count=" + count, {
      credentials: "same-origin", signal: controller.signal,
    }).then(async response => {
      if (!response.ok) throw Error("Local game API " + response.status);
      return validateProject(await response.json());
    }).then(setProject).catch(err => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Game load failed");
    });
    return () => controller.abort();
  }, [seed, count]);

  useEffect(() => {
    if (!project || !host.current) return;
    const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      setError("Local WebGL unavailable");
      return;
    }
    let disposed = false;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(56, 2.6, 0.1, 100);
    camera.position.set(0, 4.5, 10);
    camera.lookAt(0, 0.8, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.cssText = "display:block;width:100%;height:100%;touch-action:none";
    element.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0x56bfff, 1.8));
    const light = new THREE.DirectionalLight(0x9cefff, 3.2);
    light.position.set(3, 8, 4);
    scene.add(light);
    const floor = new THREE.Mesh(
      new THREE.BoxGeometry(10, 0.15, 7),
      new THREE.MeshStandardMaterial({ color: 0x062335, roughness: 0.8 }),
    );
    floor.position.set(0, -0.12, 0);
    scene.add(floor);
    const grid = new THREE.GridHelper(10, 20, 0x00a4d0, 0x0d4452);
    scene.add(grid);

    const targets: THREE.Mesh[] = [];
    for (const target of project.targets) {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(target.radius, 16, 12),
        new THREE.MeshStandardMaterial({ color: 0x00e5fc, emissive: 0x005ca1,
          emissiveIntensity: 1.5, metalness: 0.3 }),
      );
      mesh.position.set(...target.position);
      scene.add(mesh);
      targets.push(mesh);
    }
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const click = (event: PointerEvent) => {
      if (!interactive) return;
      const rect = renderer.domElement.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1,
                  -((event.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(targets.filter(t => t.visible))[0];
      if (hit) {
        hit.object.visible = false;
        setScore(previous => previous + 1);
      }
    };
    renderer.domElement.addEventListener("pointerdown", click);
    const resize = () => {
      if (disposed) return;
      const width = Math.max(element.clientWidth, 1);
      const height = Math.max(element.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(element);
    resize();
    let animation = 0;
    const draw = (time: number) => {
      if (disposed) return;
      targets.forEach((mesh, i) => {
        if (mesh.visible) mesh.position.y = project.targets[i].position[1] +
          Math.sin(time * 0.0015 + i) * 0.12;
      });
      renderer.render(scene, camera);
      animation = requestAnimationFrame(draw);
    };
    animation = requestAnimationFrame(draw);
    return () => {
      disposed = true;
      cancelAnimationFrame(animation);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", click);
      scene.traverse(object => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const mats = Array.isArray(object.material) ? object.material : [object.material];
          mats.forEach(material => material.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [project, interactive]);

  const exportProject = () => {
    if (!project || !interactive) return;
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    try {
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "aura-prototype-" + project.seed + ".json";
      anchor.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  return <div aria-label="Local game prototype studio" style={{ width: "100%", height: "100%" }}>
    <div ref={host} style={{ width: "100%", height: "156px" }} />
    <div style={{ display: "flex", gap: "5px", justifyContent: "center", alignItems: "center",
      font: "9px Consolas,monospace", color: "#9df9ff" }}>
      <span>LOCAL GAME / {score}/{project?.targets.length ?? count}</span>
      {interactive && <>
        <button type="button" onClick={() => setSeed(s => s >= 2147483646 ? 1 : s + 1)}>
          NEW
        </button>
        <button type="button" onClick={() => setCount(n => Math.min(n + 1, 24))}>+</button>
        <button type="button" onClick={() => setCount(n => Math.max(n - 1, 1))}>−</button>
        <button type="button" onClick={exportProject} disabled={!project}>JSON</button>
      </>}
    </div>
    {error && <span role="alert" style={{ fontSize: "9px", color: "#ff849b" }}>{error}</span>}
  </div>;
}
