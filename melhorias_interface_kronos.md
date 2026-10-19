# PROPOSTA DE MELHORIAS OPERACIONAIS E VISUAIS - KRONOS HUD
Hardware Alvo: AMD Ryzen 5 5600GT (6c/12t) | 16 GB DDR4 | Gráficos Integrados Radeon Vega

## DIRETRIZ FUNDAMENTAL: EFICIÊNCIA ABSOLUTA (ZERO GASTO SUPERFLUO)
Projetado especificamente para rodar com fluidez absoluta em vídeo integrado, consumindo o mínimo de memória e ciclos de CPU, garantindo que o Blender e o Roblox Studio tenham prioridade máxima de recursos.

---

### 1. ARQUITETURA DE INTERFACE (GUI LEVE)
- **Framework Recomendado:** PyQt6 / PySide6 com aceleração por software nativo ou CustomTkinter / Webview leve (Tauri/PyWebView) com aceleração desligada para não disputar a VRAM compartilhada.
- **Renderização Econômica:** 60 FPS fixos com modo ocioso caindo para 15 FPS quando a interface estiver estática (reduz o uso da iGPU a menos de 1%).
- **Tema:** Dark Cyberpunk Minimalista (fundo `#0d0f12`, acentos em ciano/âmbar `#00f0ff` / `#ffaa00`), evitando blurs pesados (Mica/Acrylic desativados ou falsificados com texturas sólidas pré-renderizadas para economizar shaders).

---

### 2. PAINEL DE TELEMETRIA EM TEMPO REAL
- **Consumo de Hardware em HUD:**
  - Medidor de uso de RAM (mantendo KRONOS abaixo de 180MB de footprint).
  - Temperatura e Clock do Ryzen 5 5600GT via `psutil` ou WMI sem sobrecarga de polling (taxa de amostragem: 2.5s).
  - Alerta de gargalo de VRAM compartilhada durante sessões do Blender/Roblox.
- **Status do Agente:** Indicador visual discreto de modos: `IDLE`, `ANALISANDO TELA`, `EXECUTANDO FERRAMENTA`, `BRAVO`.

---

### 3. INTERAÇÃO E VISÃO OTIMIZADA
- **Captura Seletiva sob Demanda:** Em vez de monitoramento contínuo em vídeo (que fritaria a APU), manter o gatilho sob demanda que já implementamos com Pillow/MSS reduzindo para JPEG 85% em buffer de memória (sem I/O de disco).
- **Atalhos Globais (Hotkeys):**
  - `Ctrl + Shift + K`: Abre o prompt flutuante de comando rápido estilo Spotlight.
  - `Ctrl + Shift + S`: Tira screenshot da janela ativa e envia direto para análise visual.

---

### 4. GERENCIAMENTO DE ESTADO E LOGS
- Log local rotativo em arquivo SQLite leve (`kronos_memory.db`) para reter contexto sem explodir consumo de memória.
- Histórico visual das últimas 5 capturas em miniaturas compactadas (128x72) para depuração instantânea sem impacto de disco.
