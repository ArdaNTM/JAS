import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

export type VisualizationModelId =
  | "procedural-object-v1"
  | "gear-v1"
  | "sphere-v1"
  | "motor-v1";

type Props = {
  target: string;
  modelId?: VisualizationModelId;
  active: boolean;
  onInspect?: (part: string) => void;
};

const material = (wireframe = false) =>
  new THREE.MeshStandardMaterial({
    color: wireframe ? 0x168cff : 0x00c9e8,
    emissive: wireframe ? 0x003c91 : 0x004c68,
    emissiveIntensity: 1.4,
    metalness: 0.6,
    roughness: 0.3,
    wireframe,
  });

function makeGear() {
  const group = new THREE.Group();
  const teeth = 12;
  const shape = new THREE.Shape();

  for (let i = 0; i < teeth * 4; i++) {
    const angle = (i / (teeth * 4)) * Math.PI * 2;
    const phase = i % 4;
    const radius = phase === 0 || phase === 3 ? 0.92 : 1.15;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  shape.closePath();

  const hole = new THREE.Path();
  hole.absarc(0, 0, 0.28, 0, Math.PI * 2, true);
  shape.holes.push(hole);

  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.2,
    bevelEnabled: true,
    bevelSegments: 2,
    bevelSize: 0.025,
    bevelThickness: 0.025,
  });
  geometry.center();

  group.add(new THREE.Mesh(geometry, material()));
  const outline = new THREE.Mesh(geometry, material(true));
  outline.scale.setScalar(1.006);
  group.add(outline);

  const hub = new THREE.Mesh(
    new THREE.TorusGeometry(0.4, 0.035, 8, 48),
    material()
  );
  hub.position.z = 0.14;
  group.add(hub);
  return group;
}

function makeSphere() {
  const group = new THREE.Group();
  group.add(new THREE.Mesh(
    new THREE.SphereGeometry(0.9, 32, 24), material()
  ));
  group.add(new THREE.Mesh(
    new THREE.SphereGeometry(0.92, 18, 12), material(true)
  ));

  for (const [x, y, z] of [
    [0, 0, 0],
    [Math.PI / 2, 0.4, 0],
    [0.7, 0.7, 0.8],
  ]) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1.2, 0.014, 6, 96),
      material()
    );
    ring.rotation.set(x, y, z);
    group.add(ring);
  }
  return group;
}

function makeMotor() {
  // Generic illustrative opposed-six assembly, not a manufacturer CAD file.
  const group = new THREE.Group();
  const block = new THREE.Group(); block.name = "Krank karteri";
  const blockGeo = new THREE.BoxGeometry(1.15, .82, 2.1);
  const shell = material();
  shell.transparent = true; shell.opacity = .32;
  block.add(new THREE.Mesh(blockGeo, shell), new THREE.Mesh(blockGeo, material(true)));
  group.add(block);
  const shaft = new THREE.Group(); shaft.name = "Krank mili";
  const shaftMesh = new THREE.Mesh(new THREE.CylinderGeometry(.12, .12, 2.6, 24), material());
  shaftMesh.rotation.x = Math.PI / 2;
  shaft.add(shaftMesh);
  const pulley = new THREE.Mesh(new THREE.CylinderGeometry(.42, .42, .15, 24), material());
  pulley.rotation.x = Math.PI / 2; pulley.position.z = 1.35; shaft.add(pulley); group.add(shaft);
  for (const side of [-1, 1]) {
    const bank = new THREE.Group(); bank.name = side < 0 ? "Sol silindir grubu" : "Sağ silindir grubu";
    bank.position.x = side * 1.02;
    for (const z of [-.68, 0, .68]) {
      const sleeve = new THREE.Mesh(new THREE.CylinderGeometry(.27, .27, .72, 24, 1, true), material(true));
      sleeve.rotation.z = Math.PI / 2; sleeve.position.z = z; bank.add(sleeve);
      const head = new THREE.Mesh(new THREE.CylinderGeometry(.22, .22, .19, 24), material());
      head.rotation.z = Math.PI / 2; head.position.z = z; head.position.x = side * -.12;
      head.userData.piston = true; head.userData.baseX = head.position.x; head.userData.phase = z * 4;
      bank.add(head);
    }
    group.add(bank);
    const turbo = new THREE.Group(); turbo.name = side < 0 ? "Sol turbo" : "Sağ turbo";
    const turbine = new THREE.Mesh(new THREE.TorusGeometry(.28, .12, 12, 36), material());
    turbine.userData.hot = true; turbo.add(turbine);
    const housing = new THREE.Mesh(new THREE.BoxGeometry(.42, .34, .48), material(true));
    housing.position.z = .33; turbo.add(housing);
    turbo.position.set(side * 1.38, -.42, -.9); group.add(turbo);
  }
  return group;
}

function makeDefault() {
  const group = new THREE.Group();
  group.add(new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.82, 1), material(true)
  ));
  group.add(new THREE.Mesh(
    new THREE.SphereGeometry(0.4, 20, 16), material()
  ));
  group.add(new THREE.Mesh(
    new THREE.TorusGeometry(1.15, 0.025, 8, 80), material()
  ));
  return group;
}

function makeModel(id: VisualizationModelId) {
  switch (id) {
    case "gear-v1": return makeGear();
    case "sphere-v1": return makeSphere();
    case "motor-v1": return makeMotor();
    default: return makeDefault();
  }
}

const labels: Record<VisualizationModelId, string> = {
  "procedural-object-v1": "PROCEDURAL OBJECT",
  "gear-v1": "GEAR ASSEMBLY",
  "sphere-v1": "SPHERE MODEL",
  "motor-v1": "MOTOR ASSEMBLY",
};

export default function DynamicHologram3D({
  target,
  modelId = "procedural-object-v1",
  active,
  onInspect,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [exploded, setExploded] = useState(false);
  const [thermal, setThermal] = useState(false);
  const [wireframe, setWireframe] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const modes = useRef({ exploded, thermal, wireframe });
  modes.current = { exploded, thermal, wireframe };

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let frame = 0;

    const scene = new THREE.Scene();
    scene.background = null;

    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0.3, modelId === "motor-v1" ? 7.5 : 5.2);

    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
    catch { setUnavailable(true); return; }
    setUnavailable(false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.cssText =
      "display:block;width:100%;height:100%;cursor:grab;touch-action:none";
    host.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0x7ddfff, 1.8));
    const keyLight = new THREE.PointLight(0x00dfff, 35);
    keyLight.position.set(3, 3, 4);
    scene.add(keyLight);
    const blueLight = new THREE.PointLight(0x1677ff, 22);
    blueLight.position.set(-3, -1, -2);
    scene.add(blueLight);

    const grid = new THREE.GridHelper(8, 32, 0x006e8a, 0x073044);
    grid.position.y = -1.5;
    scene.add(grid);

    const model = makeModel(modelId);
    scene.add(model);
    const parts = model.children.map((part, index) => ({ part, base: part.position.clone(), direction: part.position.lengthSq() > .01 ? part.position.clone().normalize() : new THREE.Vector3(0, 0, index % 2 ? 1 : -1) }));
    model.traverse(object => {
      if (object instanceof THREE.Mesh && object.material instanceof THREE.MeshStandardMaterial) {
        object.userData.originalColor = object.material.color.clone();
        object.userData.originalWire = object.material.wireframe;
      }
    });

    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(1.48, 0.012, 6, 120),
      new THREE.MeshBasicMaterial({ color: 0x00cce8 })
    );
    scene.add(halo);

    const resize = () => {
      if (disposed) return;
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const canvas = renderer.domElement;
    const down = (event: PointerEvent) => {
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      canvas.style.cursor = "grabbing";
      canvas.setPointerCapture(event.pointerId);
    };
    const move = (event: PointerEvent) => {
      if (!dragging) return;
      model.rotation.y += (event.clientX - lastX) * 0.008;
      model.rotation.x += (event.clientY - lastY) * 0.008;
      lastX = event.clientX;
      lastY = event.clientY;
      model.rotation.x = THREE.MathUtils.clamp(
        model.rotation.x, -Math.PI * 0.48, Math.PI * 0.48
      );
    };
    const up = () => {
      dragging = false;
      canvas.style.cursor = "grab";
    };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      camera.position.z = THREE.MathUtils.clamp(
        camera.position.z + event.deltaY * 0.003, 2.6, 9
      );
      camera.updateProjectionMatrix();
    };

    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", wheel, { passive: false });

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const animate = () => {
      if (disposed) return;
      frame = requestAnimationFrame(animate);
      if (!dragging && !reduced.matches) model.rotation.y += active ? 0.005 : 0.001;
      for (const {part, base, direction} of parts) part.position.lerp(base.clone().addScaledVector(direction, modes.current.exploded ? .75 : 0), .09);
      model.traverse(object => {
        if (!(object instanceof THREE.Mesh) || !(object.material instanceof THREE.MeshStandardMaterial)) return;
        const mat = object.material;
        mat.wireframe = modes.current.wireframe || Boolean(object.userData.originalWire);
        if (modes.current.thermal && modelId === "motor-v1") mat.color.setHex(object.userData.hot ? 0xff4f2b : 0xe9ad39);
        else if (object.userData.originalColor) mat.color.copy(object.userData.originalColor);
        if (object.userData.piston && !reduced.matches) object.position.x = object.userData.baseX + Math.sin(performance.now() / 180 + object.userData.phase) * .1;
      });
      halo.rotation.z += 0.001;
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      canvas.removeEventListener("wheel", wheel);

      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        mesh.geometry?.dispose();
        if (mesh.material) {
          const materials = Array.isArray(mesh.material)
            ? mesh.material : [mesh.material];
          materials.forEach((item) => item.dispose());
        }
      });
      renderer.dispose();
      canvas.remove();
    };
  }, [modelId, active]);

  return (
    <div className="w-full max-w-[520px]">
      <div className="mb-2 flex items-center justify-between text-[9px] tracking-[.2em] text-cyan-500">
        <span>HOLOGRAM / {labels[modelId]}</span>
        <span>DRAG · SCROLL TO ZOOM</span>
      </div>
      <div
        ref={hostRef}
        className="h-[360px] w-full overflow-hidden rounded-xl border border-cyan-950/80 bg-[#02060b]"
        aria-label={`Interactive 3D visualization: ${labels[modelId]}`}
      />
      {unavailable && <p role="alert">WebGL kullanılamıyor; araştırma sonucu sohbet geçmişinde kullanılabilir.</p>}
      <div className="astral-chips">
        <button type="button" className="astral-pill" aria-pressed={exploded} disabled={unavailable} onClick={() => setExploded(v => !v)}>Parçaları Ayır</button>
        <button type="button" className="astral-pill" aria-pressed={thermal} disabled={unavailable || modelId !== "motor-v1"} onClick={() => setThermal(v => !v)}>Termal renkler (temsili)</button>
        <button type="button" className="astral-pill" aria-pressed={wireframe} disabled={unavailable} onClick={() => setWireframe(v => !v)}>X-Ray Tel Kafes</button>
      </div>
      {modelId === "motor-v1" && <div className="astral-chips">{["Krank mili", "Karşılıklı silindirler", "Turbo grubu"].map(part => <button type="button" className="astral-pill" key={part} disabled={!onInspect} onClick={() => onInspect?.(part)}>{part} · incele</button>)}</div>}
      <div className="mt-3 border-l border-cyan-800 pl-3">
        <div className="text-[8px] tracking-[.2em] text-slate-600">
          REQUESTED OBJECT
        </div>
        <div className="mt-1 break-words text-sm font-semibold text-cyan-200">
          {target}
        </div>
        <div className="mt-1 text-[9px] leading-4 text-slate-500">
          Temsili yordamlı model; doğrulanmış CAD, ölçüm veya termal/akış simülasyonu değildir.
        </div>
      </div>
    </div>
  );
}