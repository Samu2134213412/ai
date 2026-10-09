// 3D-Ansicht des Builds mit three.js. Einheiten: Zentimeter.
// Koordinaten: x = vom Mainboard weg (Richtung Glasseitenteil), y = oben,
// z = vorne (Rückseite des Gehäuses liegt bei negativem z).
//
// Jedes Teil wird prozedural aufgebaut. Gibt es für ein Teil ein echtes
// 3D-Modell (.glb, vom Nutzer geladen oder in models/manifest.json), ersetzt
// es das prozedurale Modell und wird automatisch in dessen Umriss eingepasst.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { brandColor } from "./icons.js";

const CASE = { w: 22, h: 46, d: 45 };
const BACK = -CASE.d / 2 + 2; // Hinterkante Mainboard
const TOP = CASE.h / 2 - 3; // Oberkante Mainboard
const MOBO_X = -CASE.w / 2 + 1.5;

const BOARD = {
  EATX: { w: 30.5, h: 33, pcie: 12.5, slots: 4, pcieExtra: 3 },
  ATX: { w: 24.4, h: 30.5, pcie: 12.5, slots: 4, pcieExtra: 2 },
  mATX: { w: 24.4, h: 24.4, pcie: 12.5, slots: 4, pcieExtra: 1 },
  ITX: { w: 17, h: 17, pcie: 13, slots: 2, pcieExtra: 0 },
};

// ---------- Materialien ----------

const M = {
  plastic: (c = 0x1b1d22) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.55, metalness: 0.15 }),
  steel: (c = 0x26292f) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.4, metalness: 0.65 }),
  alu: () => new THREE.MeshStandardMaterial({ color: 0xc9cdd3, roughness: 0.3, metalness: 0.95 }),
  copper: () => new THREE.MeshStandardMaterial({ color: 0xc87a4a, roughness: 0.25, metalness: 1 }),
  gold: () => new THREE.MeshStandardMaterial({ color: 0xd8b04a, roughness: 0.3, metalness: 1 }),
  pcb: () => new THREE.MeshStandardMaterial({ color: 0x15171b, roughness: 0.75, metalness: 0.1 }),
  pcbGreen: () => new THREE.MeshStandardMaterial({ color: 0x1d4a2c, roughness: 0.7, metalness: 0.1 }),
  glow: (c) => new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 1.6, roughness: 0.4 }),
  glass: () => new THREE.MeshPhysicalMaterial({ color: 0xdfe8f0, roughness: 0.02, metalness: 0, transparent: true, opacity: 0.07, depthWrite: false }),
};

const box = (sx, sy, sz, mat) => new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), mat);
const rbox = (sx, sy, sz, r, mat) => new THREE.Mesh(new RoundedBoxGeometry(sx, sy, sz, 3, Math.min(r, sx / 2, sy / 2, sz / 2) * 0.999), mat);
const cyl = (r, len, mat, seg = 24) => new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, seg), mat);
const at = (mesh, x, y, z) => (mesh.position.set(x, y, z), mesh);

// Position auf dem Mainboard: u = Abstand von der Hinterkante, v = Abstand von oben, x = Höhe über der Platine.
const onBoard = (u, v, x = 0) => new THREE.Vector3(MOBO_X + x, TOP - v, BACK + u);
const place = (mesh, u, v, x) => (mesh.position.copy(onBoard(u, v, x)), mesh);

// Beschriftung als Fläche mit Canvas-Textur. Zeigt standardmäßig nach +z.
function label(text, w, h, { bg = null, fg = "#e8eaee", weight = 700 } = {}) {
  const c = document.createElement("canvas");
  const scale = 64;
  c.width = Math.max(64, Math.round(w * scale));
  c.height = Math.max(32, Math.round(h * scale));
  const g = c.getContext("2d");
  if (bg) {
    g.fillStyle = bg;
    g.fillRect(0, 0, c.width, c.height);
  }
  let size = c.height * 0.62;
  g.font = `${weight} ${size}px system-ui, sans-serif`;
  while (g.measureText(text).width > c.width * 0.92 && size > 8) g.font = `${weight} ${(size -= 2)}px system-ui, sans-serif`;
  g.fillStyle = fg;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, c.width / 2, c.height / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.6 }));
}

const faceX = (m) => ((m.rotation.y = Math.PI / 2), m);

// Lüfter mit Rotorblättern; Achse entlang z. square = Rahmen eines Gehäuselüfters.
function fan(r, { depth = 2.5, square = true, ring = null, blade = 0x24262c } = {}) {
  const g = new THREE.Group();
  if (square) {
    const s = r + 0.4;
    const shape = new THREE.Shape();
    shape.moveTo(-s, -s); shape.lineTo(s, -s); shape.lineTo(s, s); shape.lineTo(-s, s); shape.lineTo(-s, -s);
    const hole = new THREE.Path();
    hole.absarc(0, 0, r, 0, Math.PI * 2, true);
    shape.holes.push(hole);
    const frame = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 32 }), M.plastic(0x16181c));
    frame.position.z = -depth / 2;
    g.add(frame);
  } else {
    const shroudRing = new THREE.Mesh(new THREE.TorusGeometry(r + 0.05, 0.18, 8, 48), M.plastic(0x2a2d33));
    g.add(shroudRing);
  }
  if (ring) {
    const glowRing = new THREE.Mesh(new THREE.TorusGeometry(r - 0.15, 0.12, 8, 48), M.glow(ring));
    glowRing.position.z = depth / 2 - 0.1;
    g.add(glowRing);
  }
  const rotor = new THREE.Group();
  const hub = cyl(r * 0.32, depth * 0.6, M.plastic(0x202227), 32);
  hub.rotation.x = Math.PI / 2;
  rotor.add(hub);
  const bladeMat = M.plastic(blade);
  bladeMat.side = THREE.DoubleSide;
  const n = 9;
  for (let i = 0; i < n; i++) {
    const b = box(r * 0.68, r * 0.36, 0.08, bladeMat);
    b.position.x = r * 0.62;
    b.rotation.x = 0.5; // Anstellwinkel
    const arm = new THREE.Group();
    arm.rotation.z = (i / n) * Math.PI * 2;
    arm.add(b);
    rotor.add(arm);
  }
  g.add(rotor);
  g.userData.rotor = rotor;
  return g;
}

// Stapel dünner Platten (Kühlrippen) als InstancedMesh.
function fins(count, size, step, axis, mat) {
  const geo = new THREE.BoxGeometry(...size);
  const mesh = new THREE.InstancedMesh(geo, mat, count);
  const m = new THREE.Matrix4();
  for (let i = 0; i < count; i++) {
    const p = [0, 0, 0];
    p["xyz".indexOf(axis)] = (i - (count - 1) / 2) * step;
    mesh.setMatrixAt(i, m.makeTranslation(...p));
  }
  return mesh;
}

function tube(points, r, mat) {
  const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)));
  return new THREE.Mesh(new THREE.TubeGeometry(curve, 48, r, 10, false), mat);
}

// ---------- Szene ----------

export class PcScene {
  constructor(container) {
    this.container = container;
    this.slots = {}; // key -> { group, sig }
    this.anims = [];
    this.customModels = new Map(); // partId -> ArrayBuffer
    this.rotations = new Map(); // partId -> Vierteldrehungen
    this.manifest = [];
    this.gltfCache = new Map();
    this.clock = new THREE.Clock();

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);
    this.renderer = renderer;

    this.scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.environmentIntensity = 0.9;

    this.camera = new THREE.PerspectiveCamera(38, 1, 1, 500);
    this.camera.position.set(66, 18, 40);
    this.controls = new OrbitControls(this.camera, renderer.domElement);
    this.controls.target.set(-2, 0, 0);
    this.controls.enableDamping = true;
    this.controls.minDistance = 25;
    this.controls.maxDistance = 180;

    this.scene.add(new THREE.HemisphereLight(0xdde6ff, 0x30343c, 0.9));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(60, 70, 35);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    Object.assign(key.shadow.camera, { left: -40, right: 40, top: 40, bottom: -40, near: 10, far: 200 });
    key.shadow.bias = -0.0005;
    this.scene.add(key);
    // Innenbeleuchtung: weißes Licht von vorne-oben plus RGB-Schimmer
    const inner = new THREE.PointLight(0xffffff, 260, 60, 2);
    inner.position.set(6, 12, 12);
    this.scene.add(inner);
    const rgb = new THREE.PointLight(0x8a7cff, 90, 40, 2);
    rgb.position.set(2, -4, 16);
    this.scene.add(rgb);

    const floor = new THREE.Mesh(new THREE.CircleGeometry(70, 64), new THREE.MeshStandardMaterial({ color: 0x2a2e36, roughness: 0.9, metalness: 0, transparent: true, opacity: 0.55 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -CASE.h / 2 - 1.01;
    floor.receiveShadow = true;
    this.scene.add(floor);

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.tooltip = document.createElement("div");
    this.tooltip.className = "scene-tooltip";
    container.appendChild(this.tooltip);
    renderer.domElement.addEventListener("pointermove", (e) => this.onHover(e));
    renderer.domElement.addEventListener("pointerleave", () => (this.tooltip.style.display = "none"));

    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    renderer.setAnimationLoop((t) => this.tick(t));
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  tick(t) {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    for (const { group } of Object.values(this.slots)) {
      group.traverse((o) => o.userData.rotor && (o.userData.rotor.rotation.z += dt * 9));
    }
    this.anims = this.anims.filter((a) => {
      const k = Math.min(1, (t - (a.start ??= t)) / 650);
      const e = 1 - Math.pow(1 - k, 3);
      a.group.position.lerpVectors(a.from, a.to, e);
      a.group.traverse((o) => {
        if (!o.material || o.userData.baseOpacity === undefined) return;
        o.material.opacity = o.userData.baseOpacity * e;
        if (k >= 1) o.material.transparent = o.userData.baseTransparent;
      });
      return k < 1;
    });
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  onHover(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster
      .intersectObjects(Object.values(this.slots).map((s) => s.group), true)
      .find((h) => findPart(h.object) && findPart(h.object).cat !== "case" && h.object.visible);
    const part = hit && findPart(hit.object);
    if (!part) return void (this.tooltip.style.display = "none");
    this.tooltip.textContent = `${part.brand} ${part.name}`;
    this.tooltip.style.display = "block";
    this.tooltip.style.left = `${e.clientX - r.left + 14}px`;
    this.tooltip.style.top = `${e.clientY - r.top + 14}px`;
  }

  // ---------- echte 3D-Modelle ----------

  setManifest(entries) {
    this.manifest = Array.isArray(entries) ? entries : [];
    this.rebuildAll();
  }

  setCustomModel(partId, buffer) {
    if (buffer) this.customModels.set(partId, buffer);
    else this.customModels.delete(partId);
    this.gltfCache.delete(`custom:${partId}`);
    this.rebuildAll();
  }

  setRotation(partId, quarterTurns) {
    this.rotations.set(partId, quarterTurns % 4);
    this.rebuildAll();
  }

  hasCustomModel(part) {
    return this.customModels.has(part.id) || !!this.manifestEntry(part);
  }

  manifestEntry(part) {
    const full = `${part.brand} ${part.name}`.toLowerCase();
    return (
      this.manifest.find((m) => m.cat === part.cat && m.match && full.includes(m.match.toLowerCase())) ||
      this.manifest.find((m) => m.cat === part.cat && !m.match)
    );
  }

  loadModel(part) {
    const custom = this.customModels.get(part.id);
    const entry = !custom && this.manifestEntry(part);
    if (!custom && !entry) return null;
    const key = custom ? `custom:${part.id}` : `file:${entry.file}`;
    if (!this.gltfCache.has(key)) {
      const loader = new GLTFLoader();
      const p = custom ? loader.parseAsync(custom.slice(0), "") : loader.loadAsync(`models/${entry.file}`);
      this.gltfCache.set(key, p.then((g) => g.scene));
    }
    return this.gltfCache.get(key);
  }

  // Ersetzt den Inhalt einer Gruppe durch ein geladenes Modell, eingepasst in
  // den Umriss des prozeduralen Modells. Die Ausrichtung wird automatisch
  // gewählt (längste Achse auf längste Achse); Nutzer können weiterdrehen.
  async applyModel(group, part) {
    const pending = this.loadModel(part);
    if (!pending) return;
    let src;
    try {
      src = await pending;
    } catch (err) {
      console.warn(`3D-Modell für ${part.name} konnte nicht geladen werden`, err);
      return;
    }
    if (!group.parent) return; // inzwischen entfernt
    // Umriss im Ursprung messen (die Gruppe kann gerade noch einfliegen).
    const flyPos = group.position.clone();
    group.position.set(0, 0, 0);
    group.updateMatrixWorld(true);
    const target = new THREE.Box3().setFromObject(group);
    group.position.copy(flyPos);
    const tSize = target.getSize(new THREE.Vector3());
    const tCenter = target.getCenter(new THREE.Vector3());

    const model = src.clone(true);
    const holder = new THREE.Group();
    holder.add(model);
    const orientations = [[0, 0, 0], [0, 0, Math.PI / 2], [0, Math.PI / 2, 0], [Math.PI / 2, 0, 0], [Math.PI / 2, 0, Math.PI / 2], [0, Math.PI / 2, Math.PI / 2]];
    let best = null;
    for (const o of orientations) {
      holder.rotation.set(...o);
      holder.updateMatrixWorld(true);
      const s = new THREE.Box3().setFromObject(holder).getSize(new THREE.Vector3());
      const scale = Math.min(tSize.x / s.x, tSize.y / s.y, tSize.z / s.z);
      const fill = (s.x * scale) / tSize.x + (s.y * scale) / tSize.y + (s.z * scale) / tSize.z;
      if (!best || fill > best.fill) best = { o, scale, fill };
    }
    holder.rotation.set(...best.o);
    // Zusätzliche Vierteldrehungen des Nutzers um die längste Achse des Umrisses.
    const turns = this.rotations.get(part.id) || 0;
    if (turns) {
      const axis = tSize.x >= tSize.y && tSize.x >= tSize.z ? "x" : tSize.y >= tSize.z ? "y" : "z";
      const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...["x", "y", "z"].map((a) => +(a === axis))), (turns * Math.PI) / 2);
      holder.quaternion.premultiply(q);
    }
    holder.scale.setScalar(best.scale);
    holder.updateMatrixWorld(true);
    const mBox = new THREE.Box3().setFromObject(holder);
    holder.position.add(tCenter.clone().sub(mBox.getCenter(new THREE.Vector3())));

    for (const child of [...group.children]) {
      group.remove(child);
      dispose(child);
    }
    holder.traverse((o) => {
      if (o.isMesh) {
        o.castShadow = o.receiveShadow = true;
        o.material = o.material.clone();
        o.userData.baseOpacity = o.material.opacity;
        o.userData.baseTransparent = o.material.transparent;
      }
    });
    group.add(holder);
  }

  rebuildAll() {
    if (!this.lastBuild) return;
    for (const slot of Object.values(this.slots)) slot.sig = "";
    this.update(this.lastBuild, { animate: false });
  }

  // ---------- Build anzeigen ----------

  // build = { cpu, mobo, ram, gpu, cooler, psu, case, storage: [] }
  update(build, { animate = true } = {}) {
    this.lastBuild = build;
    const board = BOARD[build.mobo?.formFactor] || BOARD.ATX;
    const ff = build.mobo?.formFactor;
    const wanted = {};
    const modelSig = (p) => `${this.customModels.has(p.id) ? "c" : ""}${this.manifestEntry(p)?.file ?? ""}${this.rotations.get(p.id) ?? 0}`;
    const put = (key, part, makeFn, extra = "") => {
      if (part) wanted[key] = { part, makeFn, sig: `${part.id}|${ff}|${extra}|${modelSig(part)}` };
    };
    put("case", build.case, () => makeCase(build.case));
    put("mobo", build.mobo, () => makeMobo(build.mobo, board));
    put("cpu", build.cpu, () => makeCpu(build.cpu, board));
    put("cooler", build.cooler, () => makeCooler(build.cooler, board));
    put("ram", build.ram, () => makeRam(build.ram, board));
    put("gpu", build.gpu, () => makeGpu(build.gpu, board));
    put("psu", build.psu, () => makePsu(build.psu));
    if (build.psu && (build.mobo || build.gpu)) {
      put("cables", build.psu, () => makeCables(build, board), `${build.mobo?.id}|${build.gpu?.id}|${build.gpu?.tdp}`);
      wanted.cables.custom = false;
    }
    let m2 = 0, sata = 0;
    build.storage.forEach((s, i) => {
      const slot = s.kind === "m2" ? m2++ : sata++;
      put(`storage${i}`, s, () => makeStorage(s, board, slot), `${s.kind}${slot}`);
    });

    for (const [key, slot] of Object.entries(this.slots)) {
      if (!wanted[key] || wanted[key].sig !== slot.sig) {
        this.scene.remove(slot.group);
        dispose(slot.group);
        delete this.slots[key];
      }
    }
    for (const [key, w] of Object.entries(wanted)) {
      if (this.slots[key]) continue;
      const group = w.makeFn();
      group.userData.part = key === "cables" ? null : w.part;
      group.traverse((o) => {
        if (!o.isMesh) return;
        o.castShadow = !(o.material.transparent && o.material.opacity < 0.5);
        o.receiveShadow = true;
        o.userData.baseOpacity = o.material.opacity;
        o.userData.baseTransparent = o.material.transparent;
      });
      this.scene.add(group);
      const isNew = animate && !this.prevIds?.has(w.part.id + key);
      if (isNew && key !== "case" && key !== "cables") {
        const to = group.position.clone();
        group.traverse((o) => o.isMesh && (o.material.transparent = true));
        this.anims.push({ group, from: to.clone().add(new THREE.Vector3(28, 6, 0)), to });
      }
      if (w.custom !== false && key !== "cables") this.applyModel(group, w.part);
      this.slots[key] = { group, sig: w.sig };
    }
    this.prevIds = new Set(Object.entries(wanted).map(([k, w]) => w.part.id + k));
  }

  snapshot() {
    this.renderer.render(this.scene, this.camera);
    return this.renderer.domElement.toDataURL("image/png");
  }
}

function findPart(obj) {
  for (let o = obj; o; o = o.parent) if (o.userData.part) return o.userData.part;
  return null;
}

function dispose(obj) {
  obj.traverse((o) => {
    o.geometry?.dispose();
    if (o.material) {
      o.material.map?.dispose();
      o.material.dispose();
    }
  });
}

// ---------- Gehäuse ----------

function makeCase(part) {
  const g = new THREE.Group();
  const { w, h, d } = CASE;
  const accent = brandColor(part.brand);
  const steel = M.steel();
  g.add(at(box(0.3, h, d, steel), -w / 2 + 0.15, 0, 0)); // Mainboard-Träger
  g.add(at(box(w, 0.4, d, steel), 0, h / 2 - 0.2, 0)); // Deckel
  g.add(at(box(w, 0.6, d, steel), 0, -h / 2 + 0.3, 0)); // Boden
  g.add(at(box(w, h, 0.4, M.steel(0x24272e)), 0, 0, -d / 2 + 0.2)); // Rückwand
  // Front als Mesh-Gitter: Rahmen + dunkle, leicht durchscheinende Fläche
  const mesh = box(w - 1, h - 1, 0.25, new THREE.MeshStandardMaterial({ color: 0x0f1013, roughness: 0.9, transparent: true, opacity: 0.55 }));
  g.add(at(mesh, 0, 0, d / 2 - 0.15));
  // Deckelgitter
  g.add(at(box(w - 4, 0.05, d - 6, M.plastic(0x0c0d10)), 0, h / 2 + 0.01, 0));
  // Glasseitenteil mit Rahmen
  const glass = box(0.4, h - 0.8, d - 0.8, M.glass());
  g.add(at(glass, w / 2 - 0.2, 0, 0));
  for (const [sy, sz, py, pz] of [[0.4, d, h / 2 - 0.2, 0], [0.4, d, -h / 2 + 0.2, 0], [h, 0.4, 0, d / 2 - 0.2], [h, 0.4, 0, -d / 2 + 0.2]]) {
    g.add(at(box(0.5, sy, sz, steel), w / 2 - 0.2, py, pz));
  }
  // Netzteilabdeckung
  g.add(at(box(w - 0.8, 0.4, d * 0.72, steel), 0.2, -h / 2 + 10, -d / 2 + (d * 0.72) / 2));
  g.add(at(box(w - 0.8, 10, 0.4, steel), 0.2, -h / 2 + 5, -d / 2 + d * 0.72));
  const logo = label(part.brand.toUpperCase(), 7, 1.2, { fg: "#c9ccd3" });
  g.add(faceX(at(logo, w / 2 - 0.35, -h / 2 + 5, 0)));
  // Füße
  for (const [x, z] of [[-w / 2 + 2, -d / 2 + 3], [w / 2 - 2, -d / 2 + 3], [-w / 2 + 2, d / 2 - 3], [w / 2 - 2, d / 2 - 3]]) {
    g.add(at(rbox(3, 1, 4, 0.3, M.plastic(0x101114)), x, -h / 2 - 0.5, z));
  }
  // Lüfter: 3 vorne, 1 hinten
  for (const y of [12.5, 0, -12.5]) g.add(at(fan(6, { ring: accent }), 0, y, d / 2 - 1.8));
  g.add(at(fan(6, { ring: accent }), -1, 14, -d / 2 + 1.8));
  return g;
}

// ---------- Mainboard ----------

const cpuU = (b) => (b.w > 20 ? 11 : 8);
const ramStartU = (b) => cpuU(b) + 5.5;

function makeMobo(part, b) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  g.add(place(box(0.2, b.h, b.w, M.pcb()), b.w / 2, b.h / 2, 0));
  // Schrauben
  for (const [u, v] of [[0.6, 0.6], [b.w - 0.6, 0.6], [0.6, b.h - 0.6], [b.w - 0.6, b.h - 0.6], [cpuU(b), b.h - 0.6]]) {
    const s = cyl(0.25, 0.15, M.alu(), 12);
    s.rotation.z = Math.PI / 2;
    g.add(place(s, u, v, 0.15));
  }
  // I/O-Abdeckung mit Akzentstreifen
  g.add(place(rbox(2.6, 11, 3.2, 0.25, M.steel(0x2a2d33)), 1.8, 6.5, 1.4));
  g.add(place(box(0.05, 9, 0.35, M.glow(accent)), 3.0, 6.5, 2.72));
  // Spannungswandler-Kühler (gerippt)
  const vrmTop = rbox(1.8, 2.2, 9.5, 0.2, M.steel(0x33363d));
  g.add(place(vrmTop, cpuU(b), 1.7, 1.0));
  g.add(place(fins(10, [0.25, 2.25, 0.18], 0.9, "z", M.steel(0x1b1d22)), cpuU(b), 1.7, 2.0));
  g.add(place(rbox(1.8, 8.5, 2.2, 0.2, M.steel(0x33363d)), 4.6, 8.5, 1.0));
  // CPU-Sockel
  g.add(place(box(0.35, 5.4, 5.4, M.alu()), cpuU(b), 7, 0.25));
  g.add(place(box(0.38, 4.2, 4.2, M.plastic(0x2a2a2a)), cpuU(b), 7, 0.27));
  // RAM-Slots
  for (let i = 0; i < b.slots; i++) {
    g.add(place(box(0.9, 13.6, 0.6, M.plastic(i % 2 ? 0x3a3d44 : 0x1a1b1f)), ramStartU(b) + i * 1.1, 9, 0.45));
  }
  // 24-Pin-Anschluss
  g.add(place(box(1.3, 5.2, 1.1, M.plastic(0x101114)), b.w - 0.8, 11, 0.65));
  // PCIe-Slots (oberster verstärkt)
  g.add(place(box(0.9, 0.9, 9, M.alu()), 7.5, b.pcie, 0.45));
  for (let i = 1; i <= b.pcieExtra; i++) {
    const v = b.pcie + i * 6;
    if (v < b.h - 1.5) g.add(place(box(0.8, 0.8, i === 1 ? 9 : 4, M.plastic(0x101114)), i === 1 ? 7.5 : 5, v, 0.4));
  }
  // M.2-Abdeckung zwischen CPU und PCIe
  g.add(place(rbox(0.35, 2.6, 8.5, 0.1, M.steel(0x2c2f36)), 10, b.pcie - 2.6, 0.3));
  // Chipsatz-Kühler mit Herstellerlogo
  if (b.h > 20) {
    g.add(place(rbox(0.9, 6, 6, 0.3, M.steel(0x2c2f36)), b.w - 6, b.h - 5.5, 0.55));
    g.add(faceX(place(label(part.brand.toUpperCase(), 5, 1.4, { fg: accent }), b.w - 6, b.h - 5.5, 1.02)));
  }
  // Audio-Kondensatoren und Bauteile
  for (let i = 0; i < 5; i++) {
    const c = cyl(0.35, 0.8, M.gold(), 12);
    c.rotation.z = Math.PI / 2;
    g.add(place(c, 1.5 + (i % 2) * 1, b.h - 2 - Math.floor(i / 2) * 1.1, 0.5));
  }
  return g;
}

// ---------- CPU ----------

function makeCpu(part, b) {
  const g = new THREE.Group();
  g.add(place(box(0.15, 4, 4, M.pcbGreen()), cpuU(b), 7, 0.5));
  g.add(place(rbox(0.35, 3.3, 3.3, 0.15, M.alu()), cpuU(b), 7, 0.75));
  g.add(faceX(place(label(part.brand.toUpperCase(), 2.6, 0.7, { fg: "#55595f" }), cpuU(b), 6.5, 0.93)));
  g.add(faceX(place(label(part.name, 2.8, 0.45, { fg: "#55595f", weight: 500 }), cpuU(b), 7.3, 0.93)));
  return g;
}

// ---------- Kühler ----------

function makeCooler(part, b) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  const u = cpuU(b);
  if (part.heightMm === 0) {
    // AIO: Pumpe, Schläuche, Radiator am Deckel mit drei Lüftern
    g.add(place(rbox(2.4, 6, 6, 0.6, M.plastic(0x1a1c20)), u, 7, 2.0));
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.2, 0.15, 8, 48), M.glow(accent));
    g.add(faceX(place(ring, u, 7, 3.22)));
    g.add(faceX(place(label(part.brand, 3.4, 0.9), u, 7, 3.22)));
    const radX = -0.5, radY = CASE.h / 2 - 1.9, len = 39;
    g.add(at(box(12, 2.7, len, M.steel(0x16181c)), radX, radY, 0));
    g.add(at(fins(90, [11.4, 2.6, 0.06], 0.42, "z", M.steel(0x2c2f36)), radX, radY, 0));
    for (const z of [-12.6, 0, 12.6]) {
      const f = fan(5.9, { ring: accent });
      f.rotation.x = Math.PI / 2;
      g.add(at(f, radX, radY - 2.7, z));
    }
    const tubeMat = M.plastic(0x0e0f12);
    const p0 = onBoard(u + 1.5, 5.5, 3), p1 = onBoard(u + 1.5, 8.5, 3);
    g.add(tube([[p0.x, p0.y, p0.z], [p0.x + 3, p0.y + 6, p0.z + 6], [radX + 4, radY - 2, len / 2 - 3], [radX + 4, radY - 0.5, len / 2 + 0.5]], 0.55, tubeMat));
    g.add(tube([[p1.x, p1.y, p1.z], [p1.x + 5, p1.y + 7, p1.z + 7], [radX + 1.5, radY - 2.5, len / 2 - 2], [radX + 1.5, radY - 0.5, len / 2 + 0.5]], 0.55, tubeMat));
    return g;
  }
  const h = (part.heightMm ?? 155) / 10;
  g.add(place(box(0.6, 4, 4, M.alu()), u, 7, 1.0)); // Bodenplatte
  if (h < 8) {
    // Low-Profile: flacher Kühlkörper, Lüfter oben
    g.add(place(fins(14, [h - 2, 9, 0.12], 0.6, "z", M.alu()), u, 7, 1.3 + (h - 2) / 2));
    const f = fan(4.4, { depth: 1.4 });
    f.rotation.y = Math.PI / 2;
    g.add(place(f, u, 7, h - 0.2));
    return g;
  }
  const finCount = Math.floor((h - 3.5) / 0.22);
  const stack = fins(finCount, [0.05, 12, 5.2], 0.22, "x", M.alu());
  g.add(place(stack, u, 7, 3.2 + (h - 3.5) / 2));
  for (const dv of [-2.4, -0.8, 0.8, 2.4]) {
    const pipe = cyl(0.3, h - 1.2, M.copper(), 12);
    pipe.rotation.z = Math.PI / 2;
    g.add(place(pipe, u, 7 + dv, 0.9 + (h - 1.2) / 2));
  }
  g.add(place(rbox(0.6, 12.4, 5.6, 0.25, M.plastic(0x15171b)), u, 7, h - 0.05));
  const capLabel = label(part.brand.toUpperCase(), 10, 1.4, { fg: accent });
  capLabel.rotation.set(0, Math.PI / 2, Math.PI / 2); // Schrift entlang der langen Seite
  g.add(place(capLabel, u, 7, h + 0.26));
  const f = fan(6, { ring: part.maxTdp > 220 ? accent : null });
  g.add(place(f, u + 2.6 + 1.3, 7, h - 6.4 + 0.3));
  return g;
}

// ---------- RAM ----------

function makeRam(part, b) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  const order = b.slots === 4 ? [1, 3, 0, 2] : [0, 1];
  for (let i = 0; i < Math.min(part.sticks, b.slots); i++) {
    const u = ramStartU(b) + order[i] * 1.1;
    g.add(place(box(3.0, 13.3, 0.12, M.pcbGreen()), u, 9, 2.1));
    g.add(place(box(0.35, 13.0, 0.13, M.gold()), u, 9, 0.75));
    for (const side of [-1, 1]) g.add(place(rbox(3.1, 13.3, 0.22, 0.08, M.steel(0x23252b)), u + side * 0.17, 9, 2.45));
    g.add(place(rbox(0.5, 13.0, 0.55, 0.15, M.glow(accent)), u, 9, 4.2));
  }
  return g;
}

// ---------- Grafikkarte ----------

function makeGpu(part, b) {
  const g = new THREE.Group();
  const L = part.lengthMm / 10;
  const T = part.tdp > 300 ? 6.6 : part.tdp > 200 ? 5.6 : 4.2; // Bauhöhe in Slots
  const H = 12.6;
  const accent = brandColor(part.brand);
  const cx = 0.4 + H / 2;
  // Backplate (oben) mit Logo
  g.add(place(rbox(H, 0.3, L, 0.12, M.steel(0x2a2d33)), L / 2 + 0.5, b.pcie - 0.45, cx));
  const top = label(gpuLabel(part), L * 0.5, 1.4, { fg: "#9aa0a8" });
  top.rotation.set(-Math.PI / 2, 0, Math.PI / 2);
  g.add(place(top, L / 2 + 0.5, b.pcie - 0.61, cx));
  g.add(place(box(H - 0.4, 0.15, L - 0.6, M.pcb()), L / 2 + 0.5, b.pcie - 0.15, cx));
  // Kühlkörper (sichtbar an den Rändern) und Verkleidung
  const shroud = rbox(H, T - 0.7, L, 0.35, M.plastic(0x1d1f24));
  g.add(place(shroud, L / 2 + 0.5, b.pcie + 0.25 + (T - 0.7) / 2 + 0.25, cx));
  // Seitenteil zum Glas hin: Name und Leuchtstreifen
  g.add(faceX(place(label(gpuLabel(part), L * 0.5, (T - 0.7) * 0.45), L * 0.38, b.pcie + T / 2, cx + H / 2 + 0.02)));
  g.add(place(box(0.08, 0.25, L * 0.9, M.glow(accent)), L / 2 + 0.5, b.pcie + T - 0.7, cx + H / 2 + 0.03));
  // Lüfter auf der Unterseite
  const n = L > 28 ? 3 : 2;
  const r = Math.min(4.6, L / (2 * n) - 0.25);
  for (let i = 0; i < n; i++) {
    const f = fan(r, { square: false, depth: 0.8 });
    f.rotation.x = Math.PI / 2;
    g.add(place(f, ((i + 0.5) / n) * L + 0.5, b.pcie + T + 0.05, cx));
  }
  // Slotblech und Stromanschluss
  g.add(place(box(H + 1.2, T + 0.3, 0.15, M.alu()), -0.1, b.pcie + T / 2 - 0.2, cx + 0.3));
  g.add(place(box(1.0, 0.9, 2.2, M.plastic(0x0e0f12)), L * 0.7, b.pcie + 0.4, cx + H / 2 - 0.2));
  return g;
}

function gpuLabel(part) {
  const m = part.name.match(/(GeForce\s+)?RTX\s*\d{4}(\s*Ti)?(\s*SUPER)?|Radeon\s+RX\s*\d{4}(\s*XT|\s*XTX|\s*GRE)?|RX\s*\d{4}(\s*XT|\s*XTX)?|Arc\s+\w+\s*\w*/i);
  return (m ? m[0] : part.name).toUpperCase();
}

// ---------- Netzteil ----------

function makePsu(part) {
  const g = new THREE.Group();
  const x = -CASE.w / 2 + 8, y = -CASE.h / 2 + 5.1, z = -CASE.d / 2 + 9;
  g.add(at(rbox(15, 8.6, 16, 0.4, M.steel(0x16181b)), x, y, z));
  const sticker = label(`${part.brand} · ${part.watt} W`, 9, 1.6, { bg: "#24272d", fg: "#e8eaee" });
  g.add(faceX(at(sticker, x + 7.52, y + 1, z)));
  g.add(faceX(at(label(part.efficiency || "", 6, 1, { fg: "#b8bcc3", weight: 500 }), x + 7.52, y - 1.2, z)));
  // modulare Anschlüsse vorne
  for (let i = 0; i < 6; i++) g.add(at(box(1.6, 1, 0.2, M.plastic(0x0a0b0d)), x - 5 + (i % 3) * 3.2, y - 1 + Math.floor(i / 3) * 1.6, z + 8.05));
  return g;
}

// ---------- Kabel ----------

function makeCables(build, b) {
  const g = new THREE.Group();
  const sleeve = M.plastic(0x101114);
  const zg = BACK + b.w + 1.6; // Kabeldurchführung rechts vom Mainboard
  if (build.mobo) {
    const end = onBoard(b.w - 0.8, 11, 1.2);
    for (let i = 0; i < 6; i++) {
      const dy = (i - 2.5) * 0.4;
      g.add(tube([[-10.9, end.y - 8 + dy, zg], [-9.5, end.y - 7 + dy, zg], [end.x + 0.4, end.y + dy, end.z + 1.6], [end.x, end.y + dy, end.z + 0.6]], 0.17, sleeve));
    }
    const cpuEnd = onBoard(3.5, 0.9, 0.8);
    for (let i = 0; i < 3; i++) {
      const dz = (i - 1) * 0.4;
      g.add(tube([[-10.9, TOP + 1.8, cpuEnd.z + dz], [-9.5, TOP + 1.6, cpuEnd.z + dz], [cpuEnd.x, cpuEnd.y + 0.5, cpuEnd.z + dz]], 0.16, sleeve));
    }
  }
  if (build.gpu) {
    const L = build.gpu.lengthMm / 10;
    const end = onBoard(L * 0.7, b.pcie + 0.4, 12.4);
    for (let i = 0; i < 4; i++) {
      const dz = (i - 1.5) * 0.4;
      g.add(tube([[-9, -CASE.h / 2 + 10.3, end.z + dz], [end.x - 2, -CASE.h / 2 + 13, end.z + dz], [end.x + 1.2, end.y - 4, end.z + dz], [end.x + 0.5, end.y - 0.4, end.z + dz]], 0.15, sleeve));
    }
  }
  return g;
}

// ---------- Laufwerke ----------

function makeStorage(part, b, slot) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  if (part.kind === "m2") {
    const v = b.pcie - 2.6 + slot * 6.5;
    g.add(place(box(0.25, 2.2, 8, M.pcb()), 10, v, 0.55));
    g.add(place(box(0.05, 2.0, 6.8, new THREE.MeshStandardMaterial({ color: accent, roughness: 0.5 })), 10.4, v, 0.69));
    g.add(faceX(place(label(part.brand, 3.6, 1.2), 10.4, v, 0.72)));
    return g;
  }
  const hdd = part.hdd || /HDD/i.test(part.name);
  const size = hdd ? [10.2, 2.6, 14.7] : [7, 0.7, 10];
  const pos = [-1.5, -CASE.h / 2 + 1.0 + size[1] / 2 + slot * (size[1] + 0.4), CASE.d / 2 - 11];
  g.add(at(rbox(...size, 0.15, hdd ? M.alu() : M.steel(0x24272d)), ...pos));
  const top = label(part.brand, size[0] * 0.7, size[2] * 0.25, { bg: hdd ? "#2b2e34" : accent, fg: "#ffffff" });
  top.rotation.x = -Math.PI / 2;
  top.rotation.z = Math.PI / 2;
  g.add(at(top, pos[0], pos[1] + size[1] / 2 + 0.01, pos[2]));
  return g;
}
