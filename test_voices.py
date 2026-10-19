import subprocess

# Comando PowerShell limpo para listar as vozes
ps_script = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($v in $synth.GetInstalledVoices()) {
    [Console]::WriteLine($v.VoiceInfo.Name + " --- " + $v.VoiceInfo.Culture + " --- " + $v.VoiceInfo.Gender)
}
"""

res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
print("\n--- VOZES ENCONTRADAS NO SEU WINDOWS 11 ---")
print(res.stdout)
print("-------------------------------------------\n")