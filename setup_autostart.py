import os

def setup_startup():
    # Pasta oficial de inicialização do Windows
    startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    pythonw_path = os.path.join(project_dir, ".venv", "Scripts", "pythonw.exe")
    app_py_path = os.path.join(project_dir, "app.py")
    
    vbs_path = os.path.join(startup_dir, "KRONOS.vbs")
    
    # Cria o inicializador silencioso VBScript (sem janela preta de DOS)
    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{project_dir}"
WshShell.Run """{pythonw_path}""" & " """{app_py_path}""", 0, False
'''
    
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)
        
    print(f"\n[SUCESSO] KRONOS configurado para iniciar automaticamente com o Windows 11!")
    print(f"Arquivo gerado em: {vbs_path}")

if __name__ == "__main__":
    setup_startup()