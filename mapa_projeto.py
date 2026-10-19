import ast
import os

IGNORAR = {"venv", ".venv", "env", "node_modules", "__pycache__", ".git", "dist", "build"}
EXTENSOES = {".py", ".js", ".html", ".css", ".json"}

saida = []

for pasta, subpastas, arquivos in os.walk("."):
    subpastas[:] = [p for p in subpastas if p not in IGNORAR]
    for nome in sorted(arquivos):
        ext = os.path.splitext(nome)[1].lower()
        if ext not in EXTENSOES or nome == "mapa_projeto.py":
            continue
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                codigo = f.read()
        except Exception as e:
            saida.append(f"{caminho}: erro ao ler ({e})")
            continue

        linhas = codigo.count("\n") + 1
        saida.append(f"\n=== {caminho} ({linhas} linhas) ===")

        if ext == ".py":
            try:
                arvore = ast.parse(codigo)
            except SyntaxError as e:
                saida.append(f"  erro de sintaxe: {e}")
                continue
            imports = set()
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    for a in no.names:
                        imports.add(a.name.split(".")[0])
                elif isinstance(no, ast.ImportFrom) and no.module:
                    imports.add(no.module.split(".")[0])
            saida.append("  imports: " + ", ".join(sorted(imports)))
            for no in arvore.body:
                if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    saida.append(f"  def {no.name}()  [linha {no.lineno}]")
                elif isinstance(no, ast.ClassDef):
                    saida.append(f"  class {no.name}  [linha {no.lineno}]")
                    for m in no.body:
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            saida.append(f"      def {m.name}()")

texto = "\n".join(saida)
with open("mapa.txt", "w", encoding="utf-8") as f:
    f.write(texto)
print(texto)
print("\nPronto! Também salvei tudo em mapa.txt")