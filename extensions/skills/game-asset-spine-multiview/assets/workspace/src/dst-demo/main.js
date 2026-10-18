// 饥荒式多方向演示：3D 地面 + 可转镜头，角色和道具都是朝镜头的平面（billboard）。
// 角色有正 / 侧 / 背三套 Spine 骨骼（spine-threejs 官方运行时，SkeletonMesh 就是 three.js 的 Object3D），
// 每帧按「角色朝向」相对「镜头方向」的夹角选一套显示：朝镜头 → 正面，背对 → 背面，其余 → 侧面（朝画面左时 scaleX = −1）。
// 三套共用同名动作（idle / walk / run），切换时把动作时间带过去，步伐不断。
// 资源清单：?rig=<manifest.json>，或页面里 <meta name="dst-rig" content="...">（发布版用），默认 ../../output/dir-test/rig/manifest.json。
// 格式见 output/dir-test/rig/manifest.json 与 scripts/dir-rig.py。触屏：页面里有 #stick / #btn-* 时接上摇杆和按钮。
import * as THREE from "three";
import { AssetManager, AtlasAttachmentLoader, SkeletonJson, SkeletonMesh } from "spine-threejs";

// Spine 贴图没有标色彩空间（ThreeJsTexture 里那行是注释掉的）：关掉 three.js 的色彩管理，按显示值直接混合，
// 与 spine-webgl 的 2D 渲染一致；场景里自己画的贴图也都按显示值处理
THREE.ColorManagement.enabled = false;

const params = new URLSearchParams(location.search);
const manifestUrl = new URL(params.get("rig") || document.querySelector('meta[name="dst-rig"]')?.content ||
  "../../output/dir-test/rig/manifest.json", location.href);

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: params.has("shot") });
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x2b3528);
scene.fog = new THREE.Fog(0x2b3528, 26, 46);
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 200);

function resize() {
  renderer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize);
resize();

// ---------- 小工具 ----------
let seed = 20261010;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
function canvasTex(w, h, draw, repeat) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat, repeat); }
  t.anisotropy = 8;
  return t;
}

// ---------- 地面 ----------
const groundTex = canvasTex(512, 512, (g, w, h) => {
  g.fillStyle = "#5d6b3c"; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 2600; i++) {
    const x = rnd() * w, y = rnd() * h, r = 1 + rnd() * 3.5;
    g.fillStyle = ["#6a7a43", "#536136", "#74844a", "#4b5830"][i % 4];
    g.beginPath(); g.ellipse(x, y, r * 1.8, r, rnd() * 3, 0, 7); g.fill();
  }
  g.strokeStyle = "rgba(40,48,24,.55)"; g.lineWidth = 1.2;
  for (let i = 0; i < 500; i++) {  // 草叶
    const x = rnd() * w, y = rnd() * h;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (rnd() - .5) * 4, y - 3 - rnd() * 5); g.stroke();
  }
}, 14);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.MeshBasicMaterial({ map: groundTex }));
ground.rotation.x = -Math.PI / 2;
scene.add(ground);

// 地面上的土块和石板路：贴地的平面，转镜头时能看出地面在转
const dirtTex = canvasTex(256, 256, (g, w, h) => {
  const gr = g.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, w / 2);
  gr.addColorStop(0, "rgba(122,96,62,1)"); gr.addColorStop(.7, "rgba(112,88,56,.9)"); gr.addColorStop(1, "rgba(112,88,56,0)");
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 160; i++) {
    g.fillStyle = `rgba(${70 + rnd() * 40},${55 + rnd() * 30},${35 + rnd() * 20},.6)`;
    g.beginPath(); g.arc(w / 2 + (rnd() - .5) * w * .7, h / 2 + (rnd() - .5) * h * .7, 1 + rnd() * 3, 0, 7); g.fill();
  }
});
function decal(tex, x, z, sx, sz, rot, y = 0.004) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }));
  m.rotation.set(-Math.PI / 2, 0, rot);
  m.scale.set(sx, sz, 1);
  m.position.set(x, y, z);
  scene.add(m);
  return m;
}
for (let i = 0; i < 18; i++) decal(dirtTex, (rnd() - .5) * 50, (rnd() - .5) * 50, 2 + rnd() * 4, 1.5 + rnd() * 3, rnd() * 6);
const stoneTex = canvasTex(128, 128, (g, w, h) => {
  g.fillStyle = "#8d8a7f"; g.strokeStyle = "#3b3a33"; g.lineWidth = 6;
  g.beginPath(); g.ellipse(w / 2, h / 2, w * .42, h * .36, .3, 0, 7); g.fill(); g.stroke();
  g.fillStyle = "rgba(255,255,255,.18)"; g.beginPath(); g.ellipse(w * .42, h * .4, w * .18, h * .1, .3, 0, 7); g.fill();
});
for (let i = 0; i < 16; i++) {  // 一圈石板，中心在出生点北边
  const a = i / 16 * Math.PI * 2;
  decal(stoneTex, Math.cos(a) * 3.2, -6 + Math.sin(a) * 3.2, .9, .9, a, 0.006);
}
for (let i = 0; i < 22; i++) decal(stoneTex, 0.15 * Math.sin(i), 6 - i * 0.55 - 6, .55, .55, i, 0.006);  // 一条小路

// ---------- 影子 ----------
const shadowTex = canvasTex(128, 64, (g, w, h) => {
  const gr = g.createRadialGradient(w / 2, h / 2, 2, w / 2, h / 2, w / 2);
  gr.addColorStop(0, "rgba(0,0,0,.5)"); gr.addColorStop(.6, "rgba(0,0,0,.3)"); gr.addColorStop(1, "rgba(0,0,0,0)");
  g.setTransform(1, 0, 0, .5, 0, h / 4); g.fillStyle = gr; g.fillRect(0, 0, w, w);
});
const blob = (x, z, s) => decal(shadowTex, x, z, s, s * 0.55, 0, 0.008);

// ---------- 道具（朝镜头的平面）----------
const billboards = [];
function treeTex(variant) {
  return canvasTex(256, 384, (g, w, h) => {
    g.lineJoin = "round"; g.lineWidth = 7; g.strokeStyle = "#1c1a14";
    g.fillStyle = "#5a3f28";
    g.beginPath(); g.moveTo(w * .44, h); g.lineTo(w * .47, h * .45); g.lineTo(w * .55, h * .45); g.lineTo(w * .58, h); g.closePath();
    g.fill(); g.stroke();
    const greens = variant ? ["#2f4a2a", "#3d5c32", "#4f7340"] : ["#3a4a26", "#4d6131", "#62793d"];
    for (let k = 0; k < 3; k++) {
      g.fillStyle = greens[k];
      const cy = h * (.52 - k * .14), rw = w * (.44 - k * .08), rh = h * (.17 - k * .02);
      g.beginPath();
      for (let i = 0; i <= 16; i++) {
        const a = i / 16 * Math.PI * 2, r = 1 + (i % 2 ? .1 : -.05);
        const x = w / 2 + Math.cos(a) * rw * r, y = cy + Math.sin(a) * rh * r;
        i ? g.lineTo(x, y) : g.moveTo(x, y);
      }
      g.closePath(); g.fill(); g.stroke();
    }
  });
}
function rockTex() {
  return canvasTex(192, 128, (g, w, h) => {
    g.lineWidth = 6; g.strokeStyle = "#1c1a14"; g.fillStyle = "#7d7a72";
    g.beginPath(); g.moveTo(w * .1, h * .95); g.lineTo(w * .2, h * .45); g.lineTo(w * .45, h * .2); g.lineTo(w * .75, h * .3);
    g.lineTo(w * .92, h * .95); g.closePath(); g.fill(); g.stroke();
    g.fillStyle = "#99968c"; g.beginPath(); g.moveTo(w * .28, h * .5); g.lineTo(w * .46, h * .3); g.lineTo(w * .6, h * .5); g.closePath(); g.fill();
  });
}
function bushTex() {
  return canvasTex(160, 128, (g, w, h) => {
    g.lineWidth = 5; g.strokeStyle = "#1c1a14";
    for (const [x, y, r, c] of [[.3, .62, .26, "#3f5a2c"], [.66, .6, .28, "#4b6833"], [.48, .42, .28, "#58783a"]]) {
      g.fillStyle = c; g.beginPath(); g.arc(w * x, h * y, w * r, 0, 7); g.fill(); g.stroke();
    }
    g.fillStyle = "#d9566a";
    for (let i = 0; i < 6; i++) { g.beginPath(); g.arc(w * (.3 + rnd() * .45), h * (.3 + rnd() * .35), 4, 0, 7); g.fill(); }
    g.fillRect(0, h - 1, w, 1);
  });
}
const propTex = { tree0: treeTex(0), tree1: treeTex(1), rock: rockTex(), bush: bushTex() };
function prop(kind, x, z, height) {
  const tex = propTex[kind];
  const aspect = tex.image.width / tex.image.height;
  const geo = new THREE.PlaneGeometry(height * aspect, height);
  geo.translate(0, height / 2, 0);  // 脚底在原点
  const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, transparent: true, alphaTest: 0.05 }));
  m.position.set(x, 0, z);
  m.userData.half = height * aspect / 2;
  scene.add(m);
  billboards.push(m);
  blob(x, z, height * aspect * 0.9);
}
for (let i = 0; i < 70; i++) {
  const a = rnd() * Math.PI * 2, r = 5 + rnd() * 26;
  const x = Math.cos(a) * r, z = Math.sin(a) * r;
  if (Math.hypot(x, z + 6) < 4.5) continue;  // 石圈里不放
  const k = rnd();
  if (k < .5) prop(k < .25 ? "tree0" : "tree1", x, z, 3.4 + rnd() * 1.6);
  else if (k < .75) prop("rock", x, z, .7 + rnd() * .5);
  else prop("bush", x, z, .8 + rnd() * .4);
}

// ---------- 角色 ----------
const CHAR_H = 1.75;  // 角色世界高度（米），按清单里的 height 缩放骨骼
const player = { pos: new THREE.Vector3(0, 0, 2), heading: Math.PI, view: "front", flip: false, anim: "idle", speed: 0 };
const holder = new THREE.Group();  // 朝镜头的那层
scene.add(holder);
const playerShadow = blob(0, 0, 1.0);
let rig = null;

async function loadRig() {
  const man = await (await fetch(manifestUrl)).json();
  const base = new URL(".", manifestUrl).href;
  const am = new AssetManager(base);
  for (const v of Object.values(man.views)) { am.loadText(v.json); am.loadTextureAtlas(v.atlas); }
  await am.loadAll();
  const views = {};
  for (const [name, v] of Object.entries(man.views)) {
    const atlas = am.require(v.atlas);
    const data = new SkeletonJson(new AtlasAttachmentLoader(atlas)).readSkeletonData(am.require(v.json));
    const mesh = new SkeletonMesh({ skeletonData: data });
    mesh.zOffset = 0.5;  // 插槽之间的前后间距（骨骼单位），整体缩放后约 0.4mm，只用来定前后顺序
    mesh.state.data.defaultMix = 0.15;
    mesh.scale.setScalar(CHAR_H / (v.height || man.height));  // 各套可以有自己的身高（单位：骨骼单位）
    mesh.visible = false;
    mesh.userData.anims = { ...(man.anims || {}), ...(v.anims || {}) };
    mesh.userData.view = name;
    mesh.userData.H = v.height || man.height;
    mesh.userData.delta = 0;
    const apply = mesh.state.apply.bind(mesh.state);
    mesh.state.apply = (sk) => {
      // 视差改的属性动作里不一定有关键帧，不先复位会逐帧累积
      for (const n of ["root", "head", "neck", "chest"]) {
        const b = sk.findBone(n);
        if (b) { b.x = b.data.x; b.y = b.data.y; b.scaleX = b.data.scaleX; }
      }
      const r = apply(sk);
      if (mode.plus) parallax(mesh, sk);
      return r;
    };
    holder.add(mesh);
    views[name] = mesh;
  }
  rig = { man, views };
  setAnim("idle", true);
  document.getElementById("load").remove();
  syncButtons();
}

// ---------- B+：多方向 + 视差过渡 ----------
// 纯切换（B）在扇区边界（夹角 45°、135°）一下子换图。B+ 在每个扇区内按偏离扇区中心的角度 δ 让骨骼「转一点」：
// 正 / 背面整体横向压窄（转身时身体投影变窄）、头相对身体平移（头在身体前方，转动时位移更大）；侧面横向放宽、头往镜头方向偏。
// 只动骨骼（动画应用之后、算世界变换之前），不需要额外的图。系数是目测定的，不是测量值。
const mode = { plus: params.has("bplus"), steps: 0 };  // steps：抽帧，0 = 关，2 = 一拍二（12 张 / 秒），3 = 一拍三（8 张 / 秒）
// 抽帧（动漫的「一拍二 / 一拍三」）：骨骼姿势和物理按固定节拍步进，位置移动和镜头照常每帧更新
const STEP_LABEL = { 0: "关", 2: "一拍二", 3: "一拍三" };
function cycleSteps() { mode.steps = mode.steps === 0 ? 2 : mode.steps === 2 ? 3 : 0; syncButtons(); }
addEventListener("keydown", (e) => { if (e.code === "KeyF") cycleSteps(); });
addEventListener("keydown", (e) => { if (e.code === "KeyP") mode.plus = !mode.plus; });
function shiftBone(sk, name, dx) {
  const b = sk.findBone(name);
  if (!b) return;
  const p = b.parent;
  const r = p ? -p.getWorldRotationX() * Math.PI / 180 : 0;  // 世界 x 位移 → 父骨骼局部（上一帧的世界旋转，误差可忽略）
  const sx = p ? p.getWorldScaleX() || 1 : 1;
  b.x += (Math.cos(r) * dx) / sx;
  b.y += (Math.sin(r) * dx) / sx;
}
function parallax(mesh, sk) {
  const d = mesh.userData.delta, H = mesh.userData.H, v = mesh.userData.view;
  const sn = Math.sin(d), sq = sn * sn;
  const root = sk.findBone("root");
  if (v === "side") {
    root.scaleX *= 1 + 0.35 * sq;
    shiftBone(sk, "neck", -0.02 * H * sn);
  } else {
    root.scaleX *= 1 - 0.3 * sq;
    const sg = v === "back" ? -1 : 1;
    // 平移 neck 而不是 head：脖子皮肤画在衣身层里、挂在 neck 上，只平移 head 时头和脖子会错开
    // （2026-10-10 用户指出「脖子和头会有分离」）；neck 带着头走，领口按权重过渡到胸部，是拉伸而不是断开
    shiftBone(sk, "neck", sg * 0.035 * H * sn);
    shiftBone(sk, "chest", sg * 0.012 * H * sn);
  }
}

function setAnim(name, force) {
  if (!force && player.anim === name) return;
  player.anim = name;
  for (const m of Object.values(rig.views)) m.state.setAnimation(0, m.userData.anims[name] || name, true);
}

// ---------- 镜头 ----------
const cam = { yaw: 0, yawTarget: 0, pitch: THREE.MathUtils.degToRad(38), dist: 7 };
const keys = new Set();
addEventListener("keydown", (e) => {
  keys.add(e.code);
  if (e.code === "KeyQ") cam.yawTarget = snap45(cam.yawTarget) - Math.PI / 4;
  if (e.code === "KeyE") cam.yawTarget = snap45(cam.yawTarget) + Math.PI / 4;
});
addEventListener("keyup", (e) => keys.delete(e.code));
addEventListener("blur", () => keys.clear());
const snap45 = (a) => Math.round(a / (Math.PI / 4)) * (Math.PI / 4);
let drag = null;
renderer.domElement.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY }; renderer.domElement.setPointerCapture(e.pointerId); });
renderer.domElement.addEventListener("pointermove", (e) => {
  if (!drag) return;
  cam.yawTarget -= (e.clientX - drag.x) * 0.006;
  cam.yaw = cam.yawTarget;  // 拖动时直接跟手
  cam.pitch = THREE.MathUtils.clamp(cam.pitch + (e.clientY - drag.y) * 0.004, 0.25, 1.15);
  drag = { x: e.clientX, y: e.clientY };
});
renderer.domElement.addEventListener("pointerup", () => (drag = null));
renderer.domElement.addEventListener("wheel", (e) => { cam.dist = THREE.MathUtils.clamp(cam.dist * Math.exp(e.deltaY * 0.001), 4, 22); }, { passive: true });

// ---------- 触屏：摇杆 + 按钮（页面里有这些元素才接） ----------
const pad = { x: 0, z: 0, run: false };
const stick = document.getElementById("stick"), knob = document.getElementById("knob");
if (stick && knob) {
  let id = null;
  const move = (e) => {
    const r = stick.getBoundingClientRect(), R = r.width / 2;
    let dx = e.clientX - (r.left + R), dy = e.clientY - (r.top + R);
    const l = Math.hypot(dx, dy);
    if (l > R) { dx *= R / l; dy *= R / l; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    const dead = 0.18;
    pad.x = Math.abs(dx / R) > dead ? dx / R : 0;
    pad.z = Math.abs(dy / R) > dead ? dy / R : 0;
  };
  const end = () => { id = null; pad.x = pad.z = 0; knob.style.transform = ""; };
  stick.addEventListener("pointerdown", (e) => { id = e.pointerId; stick.setPointerCapture(id); move(e); e.preventDefault(); });
  stick.addEventListener("pointermove", (e) => { if (e.pointerId === id) move(e); });
  stick.addEventListener("pointerup", end);
  stick.addEventListener("pointercancel", end);
}
const btn = (id, fn) => document.getElementById(id)?.addEventListener("click", fn);
btn("btn-left", () => (cam.yawTarget = snap45(cam.yawTarget) - Math.PI / 4));
btn("btn-right", () => (cam.yawTarget = snap45(cam.yawTarget) + Math.PI / 4));
btn("btn-mode", () => { mode.plus = !mode.plus; syncButtons(); });
btn("btn-run", () => { pad.run = !pad.run; syncButtons(); });
btn("btn-steps", () => cycleSteps());
addEventListener("keydown", (e) => { if (e.code === "KeyP") setTimeout(syncButtons); });
function syncButtons() {
  const m = document.getElementById("btn-mode"), r = document.getElementById("btn-run");
  if (m) { m.setAttribute("aria-pressed", String(mode.plus)); m.textContent = mode.plus ? "B+ 视差过渡" : "B 纯切换"; }
  if (r) r.setAttribute("aria-pressed", String(pad.run));
  const st = document.getElementById("btn-steps");
  if (st) { st.setAttribute("aria-pressed", String(mode.steps > 0)); st.textContent = `抽帧 ${STEP_LABEL[mode.steps]}`; }
}

// 镜头的水平基向量：toCam = 从角色指向镜头，right = 画面右
const toCam = new THREE.Vector3(), right = new THREE.Vector3();
function updateCamera() {
  toCam.set(Math.sin(cam.yaw), 0, Math.cos(cam.yaw));
  right.set(Math.cos(cam.yaw), 0, -Math.sin(cam.yaw));
  const t = player.pos;
  camera.position.set(t.x + toCam.x * cam.dist * Math.cos(cam.pitch), cam.dist * Math.sin(cam.pitch) + 0.9,
    t.z + toCam.z * cam.dist * Math.cos(cam.pitch));
  camera.lookAt(t.x, 0.9, t.z);
}

// ---------- 选方向 ----------
// 角色朝向 f 与 toCam 的夹角 θ：θ < 45° 正面，θ > 135° 背面，其余侧面；边界留 6° 回差，镜头转到边界附近时不来回闪
const HYST = THREE.MathUtils.degToRad(6);
function pickView() {
  const fx = Math.sin(player.heading), fz = Math.cos(player.heading);
  const c = fx * toCam.x + fz * toCam.z;               // cos θ
  const s = fx * right.x + fz * right.z;               // >0：朝画面右
  const th = Math.acos(THREE.MathUtils.clamp(c, -1, 1));
  const q = Math.PI / 4, cur = player.view;
  let v;
  if (cur === "front") v = th < q + HYST ? "front" : th > 3 * q ? "back" : "side";
  else if (cur === "back") v = th > 3 * q - HYST ? "back" : th < q ? "front" : "side";
  else v = th < q - HYST ? "front" : th > 3 * q + HYST ? "back" : "side";
  if (v === "side" && !rig.views.side) v = th < Math.PI / 2 ? "front" : "back";
  let flip = player.flip;
  if (Math.abs(s) > 0.08) flip = rig.man.side_faces === "left" ? s > 0 : s < 0;
  return { v, flip, th, phi: Math.atan2(s, c) };  // phi：0 = 朝镜头，+90° = 朝画面右
}
const wrapPi = (a) => Math.atan2(Math.sin(a), Math.cos(a));

// ---------- 主循环 ----------
const clock = new THREE.Clock();
const tmp = new THREE.Vector3();
let lastPos = null, lastView = { yaw: 0, key: "", delta: 0 }, stepAcc = 0;
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05);
  // 镜头角度缓动（Q / E）
  cam.yaw += (cam.yawTarget - cam.yaw) * (1 - Math.exp(-dt * 10));
  updateCamera();
  if (rig) {
    // 移动：输入在镜头坐标里
    const ix = (keys.has("KeyD") ? 1 : 0) - (keys.has("KeyA") ? 1 : 0) + pad.x;
    const iz = (keys.has("KeyS") ? 1 : 0) - (keys.has("KeyW") ? 1 : 0) + pad.z;
    const run = keys.has("ShiftLeft") || keys.has("ShiftRight") || pad.run;
    if (ix || iz) {
      tmp.copy(right).multiplyScalar(ix).addScaledVector(toCam, iz).normalize();
      player.heading = Math.atan2(tmp.x, tmp.z);
      // 清单里有动捕速度（身高 / 秒）就按它走，步子和地面对得上；没有就用固定值
      const sv = rig.man.speeds?.[run ? "run" : "walk"];
      const sp = sv ? sv * CHAR_H : run ? 4.2 : 2.0;
      player.pos.addScaledVector(tmp, sp * dt);
      setAnim(run ? "run" : "walk");
    } else setAnim("idle");
    const { v, flip, th, phi } = pickView();
    if (v !== player.view) {
      // 换套：把动作时间带过去，步伐接上
      const from = rig.views[player.view].state.getCurrent(0);
      const to = rig.views[v].state.getCurrent(0);
      if (from && to) to.trackTime = from.trackTime;
      player.view = v;
    }
    player.flip = flip;
    // 偏离扇区中心的角度（侧面按原图朝右的坐标算：镜像时取反）
    rig.views.front && (rig.views.front.userData.delta = wrapPi(phi));
    rig.views.back && (rig.views.back.userData.delta = wrapPi(phi - Math.PI));
    if (rig.views.side) rig.views.side.userData.delta = flip ? -wrapPi(phi + Math.PI / 2) : wrapPi(phi - Math.PI / 2);
    for (const [name, m] of Object.entries(rig.views)) {
      m.visible = name === player.view;
      m.skeleton.scaleX = name === "side" && player.flip ? -1 : 1;
    }
    // 物理：只按角色这一帧的实际位移（投到画面横向）给冲量，头发、裙摆被甩向后方。
    // 以前按「位置在画面上的横坐标」的差算，镜头一转、人没动这个值也会变，转视角时头发乱甩（2026-10-10 用户指出）
    const m = rig.views[player.view];
    if (lastPos) {
      const dx = (player.pos.x - lastPos.x) * right.x + (player.pos.z - lastPos.z) * right.z;
      // 只传 0.2 倍：整段位移全给物理时跑步（每帧约 76 骨骼单位）会把短发甩成马尾那么长
      m.skeleton.physicsTranslate((dx / m.scale.x) * 0.2, 0);
    }
    lastPos = player.pos.clone();
    // 转镜头、切视角 / 镜像、B+ 的视差参数变化都会让骨骼位置突变，物理会把它当成运动甩起来：
    // 这些帧把物理状态重置成当前姿势（不甩），镜头停下后照常模拟
    const viewKey = `${player.view}|${player.flip}|${mode.plus}`;
    const camMoved = Math.abs(cam.yaw - lastView.yaw) > 1e-4 || viewKey !== lastView.key ||
      (mode.plus && Math.abs(m.userData.delta - lastView.delta) > 1e-3);
    if (camMoved) for (const c of m.skeleton.physicsConstraints) c.reset();
    lastView = { yaw: cam.yaw, key: viewKey, delta: m.userData.delta };
    if (mode.steps) {
      // 24fps 的「一拍 N」= 每 N/24 秒换一次姿势；累计时间到了才把整段时间一次推进给骨骼
      const step = mode.steps / 24;
      stepAcc += dt;
      if (stepAcc >= step) {
        for (const mm of Object.values(rig.views)) mm.update(stepAcc);
        stepAcc = 0;
      } else {
        for (const mm of Object.values(rig.views)) mm.update(0);  // 只重算世界变换，姿势不动
      }
    } else {
      stepAcc = 0;
      for (const mm of Object.values(rig.views)) mm.update(dt);
    }
    holder.position.copy(player.pos);
    playerShadow.position.set(player.pos.x, 0.008, player.pos.z);
    document.getElementById("state").innerHTML =
      `镜头 <b>${(((THREE.MathUtils.radToDeg(cam.yaw) % 360) + 360) % 360).toFixed(0)}°</b>　` +
      `角色朝向与镜头夹角 <b>${THREE.MathUtils.radToDeg(th).toFixed(0)}°</b>　显示 <b>${{ front: "正面", side: "侧面", back: "背面" }[player.view]}${player.view === "side" ? (player.flip ? "（镜像）" : "") : ""}</b>　${player.anim}　` +
      `模式 <b>${mode.plus ? "B+" : "B"}</b>　抽帧 <b>${STEP_LABEL[mode.steps]}</b>`;
  }
  // 朝镜头：角色和道具都绕脚底转到与镜头同向（饥荒的做法），上半身向后仰，脚不离地
  holder.quaternion.copy(camera.quaternion);
  // 挡在镜头和角色之间的道具变半透明（饥荒同款）：道具比角色离镜头近，且到「镜头 → 角色」水平连线的距离小于半宽
  const cx = camera.position.x, cz = camera.position.z;
  const lx = player.pos.x - cx, lz = player.pos.z - cz, ll = Math.hypot(lx, lz);
  for (const b of billboards) {
    b.quaternion.copy(camera.quaternion);
    const bx = b.position.x - cx, bz = b.position.z - cz;
    const along = (bx * lx + bz * lz) / ll, perp = Math.abs(bx * lz - bz * lx) / ll;
    const near = Math.hypot(bx, bz) < 2.5;  // 贴着镜头的整个隐藏，否则半透明的大树会罩住整个画面
    const target = near ? 0 : along > 0 && along < ll - 0.3 && perp < b.userData.half + 0.35 ? 0.12 : 1;
    b.material.opacity += (target - b.material.opacity) * (1 - Math.exp(-dt * 8));
    b.visible = b.material.opacity > 0.02;
  }
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

// 截图 / 自动测试用：?shot 时暴露控制接口
window.demo = {
  player, cam, mode, get rig() { return rig; }, cycleSteps,
  setInput(codes) { keys.clear(); for (const c of codes) keys.add(c); },
  ready: () => !!rig,
};
loadRig().catch((e) => { document.getElementById("load").textContent = "加载失败：" + e.message; console.error(e); });
frame();
