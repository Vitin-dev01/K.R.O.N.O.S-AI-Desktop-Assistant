import ast
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
import tkinter as tk
from tkinter import filedialog

import psutil
import pygetwindow as gw
from google import genai
from google.genai import types
from config import MODEL_ROUTER, key_rotator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_SCRIPT_CORRECTIONS = 2
BLENDER_TIMEOUT_SECONDS = 300
BLENDER_SAVE_FORMATS = {
    ".blend": "Blender Project (*.blend)",
    ".glb": "glTF Binary (*.glb)",
    ".fbx": "FBX (*.fbx)",
    ".obj": "Wavefront OBJ (*.obj)",
}
_SAFE_IMPORTS = {"bpy", "bmesh", "math", "mathutils", "random"}
_SAFE_OBJECT_OPERATORS = {
    "join",
    "mode_set",
    "origin_set",
    "select_all",
    "shade_flat",
    "shade_smooth",
    "transform_apply",
    "modifier_apply",
    "modifier_add",
    "modifier_remove",
    "modifier_copy",
    "modifier_set_active",
    "duplicate",
    "duplicate_move",
    "delete",
    "parent_set",
    "parent_clear",
    "convert",
}
_SAFE_MESH_OPERATORS = {
    "primitive_circle_add",
    "primitive_cone_add",
    "primitive_cube_add",
    "primitive_cylinder_add",
    "primitive_ico_sphere_add",
    "primitive_plane_add",
    "primitive_torus_add",
    "primitive_uv_sphere_add",
    "primitive_grid_add",
    "primitive_monkey_add",
    "extrude_region_move",
    "extrude_faces_move",
    "extrude_edges_move",
    "extrude_vertices_move",
    "inset",
    "bevel",
    "subdivide",
    "loopcut",
    "bisect",
    "knife_project",
    "separate",
    "split",
    "delete",
    "dissolve_verts",
    "dissolve_edges",
    "dissolve_faces",
    "remove_doubles",
    "fill",
    "edge_face_add",
    "normals_make_consistent",
    "select_all",
    "select_random",
    "select_linked",
    "select_more",
    "select_less",
    "shade_flat",
    "shade_smooth",
}
_BLOCKED_BUILTINS = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}


def _find_blender_executable() -> str | None:
    executable = shutil.which("blender") or shutil.which("blender.exe")
    if executable:
        return executable

    roots = [
        r"C:\Program Files\Blender Foundation",
        r"C:\Program Files (x86)\Blender Foundation",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation"),
    ]
    for base in roots:
        if not os.path.isdir(base):
            continue
        for root, _directories, files in os.walk(base):
            if "blender.exe" in files:
                return os.path.join(root, "blender.exe")
    return None


def _stop_process_tree(
    process: subprocess.Popen,
    grace_seconds: float = 5.0,
) -> bool:
    """Stop Blender and any child processes; return whether force-kill was needed."""
    if process.poll() is not None:
        return False

    targets = []
    try:
        root = psutil.Process(process.pid)
        targets = root.children(recursive=True)[::-1] + [root]
    except psutil.NoSuchProcess:
        targets = []
    except psutil.AccessDenied as error:
        print(
            f"[BLENDER][PROCESSO][AVISO] A árvore de processos não pôde ser "
            f"inspecionada: {error}",
            flush=True,
        )

    if targets:
        for target in targets:
            try:
                target.terminate()
            except psutil.NoSuchProcess:
                continue
        _gone, alive = psutil.wait_procs(targets, timeout=grace_seconds)
        for target in alive:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                continue
        if alive:
            psutil.wait_procs(alive, timeout=grace_seconds)

    forced = False
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            process.wait(timeout=grace_seconds)
    return forced


def _read_blender_status(status_path: str) -> dict[str, object] | None:
    if not os.path.isfile(status_path):
        return None
    with open(status_path, "r", encoding="utf-8") as status_file:
        status = json.load(status_file)
    if not isinstance(status, dict):
        raise ValueError("O estado do Blender não é um objeto JSON.")
    if status.get("status") not in {"running", "done", "error"}:
        raise ValueError(
            "Estado terminal desconhecido do Blender: "
            + repr(status.get("status"))
        )
    return status


def _read_text_tail(path: str, limit: int = 8_000) -> str:
    with open(path, "rb") as log_file:
        log_file.seek(0, os.SEEK_END)
        size = log_file.tell()
        log_file.seek(max(0, size - limit), os.SEEK_SET)
        return log_file.read(limit).decode("utf-8", errors="replace")


def _monitor_blender_process(
    process: subprocess.Popen,
    status_path: str,
    progress_path: str,
    timeout_seconds: float,
) -> tuple[dict[str, object] | None, str, bool]:
    """Return terminal status, diagnostic, and whether cleanup needed force-kill."""
    deadline = time.monotonic() + timeout_seconds
    last_progress_sequence = 0
    while time.monotonic() < deadline:
        if os.path.isfile(progress_path):
            try:
                with open(progress_path, "r", encoding="utf-8") as progress_file:
                    progress = json.load(progress_file)
                sequence = progress.get("sequence", 0)
                if sequence != last_progress_sequence:
                    last_progress_sequence = sequence
                    print(
                        "[BLENDER][ETAPA] " + str(progress.get("stage", "")),
                        flush=True,
                    )
            except (OSError, json.JSONDecodeError) as error:
                print(
                    f"[BLENDER][PROGRESSO][AVISO] Não foi possível ler a etapa "
                    f"atual: {error}",
                    flush=True,
                )

        status = _read_blender_status(status_path)
        if status and status["status"] in {"done", "error"}:
            forced = False
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    forced = _stop_process_tree(process)
            return status, "", forced

        if process.poll() is not None:
            return (
                status,
                "Blender encerrou sem registrar um resultado terminal; "
                f"código de saída {process.returncode}.",
                False,
            )
        time.sleep(0.1)

    forced = _stop_process_tree(process)
    status = _read_blender_status(status_path)
    if status and status["status"] in {"done", "error"}:
        return status, "", forced
    return (
        status,
        f"Blender excedeu o limite de {timeout_seconds:g} segundos.",
        forced,
    )


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())
    safe = safe.strip("_-")[:80]
    return safe or "Kronos_Blender_Project"


def _choose_save_path(default_name: str) -> str:
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        return filedialog.asksaveasfilename(
            parent=root,
            title="Salvar modelo criado no Blender",
            initialdir=os.path.expanduser("~/Documents"),
            initialfile=f"{default_name}.blend",
            defaultextension=".blend",
            filetypes=[
                (description, extension)
                for extension, description in BLENDER_SAVE_FORMATS.items()
            ],
        )
    finally:
        root.destroy()


def _companion_blend_path(export_path: str) -> str:
    stem, extension = os.path.splitext(export_path)
    candidate = f"{stem}_project.blend"
    suffix = 2
    while os.path.exists(candidate):
        candidate = f"{stem}_project_{suffix}.blend"
        suffix += 1
    return candidate


def _unique_preview_path(export_path: str) -> str:
    stem = os.path.splitext(export_path)[0]
    candidate = f"{stem}_preview.png"
    suffix = 2
    while os.path.exists(candidate):
        candidate = f"{stem}_preview_{suffix}.png"
        suffix += 1
    return candidate


def _should_show_blender() -> bool:
    try:
        windows = [
            window
            for window in gw.getAllWindows()
            if (window.title or "").casefold() == "blender"
            or re.search(
                r"\s-\sblender(?:\s|$)",
                (window.title or "").casefold(),
            )
        ]
    except gw.PyGetWindowException as error:
        print(
            f"[BLENDER][MODO][AVISO] Não foi possível detectar as janelas: {error}. "
            "Usando execução visível.",
            flush=True,
        )
        return True
    return not windows or not all(window.isMinimized for window in windows)


def _detect_botanical_kind(description: str) -> str | None:
    normalized = _normalize_request(description)
    negated_tree = re.search(
        r"\b(?:not|no|without|avoid|exclude|nao|sem|evite|exclua)\s+"
        r"(?:a\s+|an\s+|uma\s+|um\s+)?(?:tree|arvore|arvores)\b",
        normalized,
    )
    if (
        re.search(r"\b(tree|arvore|arvores)\b", normalized)
        and not negated_tree
    ):
        return "tree"
    if re.search(
        r"\b(plant|plants|planta|plantas|folhagem|houseplant|houseplants)\b|"
        r"\bhouse[\s-]+plant(?:s)?\b",
        normalized,
    ):
        return "plant"
    return None


def _detect_asset_kind(description: str) -> str:
    botanical_kind = _detect_botanical_kind(description)
    if botanical_kind:
        return botanical_kind
    normalized = _normalize_request(description)
    singular_rock = re.search(r"\b(rocha|pedra|rock|boulder)\b", normalized)
    plural_rock = re.search(r"\b(rochas|pedras|rocks|boulders)\b", normalized)
    collection_request = re.search(
        r"\b(pilha|grupo|conjunto|cluster|pile|group|collection)\b",
        normalized,
    )
    if singular_rock and not plural_rock and not collection_request:
        return "rock"
    return "generic"


def _supports_generic_botanical_fallback(description: str) -> bool:
    kind = _detect_botanical_kind(description)
    if kind not in {"tree", "plant"}:
        return False
    normalized = _normalize_request(description)
    specific_species = re.search(
        r"\b(oak|pine|fir|spruce|birch|maple|willow|cherry|apple|baobab|"
        r"palm|cedar|redwood|cypress|banyan|ginkgo|mangrove|eucalyptus|"
        r"carvalho|pinheiro|abeto|betula|bordo|salgueiro|cerejeira|"
        r"macieira|baoba|palmeira|cedro|sequoia|orquidea|samambaia|cacto|suculenta)\b",
        normalized,
    )
    return not specific_species


def _supports_generic_tree_fallback(description: str) -> bool:
    return _supports_generic_botanical_fallback(description) and _detect_botanical_kind(description) == "tree"


def _normalize_request(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    )


def _detect_style(description: str) -> str:
    normalized = _normalize_request(description)
    if re.search(r"\b(realista|realistic|fotorealista|photorealistic)\b", normalized):
        return "realistic"
    if re.search(r"\b(low[\s-]?poly|lowpoly|low[\s-]?poligonal)\b", normalized):
        return "low-poly"
    return "stylized"


def _build_botanical_source(kind: str, description: str) -> str:
    """Build botanical assets from deterministic meshes, not guessed primitives."""
    style = _detect_style(description)
    include_pot = bool(set(_normalize_request(description).split()) & {"vaso", "pot"})
    source = f'''import bpy
import math
import random
from mathutils import Vector

KRONOS_ASSET_KIND = {kind!r}
random.seed(73021)

def report(stage):
    _kronos_progress(stage)

def get_collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection

def make_material(name, color, roughness=0.82):
    material = bpy.data.materials.new(name=name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    if shader:
        shader.inputs["Base Color"].default_value = (*color, 1.0)
        shader.inputs["Roughness"].default_value = roughness
    return material

def make_mesh_object(name, collection, vertices, faces, material):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(clean_customdata=True)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = False
        polygon.material_index = 0
    return obj

def make_tapered_branch(name, start, end, radius_start, radius_end, sides, collection, material):
    start = Vector(start)
    end = Vector(end)
    axis = end - start
    if axis.length < 1e-5:
        raise ValueError(name + " has zero length")
    direction = axis.normalized()
    reference = Vector((0.0, 1.0, 0.0))
    if abs(direction.dot(reference)) > 0.94:
        reference = Vector((1.0, 0.0, 0.0))
    side = direction.cross(reference).normalized()
    forward = direction.cross(side).normalized()
    vertices = []
    for point, radius in ((start, radius_start), (end, radius_end)):
        for index in range(sides):
            angle = math.tau * index / sides
            offset = side * math.cos(angle) + forward * math.sin(angle)
            vertices.append(tuple(point + offset * radius))
    faces = [(tuple(reversed(range(sides)))), tuple(range(sides, sides * 2))]
    for index in range(sides):
        following = (index + 1) % sides
        faces.append((index, following, sides + following, sides + index))
    return make_mesh_object(name, collection, vertices, faces, material)

def add_leaf_geometry(vertices, faces, base, tip, width, seed):
    base = Vector(base)
    tip = Vector(tip)
    axis = tip - base
    if axis.length < 1e-4:
        return
    direction = axis.normalized()
    reference = Vector((0.0, 0.0, 1.0))
    if abs(direction.dot(reference)) > 0.92:
        reference = Vector((1.0, 0.0, 0.0))
    across = direction.cross(reference).normalized()
    normal = direction.cross(across).normalized()
    if seed % 2:
        across.negate()
    offset = len(vertices)
    fractions = (0.0, 0.24, 0.52, 0.79, 1.0)
    shape = (0.04, 0.68, 1.0, 0.58, 0.015)
    ring = []
    for fraction, breadth in zip(fractions, shape):
        center = base.lerp(tip, fraction)
        center += normal * (math.sin(math.pi * fraction) * width * 0.15)
        half_width = width * breadth * 0.5
        ridge = normal * width * (0.045 + 0.035 * math.sin(math.pi * fraction))
        thickness = normal * 0.012
        ring.append(tuple(center - across * half_width + ridge + thickness))
    for fraction, breadth in zip(reversed(fractions), reversed(shape)):
        center = base.lerp(tip, fraction)
        center += normal * (math.sin(math.pi * fraction) * width * 0.15)
        half_width = width * breadth * 0.5
        ridge = normal * width * (0.045 + 0.035 * math.sin(math.pi * fraction))
        thickness = normal * 0.012
        ring.append(tuple(center + across * half_width + ridge + thickness))
    for fraction, breadth in zip(fractions, shape):
        center = base.lerp(tip, fraction)
        center += normal * (math.sin(math.pi * fraction) * width * 0.15)
        half_width = width * breadth * 0.5
        thickness = normal * 0.012
        ring.append(tuple(center - across * half_width - thickness))
    for fraction, breadth in zip(reversed(fractions), reversed(shape)):
        center = base.lerp(tip, fraction)
        center += normal * (math.sin(math.pi * fraction) * width * 0.15)
        half_width = width * breadth * 0.5
        thickness = normal * 0.012
        ring.append(tuple(center + across * half_width - thickness))
    vertices.extend(ring)
    front_center = len(vertices)
    vertices.append(tuple(base.lerp(tip, 0.5) + normal * width * 0.08))
    back_center = len(vertices)
    vertices.append(tuple(base.lerp(tip, 0.5) - normal * 0.012))
    for index in range(10):
        a = offset + index
        b = offset + (index + 1) % 10
        faces.append((front_center, a, b))
        back_a = offset + 10 + (index + 1) % 10
        back_b = offset + 10 + index
        faces.append((back_center, back_a, back_b))
        faces.append((a, offset + 10 + index, offset + 10 + (index + 1) % 10, b))

def make_leaf(name, base, tip, width, collection, material, seed):
    vertices = []
    faces = []
    add_leaf_geometry(vertices, faces, base, tip, width, seed)
    return make_mesh_object(name, collection, vertices, faces, material)

def make_leaf_cluster(name, leaf_specs, collection, material):
    vertices = []
    faces = []
    for index, (base, tip, width) in enumerate(leaf_specs):
        add_leaf_geometry(vertices, faces, base, tip, width, index)
    return make_mesh_object(name, collection, vertices, faces, material)

report("Preparando materiais e colecoes")
structure = get_collection("KRONOS | Estrutura")
foliage = get_collection("KRONOS | Folhagem")
bark = make_material("KRONOS | Caule e galhos", (0.24, 0.12, 0.055) if {style!r} != "realistic" else (0.18, 0.09, 0.04))
greens = [
    make_material("KRONOS | Folha verde " + str(index + 1), color)
    for index, color in enumerate(
    ((0.045, 0.21, 0.035), (0.075, 0.31, 0.045), (0.12, 0.39, 0.065), (0.035, 0.16, 0.025))
    )
]

if KRONOS_ASSET_KIND == "plant":
report("Planejando uma planta de folhas largas com multiplos caules")
leafs_per_stem = 5 if {style!r} == "low-poly" else (8 if {style!r} == "realistic" else 6)
stem_layout = ((-0.17, 0.02, 1.82, 0.1), (0.14, -0.04, 2.12, 2.2), (0.02, 0.16, 1.64, 4.1))
sides = 7 if {style!r} == "low-poly" else 10
total_leaves = 0
for stem_index, (root_x, root_y, stem_height, phase) in enumerate(stem_layout):
    stem_name = "Plant_Stem" if stem_index == 0 else "Plant_Stem_{{:02d}}".format(stem_index + 1)
    stem_vertices = []
    stem_faces = []
    ring_profiles = ((0.0, 0.070), (0.24, 0.060), (0.52, 0.046), (0.78, 0.032), (1.0, 0.020))
    for ring_index, (fraction, radius) in enumerate(ring_profiles):
        height = stem_height * fraction
        center_x = root_x + 0.035 * math.sin(height * 1.2 + phase)
        center_y = root_y + 0.025 * math.sin(height * 1.6 + phase)
        for side_index in range(sides):
            angle = math.tau * side_index / sides + (ring_index % 2) * 0.08
            stem_vertices.append((center_x + math.cos(angle) * radius, center_y + math.sin(angle) * radius, height))
    stem_faces.extend((tuple(reversed(range(sides))), tuple(range((len(ring_profiles) - 1) * sides, len(ring_profiles) * sides))))
    for ring_index in range(len(ring_profiles) - 1):
        for side_index in range(sides):
            following = (side_index + 1) % sides
            current = ring_index * sides + side_index
            next_ring = (ring_index + 1) * sides
            stem_faces.append((current, ring_index * sides + following, next_ring + following, next_ring + side_index))
    make_mesh_object(stem_name, structure, stem_vertices, stem_faces, bark)
    report("Caule {{:02d}}/3".format(stem_index + 1))
    for leaf_index in range(leafs_per_stem):
        fraction = 0.24 + 0.105 * leaf_index
        height = stem_height * fraction
        angle = phase + leaf_index * 2.399963229728653 + stem_index * 0.72
        direction = Vector((math.cos(angle), math.sin(angle), 0.0))
        start = Vector((
            root_x + 0.035 * math.sin(height * 1.2 + phase),
            root_y + 0.025 * math.sin(height * 1.6 + phase),
            height,
        ))
        length = 0.66 + 0.12 * ((leaf_index + stem_index) % 3)
        tip = start + direction * length + Vector((0.0, 0.0, 0.16 + 0.035 * (leaf_index % 3)))
        total_leaves += 1
        make_tapered_branch(
            "Plant_Petiole_{{:02d}}".format(total_leaves),
            start,
            start.lerp(tip, 0.25),
            0.023,
            0.011,
            5,
            structure,
            bark,
        )
        make_leaf(
            "Plant_Leaf_{{:02d}}".format(total_leaves),
            start.lerp(tip, 0.20),
            tip,
            0.26 + 0.035 * ((leaf_index + stem_index) % 4),
            foliage,
            greens[(leaf_index + stem_index) % len(greens)],
            total_leaves,
        )
    report("Folhagem do caule {{:02d}}/3".format(stem_index + 1))
    if {include_pot!r}:
        report("Adicionando o vaso solicitado")
        pot_material = make_material("KRONOS | Vaso", (0.47, 0.20, 0.12))
        make_tapered_branch("Plant_Pot", (0, 0, -0.72), (0, 0, -0.08), 0.42, 0.55, 8, structure, pot_material)

elif KRONOS_ASSET_KIND == "tree":
    report("Modelando o tronco afunilado")
    height = 4.7
    trunk_sides = 8 if {style!r} == "low-poly" else (14 if {style!r} == "realistic" else 10)
    trunk_vertices = []
    trunk_faces = []
    trunk_rings = ((0.0, 0.38), (0.5, 0.32), (1.5, 0.24), (2.5, 0.18), (3.5, 0.125), (4.7, 0.055))
    for ring_index, (z, radius) in enumerate(trunk_rings):
        center_x = 0.10 * math.sin(z * 0.82)
        center_y = 0.06 * math.sin(z * 1.1)
        for side_index in range(trunk_sides):
            angle = math.tau * side_index / trunk_sides + (ring_index % 2) * 0.12
            jitter = 1.0 + 0.045 * math.sin(side_index * 3.1 + ring_index)
            trunk_vertices.append((center_x + math.cos(angle) * radius * jitter, center_y + math.sin(angle) * radius * jitter, z))
    trunk_faces.extend((tuple(reversed(range(trunk_sides))), tuple(range((len(trunk_rings) - 1) * trunk_sides, len(trunk_rings) * trunk_sides))))
    for ring_index in range(len(trunk_rings) - 1):
        for side_index in range(trunk_sides):
            following = (side_index + 1) % trunk_sides
            current = ring_index * trunk_sides + side_index
            next_ring = (ring_index + 1) * trunk_sides
            trunk_faces.append((current, ring_index * trunk_sides + following, next_ring + following, next_ring + side_index))
    make_mesh_object("Tree_Trunk", structure, trunk_vertices, trunk_faces, bark)
    report("Crescendo galhos estruturais")
    tiers = ((1.55, 1.55), (2.15, 1.40), (2.75, 1.20), (3.30, 0.95), (3.75, 0.68))
    branch_count = 0
    cluster_count = 0
    for tier_index, (z, reach) in enumerate(tiers):
        arms = 4 if tier_index < 3 else 3
        for arm_index in range(arms):
            angle = math.tau * arm_index / arms + tier_index * 0.57
            radial = Vector((math.cos(angle), math.sin(angle), 0.0))
            start = Vector((0.10 * math.sin(z * 0.82), 0.06 * math.sin(z * 1.1), z))
            end = start + radial * reach + Vector((0.0, 0.0, 0.42 + 0.08 * (arm_index % 3)))
            branch_count += 1
            make_tapered_branch(
                "Tree_Branch_{{:02d}}".format(branch_count),
                start,
                end,
                0.135 if tier_index < 2 else 0.10,
                0.035,
                6 if {style!r} == "low-poly" else 8,
                structure,
                bark,
            )
            for fork_index, side_sign in enumerate((-1.0, 1.0)):
                fork_base = start.lerp(end, 0.62 + fork_index * 0.16)
                fork_angle = angle + side_sign * (0.62 + 0.12 * tier_index)
                fork_direction = Vector((math.cos(fork_angle), math.sin(fork_angle), 0.0))
                fork_tip = fork_base + fork_direction * reach * 0.42 + Vector((0, 0, 0.43))
                branch_count += 1
                make_tapered_branch(
                    "Tree_Branch_{{:02d}}".format(branch_count),
                    fork_base,
                    fork_tip,
                    0.065,
                    0.018,
                    5 if {style!r} == "low-poly" else 7,
                    structure,
                    bark,
                )
                leaf_specs = []
                leaf_count = 7 if {style!r} == "low-poly" else (13 if {style!r} == "realistic" else 9)
                for leaf_index in range(leaf_count):
                    leaf_angle = math.tau * leaf_index / leaf_count + 0.37 * fork_index
                    tangent = Vector((math.cos(leaf_angle), math.sin(leaf_angle), 0.0))
                    base = fork_tip + tangent * (0.10 + 0.08 * (leaf_index % 2))
                    tip = base + tangent * (0.28 + 0.06 * (leaf_index % 3)) + Vector((0.0, 0.0, 0.16 + 0.04 * (leaf_index % 2)))
                    leaf_specs.append((base, tip, 0.14 + 0.025 * (leaf_index % 3)))
                cluster_count += 1
                make_leaf_cluster(
                    "Tree_Leaves_Cluster_{{:02d}}".format(cluster_count),
                    leaf_specs,
                    foliage,
                    greens[(tier_index + arm_index + fork_index) % len(greens)],
                )
        if tier_index % 2 == 1:
            report("Galhos e copas {{:02d}}/{{}}".format(tier_index + 1, len(tiers)))
    if branch_count < 30 or cluster_count < 15:
        raise RuntimeError("A arvore ficou sem a quantidade minima de galhos e copas.")

report("Validando objetos e materiais botanicos")
'''
    lines = source.splitlines()
    plant_start = lines.index('if KRONOS_ASSET_KIND == "plant":') + 1
    tree_start = lines.index('elif KRONOS_ASSET_KIND == "tree":')
    plant_block = textwrap.dedent("\n".join(lines[plant_start:tree_start]))
    lines[plant_start:tree_start] = textwrap.indent(
        plant_block,
        "    ",
    ).splitlines()
    return "\n".join(lines) + "\n"


def _validate_generated_source(source: str) -> None:
    if len(source.encode("utf-8")) > 100_000:
        raise ValueError("O script gerado excede o limite de 100 KB.")
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as error:
        raise ValueError(
            f"Erro de sintaxe no script gerado, linha {error.lineno}: {error.msg}"
        ) from error
    if sum(1 for _ in ast.walk(tree)) > 20_000:
        raise ValueError("O script gerado excede o limite de complexidade.")

    def dotted_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [alias.name.split(".", 1)[0] for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module.split(".", 1)[0] if node.module else ""]
            )
            if any(module not in _SAFE_IMPORTS for module in modules):
                raise ValueError(
                    "Import bloqueado no script gerado. "
                    "Somente bpy, bmesh, math, mathutils e random são permitidos."
                )
        elif isinstance(node, ast.Name) and node.id in {
            "__builtins__",
            "__loader__",
            "__package__",
            "__spec__",
        }:
            raise ValueError("Acesso ao ambiente interno do Python foi bloqueado.")
        elif isinstance(node, (ast.While, ast.AsyncFor, ast.AsyncFunctionDef, ast.With, ast.AsyncWith)):
            raise ValueError(
                f"Construção potencialmente não limitada bloqueada: "
                f"{type(node).__name__}."
            )
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Acesso a atributos internos do Python foi bloqueado.")
        elif isinstance(node, ast.Attribute):
            target = dotted_name(node)
            if target.startswith(
                (
                    "bpy.data.images",
                    "bpy.data.libraries",
                    "bpy.data.fonts",
                    "bpy.data.movieclips",
                    "bpy.data.sounds",
                    "bpy.context.preferences",
                    "bpy.app",
                    "bpy.utils",
                )
            ):
                raise ValueError(f"Acesso Blender não permitido: {target}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_BUILTINS:
                raise ValueError(
                    f"A chamada potencialmente perigosa {node.func.id}() foi bloqueada."
                )
            target = dotted_name(node.func)
            known_invalid_operators = {
                "bmesh.ops.create_ico_sphere": (
                    "bmesh.ops.create_icosphere"
                ),
                "bmesh.ops.create_uv_sphere": (
                    "bmesh.ops.create_uvsphere"
                ),
                "bmesh.ops.dupe_mesh": (
                    "mesh.from_pydata(vertices, edges, faces), com índices "
                    "pertencentes à malha de destino"
                ),
            }
            if target in known_invalid_operators:
                raise ValueError(
                    f"Operador BMesh inexistente: {target}; use "
                    f"{known_invalid_operators[target]}."
                )
            if target == "bpy.ops.mesh.primitive_cylinder_add":
                invalid_keywords = {
                    keyword.arg
                    for keyword in node.keywords
                    if keyword.arg in {"radius1", "radius2"}
                }
                if invalid_keywords:
                    raise ValueError(
                        "primitive_cylinder_add não aceita radius1/radius2; "
                        "use radius ou primitive_cone_add para um cone afunilado."
                    )
            if target.startswith("bpy.ops."):
                parts = target.split(".")
                if len(parts) != 4:
                    raise ValueError(f"Operador Blender não permitido: {target}")
                namespace, operator = parts[2], parts[3]
                allowed = (
                    operator in _SAFE_OBJECT_OPERATORS
                    if namespace == "object"
                    else operator in _SAFE_MESH_OPERATORS
                    if namespace == "mesh"
                    else False
                )
                if not allowed:
                    raise ValueError(f"Operador Blender não permitido: {target}")
            if target in {
                "bpy.data.images.load",
                "bpy.data.libraries.load",
                "bpy.data.fonts.load",
                "bpy.data.movieclips.load",
                "bpy.data.sounds.load",
            }:
                raise ValueError(f"Carregamento externo de arquivos bloqueado: {target}")
            if target.endswith(
                (".save", ".save_render", ".save_as_mainfile", ".write", ".open")
            ):
                raise ValueError(f"Operação de arquivo bloqueada: {target}")
            if isinstance(node.func, ast.Name) and node.func.id == "range":
                try:
                    values = [ast.literal_eval(argument) for argument in node.args]
                    if len(range(*values)) > 5_000:
                        raise ValueError(
                            "O script contém um loop range() acima de 5.000 itens."
                        )
                except (ValueError, TypeError, OverflowError):
                    if all(isinstance(argument, ast.Constant) for argument in node.args):
                        raise


def _build_saved_project_validator(
    expected_kind: str,
    blend_path: str,
    export_path: str,
    export_extension: str,
    require_mesh_materials: bool = True,
) -> str:
    return f'''import bpy
import bmesh
import json
import math
import os
from mathutils import Vector

expected_kind = {expected_kind!r}
expected_blend_path = {os.path.normcase(os.path.abspath(blend_path))!r}
export_path = {export_path!r}
export_extension = {export_extension!r}
require_mesh_materials = {require_mesh_materials!r}

def mesh_leaf_stats(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    remaining = set(mesh.faces)
    components = 0
    leaf_shaped_components = 0
    while remaining:
        components += 1
        pending = [remaining.pop()]
        component_faces = []
        while pending:
            face = pending.pop()
            component_faces.append(face)
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        pending.append(neighbor)
        vertices = {{vertex for face in component_faces for vertex in face.verts}}
        points = [vertex.co.copy() for vertex in vertices]
        if len(points) >= 12:
            longest = (0.0, None, None)
            for index, point in enumerate(points):
                for other in points[index + 1:]:
                    distance = (other - point).length
                    if distance > longest[0]:
                        longest = (distance, point, other)
            if longest[1] is not None:
                axis = (longest[2] - longest[1]).normalized()
                width = max(
                    (point - longest[1]).cross(axis).length
                    for point in points
                )
                if width > 1e-8 and longest[0] / width >= 4.0:
                    leaf_shaped_components += 1
    mesh.free()
    return components, leaf_shaped_components

def validate_saved_scene():
    geometry = [
        obj for obj in bpy.context.scene.objects
        if obj.type in {{"MESH", "CURVE", "SURFACE", "FONT", "META"}}
    ]
    meshes = [obj for obj in geometry if obj.type == "MESH"]
    if not meshes or not bpy.data.filepath:
        raise RuntimeError("O projeto salvo reabriu sem arquivo ou sem malhas.")
    if os.path.normcase(os.path.abspath(bpy.data.filepath)) != expected_blend_path:
        raise RuntimeError("O Blender abriu um projeto diferente do arquivo solicitado.")
    faces = 0
    for obj in meshes:
        if not obj.data.vertices or not obj.data.polygons:
            raise RuntimeError("Malha vazia no projeto reaberto: " + obj.name)
        faces += len(obj.data.polygons)
        if (
            (require_mesh_materials and not obj.data.materials)
            or any(material is None for material in obj.data.materials)
        ):
            raise RuntimeError("Material ausente após reabrir: " + obj.name)
        if any(
            polygon.area <= 1e-10
            or (
                require_mesh_materials
                and polygon.material_index >= len(obj.data.materials)
            )
            for polygon in obj.data.polygons
        ):
            raise RuntimeError("Face/material inválido após reabrir: " + obj.name)
    leaves = [
        obj for obj in meshes
        if obj.name.startswith("Plant_Leaf_") or obj.name.startswith("Tree_Leaves_")
    ]
    stems = [
        obj for obj in meshes
        if obj.name == "Plant_Stem" or obj.name.startswith("Plant_Stem_")
    ]
    if expected_kind == "plant" and (
        not stems or len(leaves) < 5
    ):
        raise RuntimeError("Planta incompleta após reabrir o arquivo .blend.")
    if expected_kind == "plant":
        container = (
            bpy.data.objects.get("Plant_Soil")
            or bpy.data.objects.get("Plant_Pot")
        )
        if container:
            container_top = max(
                (container.matrix_world @ Vector(corner)).z
                for corner in container.bound_box
            )
            visible_leaves = sum(
                max(
                    (obj.matrix_world @ Vector(corner)).z
                    for corner in obj.bound_box
                ) > container_top + 0.05
                for obj in leaves
            )
            required_visible = max(5, math.ceil(len(leaves) * 0.6))
            if visible_leaves < required_visible:
                raise RuntimeError(
                    "Qualidade botânica: somente "
                    + str(visible_leaves)
                    + "/"
                    + str(len(leaves))
                    + " folhas estão visíveis acima do vaso/substrato."
                )
    if expected_kind == "tree":
        branches = [
            obj for obj in meshes if obj.name.startswith("Tree_Branch_")
        ]
        if (
            bpy.data.objects.get("Tree_Trunk") is None
            or len(branches) < 20
            or len(leaves) < 15
        ):
            raise RuntimeError("Árvore incompleta após reabrir o arquivo .blend.")
        saved_leaf_faces = sum(len(obj.data.polygons) for obj in leaves)
        if saved_leaf_faces < 1_000:
            raise RuntimeError(
                "Folhagem incompleta após reabrir o arquivo .blend: exigidas "
                "1.000 faces; encontradas " + str(saved_leaf_faces) + "."
            )
        leaf_centers = [
            tuple(
                round(
                    (
                        min((obj.matrix_world @ Vector(corner))[axis] for corner in obj.bound_box)
                        + max((obj.matrix_world @ Vector(corner))[axis] for corner in obj.bound_box)
                    )
                    * 0.5,
                    2,
                )
                for axis in range(3)
            )
            for obj in leaves
        ]
        project_height = max(
            (obj.matrix_world @ Vector(corner)).z
            for obj in geometry
            for corner in obj.bound_box
        ) - min(
            (obj.matrix_world @ Vector(corner)).z
            for obj in geometry
            for corner in obj.bound_box
        )
        if (
            len(set(leaf_centers)) < 12
            or max(center[2] for center in leaf_centers)
            - min(center[2] for center in leaf_centers)
            < project_height * 0.12
        ):
            raise RuntimeError(
                "Distribuição de folhas inadequada após reabrir o arquivo .blend."
            )
        individual_leaf_groups = sum(
            components >= 3 and leaf_components >= 3
            for components, leaf_components in
            (mesh_leaf_stats(obj) for obj in leaves)
        )
        required_individual_groups = math.ceil(len(leaves) * 0.8)
        if individual_leaf_groups < required_individual_groups:
            raise RuntimeError(
                "Grupos de folhagem inadequados após reabrir o arquivo .blend: "
                "cada grupo precisa conter ao menos três folhas volumétricas "
                "individuais e alongadas (não esferas/rochas); grupos válidos "
                + str(individual_leaf_groups)
                + "/"
                + str(len(leaves))
                + "."
            )
    if expected_kind == "rock":
        primary = bpy.data.objects.get("Rock_Main")
        rock_objects = [
            obj for obj in meshes if obj.name.startswith("Rock_")
        ]
        rock_faces = sum(len(obj.data.polygons) for obj in rock_objects)
        if (
            primary is None
            or primary.type != "MESH"
            or len(rock_objects) > 4
            or len(primary.data.polygons) < 40
            or len(primary.data.polygons) < rock_faces * 0.6
        ):
            raise RuntimeError(
                "Rocha singular incompleta após reabrir o arquivo .blend."
            )
        rock_mesh = bmesh.new()
        rock_mesh.from_mesh(primary.data)
        remaining_vertices = set(rock_mesh.verts)
        connected_components = 0
        while remaining_vertices:
            connected_components += 1
            pending_vertices = [remaining_vertices.pop()]
            while pending_vertices:
                vertex = pending_vertices.pop()
                for edge in vertex.link_edges:
                    neighbor = edge.other_vert(vertex)
                    if neighbor in remaining_vertices:
                        remaining_vertices.remove(neighbor)
                        pending_vertices.append(neighbor)
        rock_mesh.free()
        if connected_components != 1:
            raise RuntimeError(
                "Rocha principal desconectada após reabrir o arquivo .blend."
            )

    separation_parts = 0
    leaves_are_separate = False
    if expected_kind == "tree":
        candidates = [
            obj for obj in leaves
            if len(obj.data.polygons) > 100
        ]
        if not candidates:
            leaves_are_separate = len(leaves) >= 15 and all(
                obj.data.polygons
                and obj.data.materials
                and all(material is not None for material in obj.data.materials)
                for obj in leaves
            )
            if not leaves_are_separate:
                raise RuntimeError(
                    "Não há malha de folhas agrupadas para testar Separate e "
                    "as folhas não estão organizadas em objetos editáveis."
                )
        else:
            original = max(candidates, key=lambda obj: len(obj.data.polygons))
            before_names = {{obj.name for obj in bpy.data.objects}}
            test_copy = original.copy()
            test_copy.data = original.data.copy()
            bpy.context.scene.collection.objects.link(test_copy)
            bpy.ops.object.select_all(action="DESELECT")
            test_copy.select_set(True)
            bpy.context.view_layer.objects.active = test_copy
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="LOOSE")
            bpy.ops.object.mode_set(mode="OBJECT")
            created = [
                obj for obj in bpy.data.objects
                if obj.name not in before_names and obj.type == "MESH"
            ]
            separation_parts = len(created)
            if separation_parts < 5:
                raise RuntimeError(
                    "Separate > By Loose Parts separou somente "
                    + str(separation_parts)
                    + " componentes de folhas."
                )
            for part in created:
                if not part.data.polygons or not part.data.materials or any(
                    material is None for material in part.data.materials
                ):
                    raise RuntimeError(
                        "Uma folha desapareceu ou perdeu o material após Separate: "
                        + part.name
                    )
            for part in created:
                bpy.data.objects.remove(part, do_unlink=True)

    imported_meshes = 0
    if export_extension:
        before_import = {{obj.name for obj in bpy.context.scene.objects}}
        if export_extension == ".fbx" and hasattr(bpy.ops.import_scene, "fbx"):
            bpy.ops.import_scene.fbx(filepath=export_path)
        elif export_extension == ".glb" and hasattr(bpy.ops.import_scene, "gltf"):
            bpy.ops.import_scene.gltf(filepath=export_path)
        elif export_extension == ".obj" and hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=export_path)
        else:
            raise RuntimeError(
                "O Blender instalado não possui importador para "
                + export_extension
            )
        imported_meshes = sum(
            1 for obj in bpy.context.scene.objects
            if obj.name not in before_import
            and obj.type == "MESH"
            and obj.data.polygons
        )
        if imported_meshes == 0:
            raise RuntimeError(
                "A exportação "
                + export_extension
                + " não pôde ser reimportada como geometria."
            )
        imported_objects = [
            obj for obj in bpy.context.scene.objects
            if obj.name not in before_import and obj.type == "MESH"
        ]
        if any(
            not obj.data.materials
            or any(material is None for material in obj.data.materials)
            for obj in imported_objects
        ):
            raise RuntimeError(
                "A exportação "
                + export_extension
                + " perdeu materiais na reimportação."
            )

    report = {{
        "reopened": True,
        "objects": len(geometry),
        "meshes": len(meshes),
        "faces": faces,
        "leaf_objects": len(leaves),
        "separated_leaf_parts": separation_parts,
        "leaves_are_separate": leaves_are_separate,
        "roundtrip_imported_meshes": imported_meshes,
    }}
    print("KRONOS_SAVED_QA " + json.dumps(report), flush=True)

validate_saved_scene()
'''


def _inspect_render(render_path: str) -> dict[str, float | int] | None:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        print(
            "[BLENDER][QA][AVISO] Pillow não está instalado; "
            "inspeção visual automática ignorada.",
            flush=True,
        )
        return None
    try:
        with Image.open(render_path) as image:
            image.verify()
        with Image.open(render_path) as source:
            image = source.convert("RGB")
            image.load()
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Prévia PNG inválida ou ilegível: {error}") from error

    if image.width < 128 or image.height < 128:
        raise RuntimeError(
            f"Prévia pequena demais para inspeção: {image.width}x{image.height}."
        )
    corners = [
        image.getpixel((0, 0)),
        image.getpixel((image.width - 1, 0)),
        image.getpixel((0, image.height - 1)),
        image.getpixel((image.width - 1, image.height - 1)),
    ]
    background = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    difference = ImageChops.difference(
        image,
        Image.new("RGB", image.size, background),
    ).convert("L")
    foreground = difference.point(lambda value: 255 if value > 22 else 0)
    bounds = foreground.getbbox()
    ratio = sum(foreground.histogram()[1:]) / (image.width * image.height)
    if bounds is None or ratio < 0.003:
        raise RuntimeError(
            "Inspeção visual: o render parece vazio; o modelo não ocupa "
            "visivelmente a imagem."
        )
    if ratio > 0.88:
        raise RuntimeError(
            "Inspeção visual: o modelo ocupa quase todo o quadro e pode estar cortado."
        )
    return {
        "width": image.width,
        "height": image.height,
        "foreground_ratio": round(ratio, 4),
    }


def _validate_saved_project(
    blender_executable: str,
    blend_path: str,
    export_path: str,
    export_extension: str,
    expected_kind: str,
    work_dir: str,
    require_mesh_materials: bool = True,
) -> dict[str, object]:
    validator_path = os.path.join(work_dir, "validate_saved_project.py")
    with open(validator_path, "w", encoding="utf-8", newline="\n") as validator_file:
        validator_file.write(
            _build_saved_project_validator(
                expected_kind,
                blend_path,
                export_path if export_extension else "",
                export_extension,
                require_mesh_materials,
            )
        )
    result = subprocess.run(
        [
            blender_executable,
            "--background",
            blend_path,
            "--python",
            validator_path,
        ],
        cwd=work_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=BLENDER_TIMEOUT_SECONDS,
        check=False,
    )
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    report_line = next(
        (line for line in output.splitlines() if line.startswith("KRONOS_SAVED_QA ")),
        None,
    )
    if result.returncode != 0 or report_line is None:
        raise RuntimeError(
            "Verificação ao reabrir o .blend/exportar falhou: "
            + output[-4000:]
        )
    try:
        return json.loads(report_line.partition(" ")[2])
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Blender retornou um relatório de qualidade ilegível: {error}"
        ) from error


def _generate_source(
    description: str,
    previous_source: str = "",
    error_details: str = "",
) -> str:
    correction = ""
    if error_details:
        geometry_correction = ""
        if "não manifold" in error_details.casefold() or "non-manifold" in error_details.casefold():
            geometry_correction = (
                "\nCorreção geométrica obrigatória: a validação encontrou arestas "
                "não manifold. Não basta recalcular normais nem ignorar o contador. "
                "Localize os objetos e arestas problemáticos e gere folhas como "
                "volumes fechados (com faces de frente, verso e laterais), não "
                "planos sem espessura. Verifique que cada aresta do caule, galho "
                "e folha pertence exatamente a duas faces antes de concluir."
            )
        if "copa incompleta" in error_details.casefold():
            geometry_correction += (
                "\nCorreção botânica obrigatória: a copa não atingiu os mínimos "
                "de grupos/folhas e faces indicados no diagnóstico. Preserve os "
                "limites exigidos; acrescente folhas volumétricas reais às pontas "
                "de ramificações distribuídas em diferentes alturas e direções, "
                "com materiais atribuídos e silhueta irregular. Não conte planos, "
                "cópias coincidentes, cascas de triangulação ou uma massa de "
                "folhagem como folhas adicionais."
            )
        if "grupos de folhagem" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de copa obrigatória: os agrupamentos atuais são massas "
                "únicas. Modele em cada objeto de copa pelo menos três folhas "
                "individuais, alongadas e fechadas, separadas entre si na malha; "
                "cada folha deve ter comprimento mínimo de duas vezes a largura. "
                "Não substitua folhas por cones, pirâmides, icosferas, elipsoides "
                "ou pedras."
            )
        if "bmesh.ops.dupe_mesh" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de API obrigatória: `bmesh.ops.dupe_mesh` não existe. "
                "Não tente outro nome de operador de duplicação BMesh. Para criar "
                "folhas separadas, gere seus vértices/faces em listas, ajuste os "
                "índices das faces e use `mesh.from_pydata`; ou copie um objeto "
                "Blender já criado com `obj.copy()` e `obj.data.copy()`."
            )
        if "from another mesh" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de malha obrigatória: não passe vértices/arestas/faces "
                "de um BMesh para outro operador BMesh. Construa uma malha nova "
                "com vértices e índices próprios, ou copie objeto e dados com "
                "`obj.copy()`/`obj.data.copy()` antes de transformar."
            )
        if "qualidade rochosa" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de rocha obrigatória: construa uma única malha "
                "conectada `Rock_Main`, com silhueta angular irregular e faces "
                "próprias. Não monte o volume com icoesferas, elipsoides ou "
                "pedras grandes sobrepostas; use poucos detalhes separados."
            )
        if "not in collection" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de coleção obrigatória: Não chame unlink() em 'Scene Collection' para objetos "
                "criados com bpy.data.objects.new(). Basta vinculá-los à coleção de destino com colecao.objects.link(obj)."
            )
        if "área zero" in error_details.casefold() or "area zero" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de área zero obrigatória: As faces das folhas geraram polígonos colapsados com área nula. "
                "Para criar folhas perfeitas sem erro de área zero e sem arestas não-manifold, construa a lâmina foliar "
                "como malha aberta simples e adicione o modificador Solidify: "
                "mod = obj.modifiers.new(name='Solidify', type='SOLIDIFY'); mod.thickness = 0.015; "
                "bpy.context.view_layer.objects.active = obj; bpy.ops.object.modifier_apply(modifier=mod.name)."
            )
        if "create_cone" in error_details.casefold() or "invalid for this operator" in error_details.casefold():
            geometry_correction += (
                "\nCorreção de operador BMesh: Em bmesh.ops.create_cone, os parâmetros de raio são radius1 e radius2 "
                "(nunca use diameter1 ou diameter2)."
            )
        correction = (
            "\n\nO script anterior falhou ao executar no Blender. Corrija o script "
            "completo sem reescrever partes que já funcionam. Classifique a causa "
            "como erro de sintaxe/API, execução, geometria, material, dimensão, "
            "exportação ou render; corrija especificamente essa causa. Erro e "
            "diagnóstico de qualidade:\n"
            f"{error_details[-5000:]}\n"
            f"{geometry_correction}\n"
            "Mantenha a solicitação original e retorne apenas o código Python."
        )
    prompt = f"""Crie um script Python executável no Blender 5.2 usando bpy para:
{description}

DIRETRIZES DE MODELAGEM 3D PROFISSIONAL:
- Trate a descrição como especificação técnica estrita. Modele exatamente o objeto solicitado com geometria, proporções, silhueta e detalhes próprios. Nunca substitua por modelos genéricos.
- Preserve o estilo solicitado (low-poly, estilizado ou realista); utilize 'stylized' por padrão.
- Organize o modelo em coleções lógicas ('Estrutura', 'Detalhes', 'Folhagem', etc.) e dê nomes semânticos aos objetos.
- Utilize materiais Principled BSDF com cores harmônicas e valores de Roughness adequados. Todos os objetos de malha devem ter material atribuído.
- Você tem permissão total para utilizar modificadores e ferramentas avançadas de modelagem quando apropriado:
  * Modificadores via Python: `mod = obj.modifiers.new(name='Bevel', type='BEVEL'); mod.width = 0.04; mod.segments = 2`
  * Modificador de Subdivisão: `mod = obj.modifiers.new(name='Subsurf', type='SUBSURF'); mod.levels = 1`
  * Modificador de Espelhamento: `mod = obj.modifiers.new(name='Mirror', type='MIRROR')`
  * Modificador de Solidificação: `mod = obj.modifiers.new(name='Solidify', type='SOLIDIFY'); mod.thickness = 0.05`
  * Modificador Booleano: `mod = obj.modifiers.new(name='Boolean', type='BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = corte_obj`
  * Operadores de malha permitidos: extrusão, inset, bevel, subdivisão, corte (bisect/loopcut), separação, união e shading flat/smooth.
- Chame `_kronos_progress("etapa curta")` no mínimo 3 vezes para relatar as fases da construção.

QUALIDADE GEOMÉTRICA E BOTÂNICA:
- COLEÇÕES E OBJETOS:
  * Quando criar novos objetos com bpy.data.objects.new(nome, mesh), vincule-os DIRETAMENTE à coleção desejada com colecao.objects.link(obj). NUNCA chame bpy.context.scene.collection.objects.unlink(obj).
- OPERADORES BMESH:
  * Em bmesh.ops.create_cone, os argumentos corretos são: radius1, radius2, depth, cap_ends, cap_tris, segments (nunca use 'diameter1' ou 'diameter2').
- MALHAS VOLUMÉTRICAS E MODIFICADOR SOLIDIFY (SEM DEFEITOS):
  * Toda geometria (tronco, galhos, caules, folhas e pétalas) DEVE ser volumétrica e fechada (2-manifold), sem planos sem espessura e SEM faces de área zero (área <= 1e-10).
  * O método mais limpo e confiável para criar folhas volumétricas perfeitas é criar a malha plana da folha e aplicar o modificador Solidify:
    leaf_mod = leaf_obj.modifiers.new(name="Solidify", type="SOLIDIFY")
    leaf_mod.thickness = 0.012
    leaf_mod.offset = 0.0
    bpy.context.view_layer.objects.active = leaf_obj
    bpy.ops.object.modifier_apply(modifier=leaf_mod.name)
    Isso elimina 100% de arestas não-manifold e faces degeneradas de área zero!
- ÁRVORES:
  * O tronco deve ser nomeado `Tree_Trunk`, com conicidade natural (base mais larga, afunilando para o topo) e leve curvatura orgânica.
  * Crie galhos volumétricos (`Tree_Branch_01`, `Tree_Branch_02`, etc., mínimo 20 galhos) saindo em espiral ou tiers ao longo da altura.
  * Crie copas/folhagens volumétricas (`Tree_Leaves_01`, etc., mínimo 15 objetos, somando >= 1.000 faces) posicionadas nas extremidades dos galhos, com silhueta recortada e orgânica (não empilhe esferas perfeitas ou pedras). Cada cluster deve conter lâminas foliares volumétricas bem definidas com comprimento > 2x largura.
- PLANTAS:
  * O caule principal deve ser `Plant_Stem` (e secundários `Plant_Stem_02`...).
  * Crie folhas (`Plant_Leaf_01`, etc., mínimo 5 folhas com >= 250 faces somadas) com pecíolo e lâmina com curvatura elegante.
  * Em plantas em vaso (`Plant_Pot`), certifique-se de que as folhas fiquem visivelmente elevadas acima da borda do vaso.
- ROCHAS / PEDRAS:
  * Uma rocha singular deve ter o volume principal conectado nomeado `Rock_Main` (>= 40 faces), com facetas angulares irregulares e chanfros que transmitam solidez mineral. Não monte empilhando esferas.
- OBJETOS GERAIS (Mecânica, Mobiliário, Cenários):
  * Mantenha proporções reais ou estilizadas consistentes, use bevel nos cantos vivos para reagir bem à iluminação e posicione a base em Z=0.

RESTRIÇÕES DO AMBIENTE:
- Inicie o script importando: `import bpy, bmesh, math, mathutils, random; from mathutils import Vector, Matrix`
- Utilize loops `for ... in range(...)`; nunca utilize `while`, `globals()`, `locals()`, `getattr()` ou `eval()`.
- Apenas bpy, bmesh, math, mathutils e random. Sem chamadas externas perigosas.
- Não tente limpar a cena, salvar arquivo nem configurar câmeras/luzes (o executor do KRONOS cuida do enquadramento, luz e render).
- Retorne SOMENTE o código Python puro, sem Markdown ou explicações.{correction}"""
    if error_details and previous_source:
        prompt += f"\n\nCódigo anterior:\n{previous_source[:12000]}"

    errors = []
    for model in MODEL_ROUTER["tools"]:
        try:
            client = genai.Client(
                api_key=key_rotator.current_key,
                http_options={
                    "timeout": 60000,
                },
            )
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.65,
                    max_output_tokens=6000,
                ),
            )
            source = re.sub(r"^\s*```(?:python)?\s*", "", response.text or "")
            source = re.sub(r"\s*```\s*$", "", source).strip()
            if not source:
                raise RuntimeError("o modelo retornou um script vazio")
            return source
        except Exception as error:
            errors.append(f"{model}: {error}")
            print(f"[BLENDER][GERACAO][AVISO] {model}: {error}", flush=True)
            key_rotator.rotate("Geração de script Blender")
    raise RuntimeError("Falha nos modelos de geração: " + " | ".join(errors))


def _build_runner(
    source_path: str,
    blend_path: str,
    render_path: str,
    export_path: str,
    status_path: str,
    progress_path: str,
    visible: bool,
    expected_kind: str,
) -> str:
    return f'''import bpy
import bmesh
import json
import math
import os
import runpy
import time
import traceback
import mathutils
from mathutils import Vector, Matrix

source_path = {source_path!r}
blend_path = {blend_path!r}
render_path = {render_path!r}
export_path = {export_path!r}
status_path = {status_path!r}
progress_path = {progress_path!r}
visible = {visible!r}
expected_kind = {expected_kind!r}

def write_json_atomic(path, value):
    temporary_path = path + "." + str(os.getpid()) + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as status_file:
        json.dump(value, status_file)
    for attempt in range(20):
        try:
            os.replace(temporary_path, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01)

def write_status(status):
    write_json_atomic(status_path, status)

progress_sequence = 0

def write_progress(label):
    global progress_sequence
    progress_sequence += 1
    write_json_atomic(progress_path, {{
        "sequence": progress_sequence,
        "stage": str(label),
        "process_id": os.getpid(),
    }})

def mesh_leaf_stats(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    remaining = set(mesh.faces)
    components = 0
    leaf_shaped_components = 0
    while remaining:
        components += 1
        pending = [remaining.pop()]
        component_faces = []
        while pending:
            face = pending.pop()
            component_faces.append(face)
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        pending.append(neighbor)
        vertices = {{vertex for face in component_faces for vertex in face.verts}}
        points = [vertex.co.copy() for vertex in vertices]
        if len(points) >= 12:
            longest = (0.0, None, None)
            for index, point in enumerate(points):
                for other in points[index + 1:]:
                    distance = (other - point).length
                    if distance > longest[0]:
                        longest = (distance, point, other)
            if longest[1] is not None:
                axis = (longest[2] - longest[1]).normalized()
                width = max(
                    (point - longest[1]).cross(axis).length
                    for point in points
                )
                if width > 1e-8 and longest[0] / width >= 4.0:
                    leaf_shaped_components += 1
    mesh.free()
    return components, leaf_shaped_components

def configure_scene():
    scene = bpy.context.scene
    geometry_objects = [
        obj for obj in scene.objects
        if obj.type in {{"MESH", "CURVE", "SURFACE", "FONT", "META"}}
    ]
    if not geometry_objects:
        raise RuntimeError("O script terminou sem criar geometria 3D renderizável.")

    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in geometry_objects
        for corner in obj.bound_box
    ]
    minimum = Vector(tuple(min(point[i] for point in corners) for i in range(3)))
    maximum = Vector(tuple(max(point[i] for point in corners) for i in range(3)))
    center = (minimum + maximum) * 0.5
    radius = max((maximum - minimum).length * 0.5, 1.0)

    camera_data = bpy.data.cameras.new("KRONOS_Camera")
    camera = bpy.data.objects.new("KRONOS_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((1.8, -2.4, 1.5)).normalized() * radius * 3.2
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 50
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = radius * 2.5
    scene.camera = camera

    def add_area_light(name, offset, energy, size):
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center + Vector(offset).normalized() * radius * 2.5
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()

    add_area_light("KRONOS_Key_Light", (1.0, -1.5, 2.0), 620, radius * 1.5)
    add_area_light("KRONOS_Fill_Light", (-1.5, -0.5, 0.8), 320, radius * 1.8)
    add_area_light("KRONOS_Rim_Light", (0.2, 1.5, 1.5), 760, radius * 1.2)

    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("KRONOS_World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.12, 0.14, 0.18, 1)
        background.inputs["Strength"].default_value = 0.35

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = render_path
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "AgX"
    scene.camera.data.dof.use_dof = False
    if visible:
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    region = area.spaces.active.region_3d
                    region.view_location = center
                    region.view_distance = radius * 1.8
                    region.view_rotation = camera.rotation_euler.to_quaternion()
                    region.view_perspective = "PERSP"
                    area.spaces.active.overlay.show_extras = False
                    area.spaces.active.overlay.show_floor = False
                    area.spaces.active.overlay.show_axis_x = False
                    area.spaces.active.overlay.show_axis_y = False
                    area.spaces.active.shading.color_type = "MATERIAL"
                    area.spaces.active.shading.light = "STUDIO"

def validate_model():
    bpy.context.view_layer.update()
    geometry = [
        obj for obj in bpy.context.scene.objects
        if obj.type in {{"MESH", "CURVE", "SURFACE", "FONT", "META"}}
    ]
    meshes = [obj for obj in geometry if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Qualidade: o script não criou nenhuma malha 3D.")
    if len(geometry) > 250:
        raise RuntimeError(
            "Qualidade: o modelo criou "
            + str(len(geometry))
            + " objetos; o limite de edição e desempenho é 250."
        )

    face_count = 0
    vertex_count = 0
    nonmanifold_edges = 0
    missing_material_objects = []
    invalid_faces = []
    for obj in meshes:
        mesh = obj.data
        mesh.validate(verbose=False, clean_customdata=True)
        mesh.update()
        if not mesh.vertices or not mesh.polygons:
            raise RuntimeError("Geometria vazia ou incompleta: " + obj.name)
        vertex_count += len(mesh.vertices)
        face_count += len(mesh.polygons)
        if any(
            not math.isfinite(component)
            for vertex in mesh.vertices
            for component in vertex.co
        ):
            raise RuntimeError("Geometria contém coordenadas inválidas: " + obj.name)
        if any(polygon.area <= 1e-10 for polygon in mesh.polygons):
            invalid_faces.append(obj.name)
        if not mesh.materials or any(material is None for material in mesh.materials):
            missing_material_objects.append(obj.name)
        if any(
            polygon.material_index >= len(mesh.materials)
            for polygon in mesh.polygons
        ):
            raise RuntimeError(
                "Há faces sem um material válido no objeto " + obj.name
            )
        bm = bmesh.new()
        bm.from_mesh(mesh)
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            nonmanifold_edges += sum(not edge.is_manifold for edge in bm.edges)
            bm.to_mesh(mesh)
        bm.free()
    if invalid_faces:
        raise RuntimeError(
            "Qualidade: faces de área zero encontradas em "
            + ", ".join(invalid_faces[:8])
        )
    if missing_material_objects:
        raise RuntimeError(
            "Qualidade: material ausente em "
            + ", ".join(missing_material_objects[:8])
        )
    if face_count > 100_000:
        raise RuntimeError(
            "Qualidade: orçamento de 100.000 faces excedido ("
            + str(face_count)
            + ")."
        )

    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in geometry
        for corner in obj.bound_box
    ]
    if not corners:
        raise RuntimeError("Qualidade: não foi possível medir as dimensões do modelo.")
    minimum = Vector(tuple(min(point[i] for point in corners) for i in range(3)))
    maximum = Vector(tuple(max(point[i] for point in corners) for i in range(3)))
    dimensions = maximum - minimum
    if max(dimensions) < 0.15 or max(dimensions) > 100.0:
        raise RuntimeError(
            "Qualidade: dimensões fora do intervalo esperado: "
            + str(tuple(round(value, 3) for value in dimensions))
        )

    leaf_objects = [
        obj for obj in meshes
        if obj.name.startswith("Plant_Leaf_")
        or obj.name.startswith("Tree_Leaves_")
        or "leaf" in obj.name.casefold()
        or "folha" in obj.name.casefold()
    ]
    branch_objects = [
        obj for obj in meshes
        if obj.name.startswith("Tree_Branch_")
        or "branch" in obj.name.casefold()
        or "galho" in obj.name.casefold()
    ]
    if expected_kind == "plant":
        stems = [
            obj for obj in meshes
            if obj.name == "Plant_Stem" or obj.name.startswith("Plant_Stem_")
        ]
        leaf_faces = sum(len(obj.data.polygons) for obj in leaf_objects)
        if not stems or not any(obj.data.vertices for obj in stems):
            raise RuntimeError("Qualidade botânica: o caule da planta está ausente.")
        if len(leaf_objects) < 5 or leaf_faces < 250:
            raise RuntimeError(
                "Qualidade botânica: esperadas pelo menos 5 folhas com malha "
                "real e materiais próprios; encontrados "
                + str(len(leaf_objects))
                + " objetos de folha e "
                + str(leaf_faces)
                + " faces."
            )
        container = (
            bpy.data.objects.get("Plant_Soil")
            or bpy.data.objects.get("Plant_Pot")
        )
        if container:
            container_top = max(
                (container.matrix_world @ Vector(corner)).z
                for corner in container.bound_box
            )
            visible_leaves = sum(
                max(
                    (obj.matrix_world @ Vector(corner)).z
                    for corner in obj.bound_box
                ) > container_top + 0.05
                for obj in leaf_objects
            )
            required_visible = max(5, math.ceil(len(leaf_objects) * 0.6))
            if visible_leaves < required_visible:
                raise RuntimeError(
                    "Qualidade botânica: somente "
                    + str(visible_leaves)
                    + "/"
                    + str(len(leaf_objects))
                    + " folhas estão visíveis acima do vaso/substrato."
                )
    elif expected_kind == "tree":
        trunk = bpy.data.objects.get("Tree_Trunk")
        leaf_faces = sum(len(obj.data.polygons) for obj in leaf_objects)
        if trunk is None or not trunk.data.vertices:
            raise RuntimeError("Qualidade botânica: o tronco da árvore está ausente.")
        if len(branch_objects) < 20:
            raise RuntimeError(
                "Qualidade botânica: estrutura insuficiente de galhos ("
                + str(len(branch_objects))
                + ")."
            )
        leaf_centers = []
        for obj in leaf_objects:
            corners = [
                obj.matrix_world @ Vector(corner)
                for corner in obj.bound_box
            ]
            if corners:
                leaf_centers.append(
                    tuple(
                        round(
                            (
                                min(point[i] for point in corners)
                                + max(point[i] for point in corners)
                            )
                            * 0.5,
                            2,
                        )
                        for i in range(3)
                    )
                )
        leaf_z_span = (
            max(center[2] for center in leaf_centers)
            - min(center[2] for center in leaf_centers)
            if leaf_centers
            else 0.0
        )
        if len(set(leaf_centers)) < 12 or leaf_z_span < dimensions.z * 0.12:
            raise RuntimeError(
                "Qualidade botânica: distribuição de folhagem insuficiente; "
                "exigidos 12 centros espaciais distintos e uma copa que ocupe "
                "pelo menos 12% da altura da árvore; encontrados "
                + str(len(set(leaf_centers)))
                + " centros e "
                + str(round(leaf_z_span, 3))
                + " unidades de altura."
            )
        minimum_leaf_groups = 15
        minimum_leaf_faces = 1_000
        if len(leaf_objects) < minimum_leaf_groups or leaf_faces < minimum_leaf_faces:
            raise RuntimeError(
                "Qualidade botânica: copa incompleta; exigidos pelo menos "
                + str(minimum_leaf_groups)
                + " grupos e "
                + str(minimum_leaf_faces)
                + " faces de folhagem; encontrados "
                + str(len(leaf_objects))
                + " grupos de folhas e "
                + str(leaf_faces)
                + " faces (déficit de "
                + str(max(0, minimum_leaf_faces - leaf_faces))
                + " faces). Não compense com triangulação ou folhas duplicadas."
            )
        individual_leaf_groups = sum(
            components >= 3 and leaf_components >= 3
            for components, leaf_components in
            (mesh_leaf_stats(obj) for obj in leaf_objects)
        )
        required_individual_groups = math.ceil(len(leaf_objects) * 0.8)
        if individual_leaf_groups < required_individual_groups:
            raise RuntimeError(
                "Qualidade botânica: grupos de folhagem devem conter pelo menos "
                "três folhas volumétricas individuais e alongadas (não "
                "esferas/rochas); grupos válidos "
                + str(individual_leaf_groups)
                + "/"
                + str(len(leaf_objects))
                + "."
            )
    elif expected_kind == "rock":
        rock_objects = [
            obj for obj in meshes if obj.name.startswith("Rock_")
        ]
        primary = bpy.data.objects.get("Rock_Main")
        rock_faces = sum(len(obj.data.polygons) for obj in rock_objects)
        if primary is None or primary.type != "MESH":
            raise RuntimeError(
                "Qualidade rochosa: falta uma malha principal chamada Rock_Main."
            )
        if (
            len(rock_objects) > 4
            or len(primary.data.polygons) < 40
            or len(primary.data.polygons) < rock_faces * 0.6
        ):
            raise RuntimeError(
                "Qualidade rochosa: a rocha singular deve ter um volume principal "
                "de pelo menos 40 faces, contendo 60% das faces rochosas, e no "
                "máximo três detalhes/apoios separados."
            )
        rock_mesh = bmesh.new()
        rock_mesh.from_mesh(primary.data)
        remaining_vertices = set(rock_mesh.verts)
        connected_components = 0
        while remaining_vertices:
            connected_components += 1
            pending_vertices = [remaining_vertices.pop()]
            while pending_vertices:
                vertex = pending_vertices.pop()
                for edge in vertex.link_edges:
                    neighbor = edge.other_vert(vertex)
                    if neighbor in remaining_vertices:
                        remaining_vertices.remove(neighbor)
                        pending_vertices.append(neighbor)
        rock_mesh.free()
        if connected_components != 1:
            raise RuntimeError(
                "Qualidade rochosa: Rock_Main deve ser um volume conectado; "
                "foram encontrados "
                + str(connected_components)
                + " componentes."
            )

    report = {{
        "objects": len(geometry),
        "meshes": len(meshes),
        "vertices": vertex_count,
        "faces": face_count,
        "nonmanifold_edges": nonmanifold_edges,
        "materials": len({{material.name for obj in meshes for material in obj.data.materials if material}}),
        "leaf_objects": len(leaf_objects),
        "branch_objects": len(branch_objects),
        "dimensions": [round(value, 4) for value in dimensions],
    }}
    if expected_kind in {{"plant", "tree"}} and nonmanifold_edges:
        raise RuntimeError(
            "Qualidade botânica: "
            + str(nonmanifold_edges)
            + " arestas não manifold; folhas e ramos devem ser malhas fechadas."
        )
    print("KRONOS_BLENDER_QA " + json.dumps(report), flush=True)
    return report

def export_model():
    extension = export_path.lower().rsplit(".", 1)[-1]
    if extension == "blend":
        return

    geometry = [
        obj for obj in bpy.context.scene.objects
        if obj.type in {{"MESH", "CURVE", "SURFACE", "FONT", "META"}}
    ]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in geometry:
        obj.select_set(True)
    if geometry:
        bpy.context.view_layer.objects.active = geometry[0]

    if extension == "fbx":
        bpy.ops.export_scene.fbx(
            filepath=export_path,
            use_selection=True,
            object_types={{"MESH", "EMPTY", "ARMATURE", "OTHER"}},
        )
    elif extension == "glb":
        bpy.ops.export_scene.gltf(
            filepath=export_path,
            export_format="GLB",
            use_selection=True,
        )
    elif extension == "obj":
        bpy.ops.wm.obj_export(
            filepath=export_path,
            export_selected_objects=True,
        )
    else:
        raise RuntimeError("Formato de exportação não suportado: ." + extension)

def _kronos_progress(label="Montando o modelo"):
    write_progress(label)
    print("KRONOS_BLENDER_STEP " + str(label), flush=True)
    if bpy.app.background:
        return
    geometry_objects = [
        obj for obj in bpy.context.scene.objects
        if obj.type in {{"MESH", "CURVE", "SURFACE", "FONT", "META"}}
    ]
    if geometry_objects:
        corners = [
            obj.matrix_world @ Vector(corner)
            for obj in geometry_objects
            for corner in obj.bound_box
        ]
        minimum = Vector(tuple(min(point[i] for point in corners) for i in range(3)))
        maximum = Vector(tuple(max(point[i] for point in corners) for i in range(3)))
        center = (minimum + maximum) * 0.5
        radius = max((maximum - minimum).length * 0.5, 1.0)
        view_rotation = Vector((1.8, -2.4, 1.5)).to_track_quat("Z", "Y")
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    region = area.spaces.active.region_3d
                    region.view_location = center
                    region.view_distance = radius * 1.8
                    region.view_rotation = view_rotation
                    region.view_perspective = "PERSP"
                    area.header_text_set("KRONOS | " + str(label)[:100])
    bpy.context.view_layer.update()
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    time.sleep(0.15)

try:
    write_status({{
        "status": "running",
        "process_id": os.getpid(),
        "background": bool(bpy.app.background),
    }})
    write_progress("Preparando a cena")
    print("KRONOS_BLENDER_STEP Preparando a cena", flush=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    runpy.run_path(
        source_path,
        run_name="__main__",
        init_globals={{
            "_kronos_progress": _kronos_progress,
            "mathutils": mathutils,
            "Vector": Vector,
            "Matrix": Matrix,
        }},
    )
    _kronos_progress("Modelo pronto; preparando luz e enquadramento")
    configure_scene()
    quality_report = validate_model()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.header_text_set(None)
    print("KRONOS_BLENDER_STEP Salvando o projeto", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("KRONOS_BLENDER_STEP Exportando e renderizando a prévia", flush=True)
    export_model()
    bpy.ops.render.render(write_still=True)
    write_status({{
        "status": "done",
        "process_id": os.getpid(),
        "background": bool(bpy.app.background),
        "quality": quality_report,
    }})
    print("KRONOS_BLENDER_DONE")
    try:
        bpy.ops.wm.quit_blender()
    except Exception:
        pass
except Exception as error:
    error_details = traceback.format_exc()
    print(error_details)
    write_status({{"status": "error", "error": error_details}})
    try:
        bpy.ops.wm.quit_blender()
    except Exception:
        pass
'''


def generate_blender_script(nome_script: str, descricao_tarefa: str) -> str:
    """Create, validate, save and preview a Blender model."""
    blender_executable = _find_blender_executable()
    if not blender_executable:
        return "Falha: Blender não encontrado. Instale-o ou adicione blender.exe ao PATH."

    requested_name = _safe_name(
        nome_script.removesuffix(".py").removesuffix(".blend")
    )
    try:
        selected_path = _choose_save_path(requested_name)
    except Exception as error:
        message = f"Falha ao abrir a janela para escolher onde salvar: {error}"
        print(f"[BLENDER][SALVAMENTO][ERRO] {message}", flush=True)
        return message
    if not selected_path:
        print("[BLENDER][SALVAMENTO] O usuário cancelou a escolha do local.", flush=True)
        return "Cancelado pelo usuário; nenhum projeto Blender foi criado."

    selected_path = os.path.abspath(selected_path)
    extension = os.path.splitext(selected_path)[1].lower()
    if extension not in BLENDER_SAVE_FORMATS:
        return "Falha: escolha um formato .blend, .glb, .fbx ou .obj."

    expected_kind = _detect_asset_kind(descricao_tarefa)
    visible = _should_show_blender()
    print(
        "[BLENDER][MODO] "
        + ("Execução visível." if visible else "Execução em segundo plano.")
        + " Os arquivos de trabalho serão temporários.",
        flush=True,
    )
    blend_path = (
        selected_path if extension == ".blend"
        else _companion_blend_path(selected_path)
    )
    render_path = _unique_preview_path(selected_path)
    source = ""
    last_output = ""
    used_procedural_fallback = False
    fallback_available = _supports_generic_tree_fallback(descricao_tarefa)
    total_attempts = MAX_SCRIPT_CORRECTIONS + 1 + int(fallback_available)

    with tempfile.TemporaryDirectory(prefix="kronos-blender-") as work_dir:
        source_path = os.path.join(work_dir, "model.py")
        runner_path = os.path.join(work_dir, "runner.py")
        status_path = os.path.join(work_dir, "status.json")
        progress_path = os.path.join(work_dir, "progress.json")
        for attempt in range(total_attempts):
            execution_succeeded = False
            process = None
            status = None
            try:
                if fallback_available and attempt == MAX_SCRIPT_CORRECTIONS + 1:
                    source = _build_botanical_source("tree", descricao_tarefa)
                    used_procedural_fallback = True
                    print(
                        "[BLENDER][FALLBACK][ARVORE] A IA não produziu uma "
                        "versão validável; executando a composição procedural "
                        "pré-validada. Detalhes específicos de espécie podem "
                        "não estar representados.",
                        flush=True,
                    )
                else:
                    source = _generate_source(
                        descricao_tarefa,
                        previous_source=source,
                        error_details=last_output if attempt else "",
                    )
                    print(
                        "[BLENDER][GERACAO] Fonte específica para o pedido "
                        "recebida e validada.",
                        flush=True,
                    )
                _validate_generated_source(source)
            except (RuntimeError, ValueError) as error:
                last_output = str(error)
                print(f"[BLENDER][VALIDACAO_DO_CODIGO][ERRO] {last_output}", flush=True)
                if attempt < total_attempts - 1:
                    continue
                break

            try:
                with open(source_path, "w", encoding="utf-8", newline="\n") as script_file:
                    script_file.write(source + "\n")
                runner = _build_runner(
                    source_path,
                    blend_path,
                    render_path,
                    selected_path,
                    status_path,
                    progress_path,
                    visible,
                    expected_kind,
                )
                with open(runner_path, "w", encoding="utf-8", newline="\n") as runner_file:
                    runner_file.write(runner)
            except OSError as error:
                return f"Falha ao preparar os arquivos temporários do Blender: {error}"

            try:
                print(
                    f"[BLENDER][TESTE] Execução {attempt + 1}/"
                    f"{total_attempts} no Blender {os.path.basename(blender_executable)}.",
                    flush=True,
                )
                if os.path.exists(status_path):
                    os.remove(status_path)
                if os.path.exists(progress_path):
                    os.remove(progress_path)
                command = [blender_executable]
                if not visible:
                    command.append("--background")
                command.extend(
                    [
                        "--factory-startup",
                        "--python",
                        runner_path,
                    ]
                )
                log_path = os.path.join(work_dir, "blender.log")
                with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
                    process = subprocess.Popen(
                        command,
                        cwd=(
                            os.path.dirname(blend_path)
                            if visible
                            else work_dir
                        ),
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                    )
                    status, process_error, forced_cleanup = (
                        _monitor_blender_process(
                            process,
                            status_path,
                            progress_path,
                            BLENDER_TIMEOUT_SECONDS,
                        )
                    )
                if forced_cleanup:
                    print(
                        "[BLENDER][PROCESSO][AVISO] O processo não encerrou após "
                        "registrar o estado terminal e precisou de encerramento "
                        "forçado.",
                        flush=True,
                    )
                if status and status.get("status") == "done":
                    execution_succeeded = True
                    last_output = ""
                elif status and status.get("status") == "error":
                    last_output = str(
                        status.get("error", "Erro não detalhado pelo Blender.")
                    )
                else:
                    last_output = process_error
                if not execution_succeeded and os.path.isfile(log_path):
                    blender_log = _read_text_tail(log_path)
                    if blender_log:
                        last_output = (
                            last_output
                            + "\nDiagnóstico do processo Blender:\n"
                            + blender_log[-8000:]
                        )
            except subprocess.TimeoutExpired as error:
                if process is not None:
                    _stop_process_tree(process)
                last_output = (
                    f"Blender excedeu o limite de {BLENDER_TIMEOUT_SECONDS} segundos. "
                    f"{error}"
                )
            except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
                if process is not None:
                    _stop_process_tree(process)
                last_output = f"Falha ao iniciar ou ler o resultado do Blender: {error}"

            if execution_succeeded:
                try:
                    if not os.path.isfile(blend_path) or os.path.getsize(blend_path) == 0:
                        raise RuntimeError("O arquivo .blend não foi salvo corretamente.")
                    if extension != ".blend" and (
                        not os.path.isfile(selected_path)
                        or os.path.getsize(selected_path) == 0
                    ):
                        raise RuntimeError(
                            f"A exportação {extension} não foi criada ou está vazia."
                        )
                    reopened_report = _validate_saved_project(
                        blender_executable,
                        blend_path,
                        selected_path if extension != ".blend" else "",
                        extension if extension != ".blend" else "",
                        expected_kind,
                        work_dir,
                    )
                    render_report = _inspect_render(render_path)
                    if not os.path.isfile(render_path) or os.path.getsize(render_path) == 0:
                        raise RuntimeError("O render da prévia não foi criado.")
                    print(
                        "[BLENDER][QA][OK] "
                        + json.dumps(
                            {
                                "scene": status.get("quality", {}),
                                "reopened_project": reopened_report,
                                "render": render_report,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    print(
                        "[BLENDER][OK] Geometria, materiais, projeto reaberto"
                        + (
                            ", separação de folhas e exportação reimportada"
                            if expected_kind == "tree" and extension != ".blend"
                            else ", separação de folhas"
                            if expected_kind == "tree"
                            else ", exportação reimportada"
                            if extension != ".blend"
                            else ""
                        )
                        + " e render inspecionados.",
                        flush=True,
                    )
                    if extension == ".blend":
                        if used_procedural_fallback:
                            return (
                                "Modelo criado e validado com composição procedural "
                                "de segurança; a geração por IA falhou e detalhes "
                                "específicos de espécie podem não estar representados. "
                                f"Projeto: {blend_path}. Prévia: {render_path}."
                            )
                        return (
                            f"Modelo criado e validado. Projeto: {blend_path}. "
                            f"Prévia: {render_path}."
                        )
                    if used_procedural_fallback:
                        return (
                            "Modelo exportado e reimportado com composição procedural "
                            "de segurança; a geração por IA falhou e detalhes "
                            "específicos de espécie podem não estar representados. "
                            f"Arquivo: {selected_path}. Projeto editável: {blend_path}. "
                            f"Prévia: {render_path}."
                        )
                    return (
                        f"Modelo exportado e reimportado: {selected_path}. "
                        f"Projeto editável: {blend_path}. Prévia: {render_path}."
                    )
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    last_output = str(error)

            if not last_output:
                last_output = "Blender encerrou sem confirmar as verificações de qualidade."
            print(
                f"[BLENDER][ERRO][QA/EXECUCAO] Tentativa {attempt + 1}: "
                f"{last_output[-5000:]}",
                flush=True,
            )
            if attempt < MAX_SCRIPT_CORRECTIONS:
                print(
                    "[BLENDER][CORRECAO] O diagnóstico específico será enviado ao "
                    "gerador para corrigir apenas a causa identificada.",
                    flush=True,
                )

    return (
        "Falha: o modelo não passou na execução e nas verificações do Blender "
        f"após {MAX_SCRIPT_CORRECTIONS} correções"
        + (" e na composição procedural de segurança" if fallback_available else "")
        + f". Erro final: {last_output[-3000:]}"
    )


def blender_render_background(arquivo_blend: str) -> str:
    """Render an existing Blender project in background and report completion."""
    blend_path = (
        os.path.abspath(arquivo_blend)
        if os.path.isabs(arquivo_blend)
        else os.path.abspath(os.path.join(BASE_DIR, arquivo_blend))
    )
    if not os.path.isfile(blend_path):
        return f"Falha: arquivo Blender não encontrado: {blend_path}"

    executable = _find_blender_executable()
    if not executable:
        return "Falha: Blender não encontrado. Instale-o ou adicione blender.exe ao PATH."

    stem = os.path.splitext(blend_path)[0]
    render_path = f"{stem}_render"
    suffix = 2
    while os.path.exists(f"{render_path}0001.png"):
        render_path = f"{stem}_render_{suffix}"
        suffix += 1
    try:
        result = subprocess.run(
            [
                executable,
                "--background",
                blend_path,
                "--render-output",
                render_path,
                "--render-frame",
                "1",
            ],
            cwd=os.path.dirname(blend_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BLENDER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "Falha: a renderização excedeu o limite de 300 segundos."
    except OSError as error:
        return f"Falha ao iniciar o Blender: {error}"

    output_file = f"{render_path}0001.png"
    if result.returncode != 0 or not os.path.isfile(output_file):
        details = ((result.stdout or "") + "\n" + (result.stderr or ""))[-3000:]
        return f"Falha ao renderizar o projeto Blender. {details}"
    return f"Renderização concluída: {output_file}."