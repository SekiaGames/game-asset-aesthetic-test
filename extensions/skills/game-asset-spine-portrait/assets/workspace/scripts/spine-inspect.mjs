// 用法：node scripts/spine-inspect.mjs <skel或json> <atlas> [out.json]
// 用官方 spine-core 4.2 加载骨骼，统计骨骼 / 插槽 / 附件类型 / 约束 / 动作（按前缀分组、每个动作驱动哪些骨骼与轨道类型），
// 用来拆解参考模型（如 ryza-ai-revive 的正面立绘）的结构。
import fs from "node:fs";
import * as spine from "@esotericsoftware/spine-core";

const [skelPath, atlasPath, outPath] = process.argv.slice(2);
const atlas = new spine.TextureAtlas(fs.readFileSync(atlasPath, "utf8"));
for (const p of atlas.pages) p.setTexture(new (class extends spine.Texture { setFilters() {} setWraps() {} dispose() {} })({ width: p.width, height: p.height }));
const loader = new spine.AtlasAttachmentLoader(atlas);
const data = skelPath.endsWith(".json")
  ? new spine.SkeletonJson(loader).readSkeletonData(fs.readFileSync(skelPath, "utf8"))
  : new spine.SkeletonBinary(loader).readSkeletonData(new Uint8Array(fs.readFileSync(skelPath)));

const attTypes = {}, meshStats = { meshes: 0, weighted: 0, verts: 0, maxVerts: 0, maxBonesPerMesh: 0 };
const attList = [];
for (const skin of data.skins) for (const e of skin.getAttachments()) {
  const a = e.attachment, t = a.constructor.name;
  attTypes[t] = (attTypes[t] || 0) + 1;
  const rec = { skin: skin.name, slot: data.slots[e.slotIndex].name, name: e.name, type: t };
  if (a instanceof spine.MeshAttachment) {
    const n = a.worldVerticesLength / 2;
    meshStats.meshes++; meshStats.verts += n; meshStats.maxVerts = Math.max(meshStats.maxVerts, n);
    rec.verts = n;
    if (a.bones) {
      meshStats.weighted++;
      const s = new Set(); for (let i = 0; i < a.bones.length;) { const c = a.bones[i++]; for (let j = 0; j < c; j++) s.add(a.bones[i++]); }
      rec.bones = [...s].map((b) => data.bones[b].name);
      meshStats.maxBonesPerMesh = Math.max(meshStats.maxBonesPerMesh, s.size);
    }
    if (a.parentMesh) rec.linkedTo = a.parentMesh.name;
  }
  attList.push(rec);
}

const anims = data.animations.map((a) => {
  const kinds = {}, bones = new Set(), slots = new Set();
  for (const t of a.timelines) {
    const k = t.constructor.name; kinds[k] = (kinds[k] || 0) + 1;
    if (t.boneIndex !== undefined) bones.add(data.bones[t.boneIndex].name);
    if (t.slotIndex !== undefined) slots.add(data.slots[t.slotIndex].name);
  }
  return { name: a.name, duration: +a.duration.toFixed(3), timelines: a.timelines.length, kinds, bones: [...bones], slots: [...slots] };
});
const groups = {};
for (const a of anims) { const g = a.name.split("_").slice(0, 2).join("_"); (groups[g] ||= []).push(a.name); }

const out = {
  version: data.version, hash: data.hash, size: [data.width, data.height], x: data.x, y: data.y,
  counts: { bones: data.bones.length, slots: data.slots.length, skins: data.skins.length, animations: data.animations.length,
            ik: data.ikConstraints.length, transform: data.transformConstraints.length, path: data.pathConstraints.length,
            physics: (data.physicsConstraints || []).length, events: data.events.length },
  attTypes, meshStats,
  rootBones: data.bones.filter((b) => !b.parent).map((b) => b.name),
  bones: data.bones.map((b) => ({ name: b.name, parent: b.parent?.name, len: +b.length.toFixed(1), x: +b.x.toFixed(1), y: +b.y.toFixed(1), rot: +b.rotation.toFixed(1), inherit: b.inherit })),
  slots: data.slots.map((s) => ({ name: s.name, bone: s.boneData.name, blend: s.blendMode, att: s.attachmentName })),
  ik: data.ikConstraints.map((c) => ({ name: c.name, bones: c.bones.map((b) => b.name), target: c.target.name, mix: c.mix, bend: c.bendDirection })),
  transform: data.transformConstraints.map((c) => ({ name: c.name, bones: c.bones.map((b) => b.name), target: c.target.name,
            mix: [c.mixRotate, c.mixX, c.mixY, c.mixScaleX, c.mixScaleY, c.mixShearY], local: c.local, relative: c.relative })),
  path: data.pathConstraints.map((c) => ({ name: c.name, bones: c.bones.map((b) => b.name), target: c.target.name })),
  physics: (data.physicsConstraints || []).map((c) => ({ name: c.name, bone: c.bone.name, inertia: c.inertia, strength: c.strength, damping: c.damping, mass: 1 / c.massInverse, wind: c.wind, gravity: c.gravity,
            x: c.x, y: c.y, rotate: c.rotate, scaleX: c.scaleX, shearX: c.shearX })),
  skins: data.skins.map((s) => s.name),
  groups: Object.fromEntries(Object.entries(groups).map(([k, v]) => [k, v.length])),
  animations: anims, attachments: attList,
};
if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
console.log(JSON.stringify({ version: out.version, size: out.size, counts: out.counts, attTypes, meshStats, rootBones: out.rootBones, groups: out.groups }, null, 1));
