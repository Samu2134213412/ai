// 3D-Ansicht des Builds mit three.js. Einheiten: Zentimeter.
// Koordinaten: x = vom Mainboard weg (Richtung Glasseitenteil), y = oben,
// z = vorne (Rückseite des Gehäuses liegt bei negativem z).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { brandColor } from "./icons.js";

const CASE = { w: 22, h: 46, d: 45 };
const BACK = -CASE.d / 2 + 2; // Hinterkante Mainboard
const TOP = CASE.h / 2 - 3; // Oberkante Mainboard
const MOBO_X = -CASE.w / 2 + 1.5;

const BOARD = {
  ATX: { w: 24.4, h: 30.5, pcie: 12.5 },
  mATX: { w: 24.4, h: 24.4, pcie: 12.5 },
  ITX: { w: 17, h: 17, pcie: 13 },
};

const mat = (color, opts = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.35, ...opts });
const box = (sx, sy, sz, material) => new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), material);

export class PcScene {
  constructor(container) {
    this.container = container;
    this.slots = {}; // key -> { group, sig }
    this.anims = [];

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);
    this.renderer = renderer;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 1, 500);
    this.camera.position.set(75, 22, 48);
    this.controls = new OrbitControls(this.camera, renderer.domElement);
    this.controls.target.set(0, 0, 0);
    this.controls.enableDamping = true;
    this.controls.minDistance = 30;
    this.controls.maxDistance = 180;

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 2.2);
    sun.position.set(60, 80, 40);
    this.scene.add(sun);
    const rgb = new THREE.PointLight(0x6a5cff, 60, 60);
    rgb.position.set(0, 10, 10);
    this.scene.add(rgb);

    const floor = new THREE.Mesh(new THREE.CircleGeometry(60, 48), mat(0x20242c, { roughness: 1, metalness: 0, transparent: true, opacity: 0.5 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -CASE.h / 2 - 0.01;
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
    this.anims = this.anims.filter((a) => {
      const k = Math.min(1, (t - (a.start ??= t)) / 650);
      const e = 1 - Math.pow(1 - k, 3);
      a.group.position.lerpVectors(a.from, a.to, e);
      a.group.traverse((o) => {
        if (!o.material) return;
        o.material.opacity = o.userData.baseOpacity * e;
        if (k >= 1) o.material.transparent = o.userData.baseOpacity < 1;
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
      .find((h) => findPart(h.object) && findPart(h.object).cat !== "case");
    const part = hit && findPart(hit.object);
    if (!part) return void (this.tooltip.style.display = "none");
    this.tooltip.textContent = `${part.brand} ${part.name}`;
    this.tooltip.style.display = "block";
    this.tooltip.style.left = `${e.clientX - r.left + 14}px`;
    this.tooltip.style.top = `${e.clientY - r.top + 14}px`;
  }

  // build = { cpu, mobo, ram, gpu, cooler, psu, case, storage: [] }
  update(build) {
    const board = BOARD[build.mobo?.formFactor] || BOARD.ATX;
    const wanted = {};
    const put = (key, part, makeFn) => {
      if (part) wanted[key] = { part, makeFn, sig: `${part.id}|${build.mobo?.formFactor}` };
    };
    put("case", build.case, () => makeCase(build.case));
    put("mobo", build.mobo, () => makeMobo(build.mobo, board));
    put("cpu", build.cpu, () => makeCpu(build.cpu, board));
    put("cooler", build.cooler, () => makeCooler(build.cooler, board));
    put("ram", build.ram, () => makeRam(build.ram, board));
    put("gpu", build.gpu, () => makeGpu(build.gpu, board));
    put("psu", build.psu, () => makePsu(build.psu));
    let m2 = 0, sata = 0;
    build.storage.forEach((s, i) => {
      const slot = s.kind === "m2" ? m2++ : sata++;
      put(`storage${i}`, s, () => makeStorage(s, board, slot));
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
      group.userData.part = w.part;
      group.traverse((o) => {
        if (!o.material) return;
        o.material = o.material.clone();
        o.userData.baseOpacity = o.material.transparent ? o.material.opacity : 1;
      });
      this.scene.add(group);
      // Nur neu eingesetzte Teile einfliegen lassen (nicht bei reinem Neuaufbau).
      const isNew = !this.prevIds?.has(w.part.id + key);
      if (isNew && key !== "case") {
        const to = group.position.clone();
        group.traverse((o) => o.material && (o.material.transparent = true));
        this.anims.push({ group, from: to.clone().add(new THREE.Vector3(28, 6, 0)), to });
      }
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

function dispose(group) {
  group.traverse((o) => {
    o.geometry?.dispose();
    o.material?.dispose();
  });
}

// Position auf dem Mainboard: u = Abstand von der Hinterkante, v = Abstand von oben.
const onBoard = (u, v, x = 0) => new THREE.Vector3(MOBO_X + x, TOP - v, BACK + u);

function makeCase(part) {
  const g = new THREE.Group();
  const shell = box(CASE.w, CASE.h, CASE.d, mat(0x2a2e36, { transparent: true, opacity: 0.12, side: THREE.BackSide }));
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(shell.geometry),
    new THREE.LineBasicMaterial({ color: brandColor(part.brand), transparent: true, opacity: 0.9 }),
  );
  const backWall = box(0.4, CASE.h, CASE.d, mat(0x1b1e24));
  backWall.position.x = -CASE.w / 2;
  const shroud = box(CASE.w, 0.4, CASE.d * 0.75, mat(0x1b1e24));
  shroud.position.set(0, -CASE.h / 2 + 10, -CASE.d * 0.125);
  const frontFan = (y) => {
    const f = new THREE.Mesh(new THREE.TorusGeometry(5.2, 0.5, 8, 32), mat(0x6a5cff, { emissive: 0x3a2cff, emissiveIntensity: 0.8 }));
    f.rotation.y = 0;
    f.position.set(0, y, CASE.d / 2 - 1.2);
    return f;
  };
  g.add(shell, edges, backWall, shroud, frontFan(10), frontFan(-2));
  return g;
}

function makeMobo(part, b) {
  const g = new THREE.Group();
  const pcb = box(0.3, b.h, b.w, mat(0x1d3a2b, { roughness: 0.8 }));
  pcb.position.copy(onBoard(b.w / 2, b.h / 2));
  const io = box(2.5, 5, 4, mat(0x3a3f47));
  io.position.copy(onBoard(2, 5, 1.4));
  const vrm = box(1.6, 2, 8, mat(brandColor(part.brand)));
  vrm.position.copy(onBoard(5, 2.5, 1));
  const pcie = box(0.8, 0.8, 9, mat(0x444444));
  pcie.position.copy(onBoard(6, b.pcie, 0.5));
  const chipset = box(0.8, 4, 4, mat(brandColor(part.brand)));
  chipset.position.copy(onBoard(b.w - 6, b.h - 6, 0.5));
  const socket = box(0.6, 5, 5, mat(0x9aa0a6, { metalness: 0.8 }));
  socket.position.copy(onBoard(cpuU(b), 7, 0.4));
  g.add(pcb, io, vrm, pcie, chipset, socket);
  return g;
}

const cpuU = (b) => (b.w > 20 ? 11 : 8);

function makeCpu(part, b) {
  const g = new THREE.Group();
  const ihs = box(0.5, 4, 4, mat(0xc9ccd1, { metalness: 0.9, roughness: 0.25 }));
  ihs.position.copy(onBoard(cpuU(b), 7, 0.9));
  const logo = box(0.05, 1.6, 1.6, mat(brandColor(part.brand)));
  logo.position.copy(onBoard(cpuU(b), 7, 1.18));
  g.add(ihs, logo);
  return g;
}

function makeCooler(part, b) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  if (!part.heightMm) {
    // AIO: Pumpenblock + Radiator am Gehäusedeckel
    const pump = new THREE.Mesh(new THREE.CylinderGeometry(3, 3, 3, 32), mat(0x22252b));
    pump.rotation.z = Math.PI / 2;
    pump.position.copy(onBoard(cpuU(b), 7, 2.6));
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.6, 0.25, 8, 32), mat(accent, { emissive: accent, emissiveIntensity: 0.9 }));
    ring.rotation.y = Math.PI / 2;
    ring.position.copy(onBoard(cpuU(b), 7, 4.15));
    const rad = box(12, 2.8, 39, mat(0x1b1e24));
    rad.position.set(0, CASE.h / 2 - 1.8, 0);
    g.add(pump, ring, rad);
    return g;
  }
  const h = part.heightMm / 10;
  const towers = part.heightMm > 100 ? 1 : 0;
  const fin = box(h - 1, 12, 5, mat(0xb8bcc2, { metalness: 0.8, roughness: 0.3 }));
  fin.position.copy(onBoard(cpuU(b), 7, 1 + h / 2));
  const fan = box(h - 1.5, 12, 2.5, mat(accent));
  fan.position.copy(onBoard(cpuU(b) + 3.8, 7, 1 + h / 2));
  g.add(fin, fan);
  if (towers) {
    for (let i = -2; i <= 2; i++) {
      const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, h - 1, 10), mat(0xb87333, { metalness: 0.9 }));
      pipe.rotation.z = Math.PI / 2;
      pipe.position.copy(onBoard(cpuU(b) - 0.5, 7 + i * 1.8, 1 + h / 2));
      g.add(pipe);
    }
  }
  return g;
}

function makeRam(part, b) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  const slots = b.w > 20 ? 4 : 2;
  const startU = cpuU(b) + 5.5;
  // Riegel in Slot 2 und 4 (Dual-Channel), sonst von vorne auffüllen.
  const order = slots === 4 ? [1, 3, 0, 2] : [0, 1];
  for (let i = 0; i < Math.min(part.sticks, slots); i++) {
    const u = startU + order[i] * 1.1;
    const stick = box(3.4, 13.3, 0.7, mat(0x2b2f36));
    stick.position.copy(onBoard(u, 9, 2));
    const bar = box(0.4, 13.3, 0.75, mat(accent, { emissive: accent, emissiveIntensity: 0.7 }));
    bar.position.copy(onBoard(u, 9, 3.8));
    g.add(stick, bar);
  }
  return g;
}

function makeGpu(part, b) {
  const g = new THREE.Group();
  const len = part.lengthMm / 10;
  const slotsThick = part.tdp > 300 ? 6.5 : part.tdp > 200 ? 5.5 : 4.2;
  const accent = brandColor(part.brand);
  const shroud = box(12, slotsThick, len, mat(0x23262c));
  shroud.position.copy(onBoard(len / 2 + 0.5, b.pcie + slotsThick / 2 - 0.3, 6.3));
  const stripe = box(12.05, 0.4, len * 0.9, mat(accent, { emissive: accent, emissiveIntensity: 0.6 }));
  stripe.position.copy(onBoard(len / 2 + 0.5, b.pcie - 0.2, 6.3));
  g.add(shroud, stripe);
  const fans = len > 28 ? 3 : 2;
  for (let i = 0; i < fans; i++) {
    const fan = new THREE.Mesh(new THREE.CylinderGeometry(4.3, 4.3, 0.3, 32), mat(0x111317));
    fan.position.copy(onBoard(((i + 0.5) / fans) * len + 0.5, b.pcie + slotsThick - 0.15, 6.3));
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.35, 16), mat(accent));
    hub.position.copy(fan.position);
    g.add(fan, hub);
  }
  return g;
}

function makePsu(part) {
  const g = new THREE.Group();
  const body = box(15, 8.6, 16, mat(0x23262c));
  body.position.set(-CASE.w / 2 + 8, -CASE.h / 2 + 4.6, -CASE.d / 2 + 9);
  const label = box(0.1, 4, 8, mat(brandColor(part.brand)));
  label.position.set(-CASE.w / 2 + 15.55, -CASE.h / 2 + 4.6, -CASE.d / 2 + 9);
  g.add(body, label);
  return g;
}

function makeStorage(part, b, slot) {
  const g = new THREE.Group();
  const accent = brandColor(part.brand);
  if (part.kind === "m2") {
    const stick = box(0.3, 2.2, 8, mat(0x1d1f24));
    stick.position.copy(onBoard(cpuU(b) - 2 + 4, b.pcie - 2.5 + slot * 6.5, 0.4));
    const sink = box(0.3, 2, 6, mat(accent));
    sink.position.copy(onBoard(cpuU(b) - 2 + 4, b.pcie - 2.5 + slot * 6.5, 0.7));
    g.add(stick, sink);
  } else {
    const isHdd = part.sizeGB >= 2000 && /HDD/.test(part.name);
    const drive = isHdd ? box(10.2, 2.6, 14.7, mat(0x8a8f96, { metalness: 0.8 })) : box(7, 0.7, 10, mat(0x2b2f36));
    drive.position.set(-2, -CASE.h / 2 + 2 + slot * 3.2, CASE.d / 2 - 10);
    const tag = box(isHdd ? 10.25 : 7.05, 0.1, 3, mat(accent));
    tag.position.copy(drive.position).add(new THREE.Vector3(0, isHdd ? 1.31 : 0.36, 0));
    g.add(drive, tag);
  }
  return g;
}
