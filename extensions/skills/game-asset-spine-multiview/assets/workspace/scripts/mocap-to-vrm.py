"""Retarget a mocap clip (FBX/BVH: CMU, Mixamo) onto a VRM humanoid in Blender, bake it, render previews.

Usage (Blender 5.2 + VRM Add-on, headless):
    blender -b --python scripts/mocap-to-vrm.py -- \
        <model.vrm> <clip.fbx|.bvh> <out dir> [--map cmu|mixamo|smplx] [--start N] [--end N] [--size 512] [--no-render]

Writes <out>/<clip>.blend (VRM + baked action, source armature hidden), <out>/<clip>_report.json, and,
unless --no-render, PNG frames for two orthographic cameras following the hips: side/ (camera on the
character's left, so a character walking forward moves to screen right) and q34/ (front-left 3/4).
Stitch with ffmpeg (hstack) afterwards.

Method: world-space rotation transfer. Both skeletons are assumed to share a rest pose shape (T-pose for
CMU, Mixamo and VRoid VRM) and a Z-up world. A yaw-only facing correction C (from each rest pose's
left-right shoulder axis) maps source world axes to target ones; a mapped target bone gets world rotation
C * Rsrc(f) * Rsrc_rest^-1 * C^-1 * Rtgt_rest. Unmapped target bones keep their rest pose relative to
their parent. Hips translation = source hips displacement (rotated by C) scaled by the hips-height ratio.
Pose is solved with an explicit forward-kinematics chain in armature space (no depsgraph updates).
Fingers are mapped only for smplx (GVHMR BVH from scripts/gvhmr-to-bvh.py; CMU has no finger data). Report: per-frame lowest foot/toe height of the target
vs the scaled source, to check ground contact after retargeting.
"""
import argparse
import json
import math
import os
import statistics
import sys

import bpy
from mathutils import Matrix, Vector

# source bone -> VRM humanoid bone
MAPS = {
    "cmu": {
        "hip": "hips", "abdomen": "spine", "chest": "chest", "neck": "neck", "head": "head",
        "lCollar": "left_shoulder", "lShldr": "left_upper_arm", "lForeArm": "left_lower_arm", "lHand": "left_hand",
        "rCollar": "right_shoulder", "rShldr": "right_upper_arm", "rForeArm": "right_lower_arm", "rHand": "right_hand",
        "lThigh": "left_upper_leg", "lShin": "left_lower_leg", "lFoot": "left_foot",
        "rThigh": "right_upper_leg", "rShin": "right_lower_leg", "rFoot": "right_foot",
    },
    "mixamo": {
        "mixamorig:Hips": "hips", "mixamorig:Spine": "spine", "mixamorig:Spine1": "chest",
        "mixamorig:Spine2": "upper_chest", "mixamorig:Neck": "neck", "mixamorig:Head": "head",
        "mixamorig:LeftShoulder": "left_shoulder", "mixamorig:LeftArm": "left_upper_arm",
        "mixamorig:LeftForeArm": "left_lower_arm", "mixamorig:LeftHand": "left_hand",
        "mixamorig:RightShoulder": "right_shoulder", "mixamorig:RightArm": "right_upper_arm",
        "mixamorig:RightForeArm": "right_lower_arm", "mixamorig:RightHand": "right_hand",
        "mixamorig:LeftUpLeg": "left_upper_leg", "mixamorig:LeftLeg": "left_lower_leg",
        "mixamorig:LeftFoot": "left_foot", "mixamorig:LeftToeBase": "left_toes",
        "mixamorig:RightUpLeg": "right_upper_leg", "mixamorig:RightLeg": "right_lower_leg",
        "mixamorig:RightFoot": "right_foot", "mixamorig:RightToeBase": "right_toes",
    },
}
# SMPL-X joints as written by scripts/gvhmr-to-bvh.py (GVHMR), fingers included
MAPS["smplx"] = {
    "pelvis": "hips", "spine1": "spine", "spine2": "chest", "spine3": "upper_chest", "neck": "neck", "head": "head",
}
for _s in ("left", "right"):
    MAPS["smplx"].update({
        f"{_s}_collar": f"{_s}_shoulder", f"{_s}_shoulder": f"{_s}_upper_arm", f"{_s}_elbow": f"{_s}_lower_arm",
        f"{_s}_wrist": f"{_s}_hand", f"{_s}_hip": f"{_s}_upper_leg", f"{_s}_knee": f"{_s}_lower_leg",
        f"{_s}_ankle": f"{_s}_foot", f"{_s}_foot": f"{_s}_toes",
        f"{_s}_thumb1": f"{_s}_thumb_metacarpal", f"{_s}_thumb2": f"{_s}_thumb_proximal",
        f"{_s}_thumb3": f"{_s}_thumb_distal",
    })
    for _f, _v in (("index", "index"), ("middle", "middle"), ("ring", "ring"), ("pinky", "little")):
        MAPS["smplx"].update({f"{_s}_{_f}1": f"{_s}_{_v}_proximal", f"{_s}_{_f}2": f"{_s}_{_v}_intermediate",
                              f"{_s}_{_f}3": f"{_s}_{_v}_distal"})
FEET =("left_foot", "right_foot", "left_toes", "right_toes")


def args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("vrm"); p.add_argument("clip"); p.add_argument("out")
    p.add_argument("--map", default="cmu", choices=MAPS)
    p.add_argument("--start", type=int); p.add_argument("--end", type=int)
    p.add_argument("--size", type=int, default=512)
    p.add_argument("--no-render", action="store_true")
    return p.parse_args(argv)


def import_vrm(path):
    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.vrm")
    bpy.ops.import_scene.vrm(filepath=path)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    ext = arm.data.vrm_addon_extension
    hb = ext.vrm1.humanoid.human_bones
    names = {}
    for key in dir(hb):
        node = getattr(hb, key, None)
        bn = getattr(getattr(node, "node", None), "bone_name", "")
        if bn and bn in arm.data.bones:
            names[key] = bn
    return arm, names


def import_clip(path):
    before = set(bpy.data.objects)
    if path.lower().endswith(".bvh"):
        bpy.ops.import_anim.bvh(filepath=path, update_scene_fps=True, update_scene_duration=True)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    return next(o for o in new if o.type == "ARMATURE")


def rest_yaw(arm, left, right):
    """Heading (radians about world Z) of a rest skeleton's left-right axis. Yaw only: a pitch here
    (e.g. from a forward-leaning rest spine) would tilt the root trajectory into or out of the floor."""
    mw = arm.matrix_world
    side = mw @ arm.data.bones[left].head_local - mw @ arm.data.bones[right].head_local
    return math.atan2(side.y, side.x)


def main():
    a = args()
    a.out = os.path.abspath(a.out)  # render paths are resolved against the saved .blend otherwise
    os.makedirs(a.out, exist_ok=True)
    clip = os.path.splitext(os.path.basename(a.clip))[0]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    tgt, hum = import_vrm(a.vrm)
    src = import_clip(a.clip)
    sc = bpy.context.scene
    fr = src.animation_data.action.frame_range
    f0 = a.start or int(fr[0]); f1 = a.end or int(fr[1])

    mapping = {s: hum[t] for s, t in MAPS[a.map].items() if s in src.data.bones and t in hum}
    if a.map == "mixamo" and "upper_chest" not in hum and "mixamorig:Spine2" in src.data.bones:
        mapping.pop("mixamorig:Spine1", None); mapping["mixamorig:Spine2"] = hum["chest"]  # chest follows the top
    if a.map == "smplx" and "upper_chest" not in hum and "spine3" in src.data.bones:
        mapping.pop("spine2", None); mapping["spine3"] = hum["chest"]
    inv = {t: s for s, t in mapping.items()}
    skeys = {v: k for k, v in MAPS[a.map].items()}
    # facing correction: source world axes -> target world axes
    yaw = rest_yaw(tgt, hum["left_upper_arm"], hum["right_upper_arm"]) \
        - rest_yaw(src, skeys["left_upper_arm"], skeys["right_upper_arm"])
    C = Matrix.Rotation(yaw, 4, "Z")
    Ci = C.inverted()

    sw, tw = src.matrix_world, tgt.matrix_world
    twi = tw.inverted()
    s_hip = skeys["hips"]
    s_rest_rot = {s: (sw @ src.data.bones[s].matrix_local).to_quaternion() for s in mapping}
    s_hip_rest = sw @ src.data.bones[s_hip].head_local
    t_bones = tgt.data.bones
    t_hip = hum["hips"]
    t_hip_rest = tw @ t_bones[t_hip].head_local
    ground_t = min((tw @ b.head_local).z for b in t_bones)
    scale = (t_hip_rest.z - ground_t) / s_hip_rest.z   # source ground assumed at z = 0
    order = []
    def walk(b):
        order.append(b)
        for c in b.children:
            walk(c)
    for b in t_bones:
        if b.parent is None:
            walk(b)

    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"  # one key per frame
    for pb in tgt.pose.bones:
        pb.rotation_mode = "QUATERNION"
    tgt.animation_data_create()
    tgt.animation_data.action = bpy.data.actions.new(f"{clip}_vrm")
    prev_q = {}
    lowest_t, lowest_s = [], []
    feet_t = [hum[k] for k in FEET if k in hum]
    feet_s = [s for s, t in mapping.items() if t in feet_t] or [skeys["left_foot"], skeys["right_foot"]]

    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        posed = {}
        for b in order:
            rest = b.matrix_local
            rel = (b.parent.matrix_local.inverted() @ rest) if b.parent else rest
            parent_pose = posed[b.parent.name] if b.parent else Matrix.Identity(4)
            unposed = parent_pose @ rel
            s = inv.get(b.name)
            if s is None:
                posed[b.name] = unposed
                continue
            rs = (sw @ src.pose.bones[s].matrix).to_quaternion()
            d = (C @ (rs @ s_rest_rot[s].inverted()).to_matrix().to_4x4() @ Ci)
            want_rot = twi.to_3x3() @ d.to_3x3() @ (tw @ rest).to_3x3()
            if b.name == t_hip:
                disp = (C.to_3x3() @ ((sw @ src.pose.bones[s].head) - s_hip_rest)) * scale
                head = twi @ (t_hip_rest + disp)
            else:
                head = unposed.to_translation()
            want = Matrix.Translation(head) @ want_rot.to_4x4()
            basis = unposed.inverted() @ want
            q = basis.to_quaternion()
            if b.name in prev_q and q.dot(prev_q[b.name]) < 0:
                q.negate()
            prev_q[b.name] = q
            pb = tgt.pose.bones[b.name]
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if b.name == t_hip:
                pb.location = basis.to_translation()
                pb.keyframe_insert("location", frame=f)
            posed[b.name] = unposed @ basis
        lowest_t.append(min((tw @ posed[n].to_translation()).z for n in feet_t) - ground_t)
        lowest_s.append(min((sw @ src.pose.bones[n].head).z for n in feet_s) * scale)

    src.hide_viewport = src.hide_render = True
    sc.frame_start, sc.frame_end = f0, f1
    rep = {
        "clip": clip, "frames": [f0, f1], "fps": sc.render.fps, "scale": scale,
        "mapped": mapping, "unmapped_vrm": sorted(set(hum) - set(MAPS[a.map].values())),
        "facing_correction_deg": math.degrees(C.to_quaternion().angle),
        "lowest_foot_target_m": {"min": min(lowest_t), "median": statistics.median(lowest_t), "max": max(lowest_t)},
        "lowest_foot_source_scaled_m": {"min": min(lowest_s), "median": statistics.median(lowest_s), "max": max(lowest_s)},
    }
    with open(os.path.join(a.out, f"{clip}_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, ensure_ascii=False)
    print("REPORT", json.dumps(rep, ensure_ascii=False))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, f"{clip}.blend"))
    if not a.no_render:
        render(tgt, t_hip, a, clip, f0, f1)


def render(tgt, hip, a, clip, f0, f1):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = a.size
    sc.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("bg"); sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.35, 0.38, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3; sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
    sc.collection.objects.link(sun)
    # floor grid as a plane for ground reference
    bpy.ops.mesh.primitive_plane_add(size=40)
    floor = bpy.context.object
    mat = bpy.data.materials.new("floor"); mat.diffuse_color = (0.25, 0.25, 0.27, 1); floor.data.materials.append(mat)
    pivot = bpy.data.objects.new("pivot", None); sc.collection.objects.link(pivot)
    pb = tgt.pose.bones[hip]
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        p = tgt.matrix_world @ pb.head
        pivot.location = (p.x, p.y, 0.85)
        pivot.keyframe_insert("location", frame=f)
    views = {"side": ((-6, 0, 0), (math.radians(90), 0, math.radians(-90))),
             "q34": ((-4.24, -4.24, 1.6), (math.radians(75), 0, math.radians(-45)))}
    for name, (loc, rot) in views.items():
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        cam.data.type = "ORTHO"; cam.data.ortho_scale = 2.4
        cam.parent = pivot; cam.location = loc; cam.rotation_euler = rot
        sc.collection.objects.link(cam)
        sc.camera = cam
        sc.render.filepath = os.path.join(a.out, f"{clip}_{name}", "f_")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":  # imported by vrm-dress.py for render()
    main()
