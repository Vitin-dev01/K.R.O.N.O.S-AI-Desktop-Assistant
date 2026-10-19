"""Non-destructive editing of an existing Blender project."""

from __future__ import annotations

import json
import os
import glob
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog

from blender_automation import (
    BLENDER_TIMEOUT_SECONDS,
    MAX_SCRIPT_CORRECTIONS,
    _find_blender_executable,
    _generate_source,
    _inspect_render,
    _validate_generated_source,
    _validate_saved_project,
    blender_render_background,
)


def _choose_project_to_edit() -> str:
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        return filedialog.askopenfilename(
            parent=root,
            title="Selecione o projeto Blender que deseja editar",
            filetypes=[("Blender Project", "*.blend")],
        )
    finally:
        root.destroy()


def _choose_edited_project_path(source_path: str) -> str:
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        directory = os.path.dirname(source_path)
        filename = os.path.splitext(os.path.basename(source_path))[0]
        return filedialog.asksaveasfilename(
            parent=root,
            title="Salvar uma cópia editada do projeto",
            initialdir=directory,
            initialfile=f"{filename}_edited.blend",
            defaultextension=".blend",
            filetypes=[("Blender Project", "*.blend")],
        )
    finally:
        root.destroy()


def _build_inspector() -> str:
    return '''import bpy
import json
import math

items = []
for obj in bpy.context.scene.objects:
    if len(items) >= 200:
        break
    items.append({
        "name": obj.name,
        "type": obj.type,
        "location": [round(float(value), 4) for value in obj.location],
        "dimensions": [round(float(value), 4) for value in obj.dimensions],
        "hidden_viewport": bool(obj.hide_viewport),
        "hidden_render": bool(obj.hide_render),
        "collections": sorted(collection.name for collection in obj.users_collection),
        "materials": [
            material.name if material else None
            for material in getattr(obj.data, "materials", [])
        ],
        "modifiers": [
            {"name": modifier.name, "type": modifier.type}
            for modifier in obj.modifiers
        ],
        "vertices": len(obj.data.vertices) if obj.type == "MESH" else None,
        "faces": len(obj.data.polygons) if obj.type == "MESH" else None,
    })

report = {
    "filepath": bpy.data.filepath,
    "scene": bpy.context.scene.name,
    "active_object": (
        bpy.context.view_layer.objects.active.name
        if bpy.context.view_layer.objects.active
        else None
    ),
    "object_count": len(bpy.context.scene.objects),
    "objects_reported": items,
    "truncated": len(bpy.context.scene.objects) > len(items),
    "materials": sorted(material.name for material in bpy.data.materials),
    "collections": sorted(collection.name for collection in bpy.data.collections),
    "blender_version": bpy.app.version_string,
}
print("KRONOS_PROJECT_INSPECTION " + json.dumps(report))
'''


def _inspect_project(blender_executable: str, source_path: str, work_dir: str) -> dict:
    inspector_path = os.path.join(work_dir, "inspect_project.py")
    with open(inspector_path, "w", encoding="utf-8", newline="\n") as inspector_file:
        inspector_file.write(_build_inspector())
    try:
        result = subprocess.run(
            [
                blender_executable,
                "--background",
                source_path,
                "--python",
                inspector_path,
            ],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Não foi possível inspecionar o projeto: {error}") from error
    report_line = next(
        (
            line
            for line in result.stdout.splitlines()
            if line.startswith("KRONOS_PROJECT_INSPECTION ")
        ),
        None,
    )
    if result.returncode != 0 or report_line is None:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "A leitura do projeto Blender falhou: "
            + (detail[-4000:] or f"código de saída {result.returncode}")
        )
    try:
        return json.loads(report_line.partition(" ")[2])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Relatório da cena ilegível: {error}") from error


def _build_edit_runner(source_path: str, output_path: str) -> str:
    return f'''import bpy
import json
import math
import runpy
import traceback

source_path = {source_path!r}
output_path = {output_path!r}

def snapshot():
    objects = []
    for obj in bpy.context.scene.objects:
        material_values = []
        for material in getattr(obj.data, "materials", []):
            if material and hasattr(material, "diffuse_color"):
                material_values.append(
                    (material.name, tuple(round(float(value), 5) for value in material.diffuse_color))
                )
        objects.append((
            obj.name,
            obj.type,
            tuple(round(float(value), 5) for value in obj.location),
            tuple(round(float(value), 5) for value in obj.dimensions),
            bool(obj.hide_viewport),
            bool(obj.hide_render),
            tuple(modifier.type for modifier in obj.modifiers),
            len(obj.data.vertices) if obj.type == "MESH" else 0,
            len(obj.data.polygons) if obj.type == "MESH" else 0,
            tuple(material_values),
        ))
    return tuple(sorted(objects))

try:
    before = snapshot()
    runpy.run_path(
        source_path,
        run_name="__main__",
        init_globals={{
            "_kronos_progress": lambda label: print("KRONOS_EDIT_STEP " + str(label)),
        }},
    )
    bpy.context.view_layer.update()
    after = snapshot()
    if before == after:
        raise RuntimeError(
            "A cena não apresentou nenhuma alteração observável; "
            "o projeto não foi salvo como uma edição concluída."
        )

    meshes = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH"
    ]
    if not meshes:
        raise RuntimeError("A edição removeu todas as malhas da cena.")
    invalid_meshes = []
    for obj in meshes:
        if not obj.data.vertices or not obj.data.polygons:
            invalid_meshes.append(obj.name)
            continue
        if any(
            not math.isfinite(float(component))
            for vertex in obj.data.vertices
            for component in vertex.co
        ):
            invalid_meshes.append(obj.name)
    if invalid_meshes:
        raise RuntimeError(
            "Malhas vazias ou com coordenadas inválidas após a edição: "
            + ", ".join(invalid_meshes[:10])
        )

    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    print("KRONOS_EDIT_DONE " + json.dumps({{
        "objects": len(bpy.context.scene.objects),
        "meshes": len(meshes),
        "faces": sum(len(obj.data.polygons) for obj in meshes),
        "changed_objects": len(set(before) ^ set(after)),
    }}))
except Exception:
    traceback.print_exc()
    raise
'''


def _unique_backup_path(path: str) -> str:
    candidate = path + ".bak"
    suffix = 2
    while os.path.exists(candidate):
        candidate = f"{path}.bak.{suffix}"
        suffix += 1
    return candidate


def edit_blender_project(descricao_tarefa: str) -> str:
    """Inspect an existing .blend and apply a requested edit to a separate copy."""
    blender_executable = _find_blender_executable()
    if not blender_executable:
        return "Falha: Blender não encontrado."
    try:
        source_path = _choose_project_to_edit()
    except Exception as error:
        return f"Falha ao selecionar o projeto Blender: {error}"
    if not source_path:
        return "Cancelado pelo usuário; nenhum projeto foi alterado."
    source_path = os.path.abspath(source_path)
    if os.path.splitext(source_path)[1].casefold() != ".blend":
        return "Falha: selecione um arquivo .blend existente."
    if not os.path.isfile(source_path):
        return "Falha: o arquivo .blend selecionado não existe."

    try:
        output_path = _choose_edited_project_path(source_path)
    except Exception as error:
        return f"Falha ao escolher o destino da edição: {error}"
    if not output_path:
        return "Cancelado pelo usuário; o projeto original permanece intacto."
    output_path = os.path.abspath(output_path)
    if os.path.splitext(output_path)[1].casefold() != ".blend":
        return "Falha: o destino da edição deve terminar em .blend."
    if os.path.normcase(source_path) == os.path.normcase(output_path):
        return (
            "Falha: escolha outro destino. A automação não sobrescreve "
            "o arquivo original durante uma edição."
        )
    if os.path.dirname(output_path) and not os.path.isdir(os.path.dirname(output_path)):
        return "Falha: a pasta de destino não existe."

    backup_path = None
    output_touched = False

    with tempfile.TemporaryDirectory(prefix="kronos-blender-edit-") as work_dir:
        try:
            scene_report = _inspect_project(
                blender_executable,
                source_path,
                work_dir,
            )
        except RuntimeError as error:
            return f"Falha ao inspecionar o projeto existente: {error}"

        edit_request = (
            "EDITAR O PROJETO EXISTENTE, NÃO CRIAR UMA CENA NOVA.\n"
            "A fonte Blender abre o projeto e preserva o conteúdo atual. "
            "Implemente apenas a alteração pedida, reaproveitando os objetos, "
            "coleções, materiais e modificadores existentes quando apropriado. "
            "Não limpe nem recrie a cena inteira. Se a tarefa exigir remover "
            "partes, remova somente as partes explicitamente solicitadas. "
            "Use nomes dos objetos reais da inspeção abaixo; não invente "
            "objetos como se estivessem presentes.\n"
            f"Pedido do usuário: {descricao_tarefa}\n"
            "Estado confirmado da cena salva:\n"
            + json.dumps(scene_report, ensure_ascii=False)
        )
        last_error = ""
        script = ""
        for attempt in range(MAX_SCRIPT_CORRECTIONS + 1):
            try:
                script = _generate_source(
                    edit_request,
                    previous_source=script,
                    error_details=last_error if attempt else "",
                )
                _validate_generated_source(script)
            except (RuntimeError, ValueError) as error:
                last_error = str(error)
                if attempt == MAX_SCRIPT_CORRECTIONS:
                    break
                continue

            script_path = os.path.join(work_dir, "edit.py")
            runner_path = os.path.join(work_dir, "edit_runner.py")
            try:
                with open(script_path, "w", encoding="utf-8", newline="\n") as script_file:
                    script_file.write(script + "\n")
                with open(runner_path, "w", encoding="utf-8", newline="\n") as runner_file:
                    runner_file.write(_build_edit_runner(script_path, output_path))
                if os.path.exists(output_path) and backup_path is None:
                    backup_path = _unique_backup_path(output_path)
                    shutil.copy2(output_path, backup_path)
                output_touched = True
                shutil.copy2(source_path, output_path)
                result = subprocess.run(
                    [
                        blender_executable,
                        "--background",
                        output_path,
                        "--python",
                        runner_path,
                    ],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=BLENDER_TIMEOUT_SECONDS,
                    check=False,
                )
                done_line = next(
                    (
                        line
                        for line in result.stdout.splitlines()
                        if line.startswith("KRONOS_EDIT_DONE ")
                    ),
                    None,
                )
                if result.returncode != 0 or done_line is None:
                    last_error = (result.stderr or result.stdout or "").strip()[-5000:]
                    if not last_error:
                        last_error = (
                            "O Blender encerrou sem confirmar a validação da edição."
                        )
                    continue
                try:
                    edit_report = json.loads(done_line.partition(" ")[2])
                    reopened_report = _validate_saved_project(
                        blender_executable,
                        output_path,
                        "",
                        "",
                        "generic",
                        work_dir,
                        require_mesh_materials=False,
                    )
                except (json.JSONDecodeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    last_error = f"QA do arquivo editado falhou: {error}"
                    continue

                output_directory = os.path.dirname(output_path)
                files_before_render = set(os.listdir(output_directory))
                preview_result = ""
                preview_path = ""
                preview_report = None
                try:
                    preview_result = blender_render_background(output_path)
                    new_previews = [
                        path
                        for path in glob.glob(
                            os.path.join(
                                output_directory,
                                os.path.splitext(os.path.basename(output_path))[0]
                                + "_render*.png",
                            )
                        )
                        if os.path.basename(path) not in files_before_render
                    ]
                    if new_previews:
                        preview_path = max(new_previews, key=os.path.getmtime)
                        preview_report = _inspect_render(preview_path)
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    preview_result = str(error)
                print(
                    "[BLENDER][EDIT][QA][OK] "
                    + json.dumps(
                        {
                            "edited": edit_report,
                            "reopened": reopened_report,
                            "preview": preview_report,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                result_text = (
                    f"Projeto editado e reaberto com validação: {output_path}. "
                )
                if preview_path:
                    result_text += f" Prévia: {preview_path}."
                if backup_path:
                    result_text += f" Cópia anterior do destino: {backup_path}."
                if not preview_path:
                    result_text += f" Aviso: a prévia não foi confirmada ({preview_result})."
                return result_text
            except (OSError, subprocess.TimeoutExpired) as error:
                last_error = f"Falha ao executar a edição no Blender: {error}"

    if output_touched and os.path.exists(output_path):
        try:
            if backup_path:
                shutil.copy2(backup_path, output_path)
            else:
                os.remove(output_path)
        except OSError as error:
            last_error += f" Falha ao restaurar/remover a saída parcial: {error}"
    return (
        "Falha: a edição não passou pela execução e pelas validações. "
        f"O projeto original permaneceu intacto. Diagnóstico: {last_error[-3000:]}"
    )
