// Load a rig with the official spine-core 4.2 runtime (headless) and report what it sees:
// animations, per-pose bounds and slots with no attachment. Catches JSON/atlas mismatches
// that a browser preview would only show as a blank canvas.
// Usage (from projects/game-aesthetic-asset, after `npm install`):
//   node scripts/spine-verify.mjs <rig_dir> [name=kurumi]
import * as spine from "@esotericsoftware/spine-core";
import fs from "fs";
import path from "path";

const dir = process.argv[2];
const name = process.argv[3] || "kurumi";
if (!dir) { console.error("usage: node scripts/spine-verify.mjs <rig_dir> [name]"); process.exit(2); }

class NullTexture extends spine.Texture { setFilters() {} setWraps() {} dispose() {} }
const atlas = new spine.TextureAtlas(fs.readFileSync(path.join(dir, name + ".atlas"), "utf8"));
for (const p of atlas.pages) p.setTexture(new NullTexture({ width: p.width, height: p.height }));
const data = new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas))
  .readSkeletonData(fs.readFileSync(path.join(dir, name + ".json"), "utf8"));
const sk = new spine.Skeleton(data);
const state = new spine.AnimationState(new spine.AnimationStateData(data));

console.log(`bones ${data.bones.length}, slots ${data.slots.length}, regions ${atlas.regions.length}`);
let bad = 0;
for (const anim of [null, ...data.animations.map(a => a.name)]) {
  sk.setToSetupPose();
  if (anim) { state.setAnimation(0, anim, true); state.update(0.15); state.apply(sk); }
  sk.updateWorldTransform(spine.Physics.update);
  const off = new spine.Vector2(), size = new spine.Vector2();
  sk.getBounds(off, size, []);
  const empty = sk.drawOrder.filter(s => !s.attachment).map(s => s.data.name);
  if (empty.length) bad++;
  const dur = anim ? data.findAnimation(anim).duration.toFixed(2) + "s" : "";
  console.log(`${(anim || "setup").padEnd(8)} ${dur.padEnd(6)} bounds x=${off.x.toFixed(0)} y=${off.y.toFixed(0)} w=${size.x.toFixed(0)} h=${size.y.toFixed(0)}` +
    (empty.length ? `  MISSING: ${empty.join(",")}` : ""));
}
process.exit(bad ? 1 : 0);
