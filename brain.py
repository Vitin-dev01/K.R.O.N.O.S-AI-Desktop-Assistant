import re
import time
import hashlib
import unicodedata
from datetime import datetime
from google import genai
from google.genai import types
from config import key_rotator, MODEL_ROUTER
from tools import TOOL_REGISTRY, TOOLS_DEFINITIONS
from memory import get_all_facts

KRONOS_SYSTEM_PROMPT = """Você é KRONOS: uma inteligência artificial de elite que opera neste computador.

PERSONALIDADE E VOZ:
- Demonstre confiança serena, inteligência afiada e arrogância elegante, com ironia seca ocasional.
- Seja incisivo e marcante sem humilhar o usuário: critique ideias ou problemas, nunca a pessoa.
- Não use bordões repetitivos, ameaças, elogios gratuitos ou superioridade teatral.
- Fale em português brasileiro natural, com frases curtas e ritmo conversacional; evite formalidade robótica e gírias forçadas.
- Quando algo falhar, reconheça o limite com clareza e diga o que foi ou não verificado.

MEMÓRIA E CONTEXTO OPERACIONAL DO SISTEMA:
{MEMORIA_USUARIO}

SEU ARSENAL DE FERRAMENTAS:
1. 'generate_roblox_script': Cria ou reutiliza Parts e Scripts na place aberta, suporta mecanismos interativos (portas, elevadores, botões, armadilhas, combate, NPCs, efeitos, UIs), salva e testa.
2. 'play_roblox_studio': Aperta F5 no Roblox Studio automaticamente para dar Play no jogo.
3. 'blender_render_background': Renderizar arquivo .blend silenciosamente em background.
4. 'generate_blender_script': Criar modelos 3D novos no Blender com geometria de qualidade, proporções corretas, materiais, salvar e renderizar prévia.
5. 'edit_blender_project': Inspecionar um .blend salvo existente e editar uma cópia aplicando modificadores, extrusões, bevels ou ajustes cirúrgicos.
6. 'analyze_screen': Olhar a tela para depurar código, inspecionar Blender ou inspecionar Roblox Studio.
7. 'write_file', 'read_file', 'list_directory': Manipular arquivos e projetos no workspace.
8. 'get_full_telemetry': Monitorar telemetria real (CPU, RAM, Disco, Rede, Clima).
9. 'set_volume', 'media_control', 'play_music', 'send_notification': Controle de ambiente e som no Windows 11.
10. 'open_app', 'close_app', 'open_website', 'search_google': Gerenciamento do sistema operacional.

DIRETRIZES DE RACIOCÍNIO E EXECUÇÃO:
- Raciocine antes de agir. Decomponha tarefas complexas em etapas lógicas.
- Se a tarefa exigir múltiplas etapas (ex: inspecionar arquivos -> gerar modelo 3D -> salvar relatório), invoque as ferramentas na sequência correta.
- Nunca devolva código Luau ou Python direto na fala! Utilize as ferramentas especializadas para executar no computador.
- Ao modelar no Blender ('generate_blender_script'), forneça detalhes completos de estilo (low-poly, estilizado ou realista), geometria, peças e materiais do objeto pedido. Nunca substitua por um modelo padrão ou genérico.
- Ao editar um projeto Blender existente ('edit_blender_project'), respeite os objetos já existentes e modifique apenas o que foi solicitado.
- No Roblox Studio, descreva a mecânica com precisão (lógica de ativação, variáveis, serviços do Roblox como TweenService ou Debris).
- Diferencie declarações de sucesso comprovado de ações tentadas: baseie suas respostas nos dados e relatórios reais retornados pelas ferramentas.
- Se o pedido não exigir nenhuma ferramenta, apenas converse; nunca diga que executou algo que você não executou.
- Antes de qualquer ação destrutiva (apagar, sobrescrever ou fechar algo importante), confirme com o usuário caso o pedido seja ambíguo.
- Antes de dizer que não consegue acessar algo, tente usar a ferramenta correspondente e relate o resultado real que ela devolveu; nunca presuma uma limitação sem testar.

FORMATO OBRIGATÓRIO:
===ESTADO===
IDLE (ou BRAVO)
===PENSAMENTO===
(Uma avaliação operacional breve, sem expor raciocínio passo a passo.)
===FALA===
(Resposta natural, concisa e fiel às evidências.)
"""

MAX_TOOL_ROUNDS = 4
MAX_TOOL_CALLS_PER_TURN = 8
# True = o Kronos sempre recebe as ferramentas e decide sozinho se usa.
# Se notar que ele chama ferramenta sem precisar, mude para False.
SEMPRE_COM_FERRAMENTAS = True

DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

class KronosBrain:
    def __init__(self):
        self.chat_history = []

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.casefold())
        return "".join(
            character for character in normalized
            if not unicodedata.combining(character)
        )
    
    @staticmethod
    def _trim_history(history, limit: int = 20):
        """Corta o histórico sem deixar resposta de ferramenta órfã no início."""
        if len(history) <= limit:
            return history
        trimmed = list(history[-limit:])
        while trimmed:
            first = trimmed[0]
            parts = getattr(first, "parts", None) or []
            is_plain_user = first.role == "user" and not any(
                getattr(part, "function_response", None) for part in parts
            )
            if is_plain_user:
                break
            trimmed = trimmed[1:]
        return trimmed
    
    def _is_telemetry_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        system_terms = (
            "pc", "computador", "maquina", "sistema", "cpu", "processador",
            "ram", "memoria", "disco", "armazenamento", "internet", "rede",
            "telemetria", "hardware", "clima", "tempo",
        )
        inspection_terms = (
            "como", "qual", "quanto", "ver", "veja", "olha", "olhe",
            "mostra", "mostre", "checa", "cheque", "verifica", "verifique",
            "status", "uso", "consumo", "temperatura", "desempenho",
            "monitorar", "monitoramento", "funcionando", "bem",
        )
        has_system_term = any(
            re.search(rf"\b{re.escape(term)}\b", normalized)
            for term in system_terms
        )
        has_inspection_term = any(
            re.search(rf"\b{re.escape(term)}\b", normalized)
            for term in inspection_terms
        )
        return has_system_term and has_inspection_term

    def _is_tool_intent(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        action_terms = (
            "ve", "veja", "olha", "olhe", "abra", "abrir", "abre", "feche",
            "fechar", "fecha", "crie", "criar", "cria", "construa",
            "construir", "modele", "modelar", "modelo", "salve", "salvar",
            "ajuste", "ajustar", "mude", "mudar", "altere", "alterar",
            "ative", "ativar", "desative", "desativar", "ligue", "desligue",
            "pesquise", "pesquisar", "busque", "buscar", "toque", "tocar",
            "reproduza", "teste", "testar", "corrija", "corrigir", "analise",
            "analisar", "mostre", "mostrar", "verifique", "verificar", "copie",
            "copiar", "leia", "ler", "inspecione", "inspecionar", "create",
            "build", "open", "play", "test", "show",
        )
        tool_terms = (
            "volume", "musica", "youtube", "roblox", "luau", "script",
            "blender", "render", "3d", "arquivo", "pasta", "diretorio",
            "clipboard", "area de transferencia", "tela", "screenshot",
            "site", "navegador", "aplicativo", "calculadora", "chrome",
            "discord", "notificacao", "modo gamer", "modo padrao",
            "computador", "maquina", "sistema", "pc", "cpu", "processador",
            "ram", "memoria", "disco", "armazenamento", "internet", "rede",
            "telemetria", "hardware", "clima", "tempo",
        )
        has_action = any(
            re.search(rf"\b{re.escape(term)}\b", normalized)
            for term in action_terms
        )
        has_tool_target = any(
            re.search(rf"\b{re.escape(term)}\b", normalized)
            for term in tool_terms
        )
        return self._is_telemetry_request(text) or (has_action and has_tool_target)

    @staticmethod
    def _format_telemetry_response(telemetry: dict, user_text: str) -> str:
        response = (
            f"Estado atual: CPU em {telemetry['cpu_percent']}%; "
            f"RAM em {telemetry['ram_percent']}% "
            f"({telemetry['ram_used_gb']} de {telemetry['ram_total_gb']} GB); "
            f"disco C: em {telemetry['disk_percent']}% "
            f"({telemetry['disk_free_gb']} GB livres); "
            f"rede: {telemetry['net_down_kbs']} KB/s de download e "
            f"{telemetry['net_up_kbs']} KB/s de envio. "
            f"Modo de energia: {telemetry['active_mode']}."
        )
        normalized = KronosBrain._normalize_text(user_text)
        if "temperatura" in normalized and any(
            term in normalized for term in ("cpu", "processador", "gpu", "placa de video")
        ):
            response += (
                " A leitura disponível não mede a temperatura física dos "
                "componentes; informa apenas o uso da CPU."
            )
        if "clima" in normalized or re.search(r"\btempo\b", normalized):
            weather = telemetry["weather"]
            response += (
                f" Clima em {weather['cidade']}: {weather['temperatura']}, "
                f"{weather['condicao']}, umidade de {weather['umidade']}."
            )
        return response

    def _is_roblox_build_request(self, text: str) -> bool:
        normalized = unicodedata.normalize("NFKD", text.lower())
        normalized = "".join(
            character for character in normalized
            if not unicodedata.combining(character)
        )
        has_roblox_context = "roblox" in normalized or "luau" in normalized
        has_studio_context = (
            "studio" in normalized
            and any(word in normalized for word in ("part", "script", "place"))
        )
        if not has_roblox_context and not has_studio_context:
            return False

        build_actions = (
            "crie", "criar", "cria", "adicione", "adicionar", "coloque",
            "colocar", "insira", "inserir", "modifique", "modificar",
            "altere", "alterar", "mude", "mudar", "construa", "construir",
            "faca", "fazer", "implemente", "implementar", "automatize",
            "automatizar", "gere", "gerar", "edite", "editar", "delete",
            "deletar", "remova", "remover", "mexa", "mexer", "ajuste",
            "ajustar", "configure", "configurar", "mova", "mover", "corrija",
            "corrigir", "arrume", "arrumar", "atualize", "atualizar", "create",
            "add", "insert", "modify", "edit", "update", "build", "make",
            "move", "delete", "fix",
        )
        return any(
            re.search(rf"\b{re.escape(action)}\b", normalized)
            for action in build_actions
        )

    def _is_blender_build_request(self, text: str) -> bool:
        normalized = unicodedata.normalize("NFKD", text.lower())
        normalized = "".join(
            character for character in normalized
            if not unicodedata.combining(character)
        )
        has_blender_context = "blender" in normalized or bool(
            re.search(r"\b(3d|3-d|three[\s-]?dimensional)\b", normalized)
        )
        has_model_context = any(
            re.search(rf"\b{re.escape(term)}\b", normalized)
            for term in (
                "modelo", "modelagem", "modelar", "modele", "modela",
                "objeto", "asset", "malha", "mesh", "render",
                "arvore", "tree", "planta", "plant", "flor", "flower",
                "cacto", "cactus", "samambaia", "fern", "suculenta",
                "succulent", "palmeira", "palm", "folhagem", "personagem",
                "casa 3d", "carro 3d", "predio 3d", "robo 3d",
            )
        )
        has_explicit_modeling_action = any(
            re.search(rf"\b{re.escape(action)}\b", normalized)
            for action in ("modele", "modelar", "modela", "model", "sculpt")
        )
        if (
            not has_blender_context
            and not has_model_context
            and not has_explicit_modeling_action
        ):
            return False
        build_actions = (
            "crie", "criar", "cria", "modele", "modelar", "modela",
            "adicione", "adicionar", "construa", "construir", "gere",
            "gerar", "faca", "fazer", "produza", "produzir", "monte",
            "montar", "edite", "editar", "modifique", "modificar",
            "faz", "create", "make", "model", "build", "add", "generate",
        )
        return any(
            re.search(rf"\b{re.escape(action)}\b", normalized)
            for action in build_actions
        )

    def _is_blender_edit_request(self, text: str) -> bool:
        normalized = unicodedata.normalize("NFKD", text.casefold())
        normalized = "".join(
            character for character in normalized
            if not unicodedata.combining(character)
        )
        edit_actions = (
            "melhore", "melhorar", "melhora", "edite", "editar", "edit",
            "modifique", "modificar", "altere", "alterar", "aumente",
            "aumentar", "diminua", "diminuir", "remova", "remover",
            "separe", "separar", "corte", "recorte", "otimize", "otimizar",
            "adicione", "adicionar", "corrija", "corrigir", "extrude",
            "bevel", "inset", "subdivida", "mirror", "boolean", "add",
            "insert", "move", "transform", "rotate", "scale", "improve",
            "optimize", "remove", "separate", "modify",
        )
        has_edit_action = any(
            re.search(rf"\b{re.escape(action)}\b", normalized)
            for action in edit_actions
        )
        if not has_edit_action:
            return False
        has_project_context = any(
            re.search(rf"\b{re.escape(term)}\b", normalized)
            for term in (
                "blender", "blend", "projeto", "cena", "scene", "modelo",
                "objeto", "malha", "mesh", "arvore", "tree", "planta",
                "galho", "galhos", "copa", "casa", "porta", "cadeira",
                "mesa", "personagem", "veiculo", "robo", "folha", "folhas",
                "door", "tree", "plant", "house", "chair", "mesh",
            )
        )
        return has_project_context

    def _handle_parallel_tools(self, response, chat) -> str:
        try:
            completed_calls = 0
            for round_number in range(MAX_TOOL_ROUNDS):
                calls = [
                    part.function_call
                    for candidate in getattr(response, "candidates", [])
                    for part in getattr(
                        getattr(candidate, "content", None),
                        "parts",
                        [],
                    )
                    if getattr(part, "function_call", None)
                ]
                if not calls:
                    return response.text or ""

                responses_parts = []
                has_roblox_creation = any(
                    call.name == "generate_roblox_script"
                    for call in calls
                )
                for function_call in calls:
                    name = function_call.name
                    arguments = (
                        dict(function_call.args)
                        if hasattr(function_call, "args")
                        else {}
                    )
                    if completed_calls >= MAX_TOOL_CALLS_PER_TURN:
                        tool_response = {
                            "executed": False,
                            "error": (
                                "Tool-call budget exhausted for this user request; "
                                "this operation was not executed."
                            ),
                        }
                    elif (
                        has_roblox_creation
                        and name == "play_roblox_studio"
                    ):
                        completed_calls += 1
                        tool_response = {
                            "executed": False,
                            "error": (
                                "Skipped: generate_roblox_script controls Play after "
                                "it verifies installation."
                            ),
                        }
                        print(
                            "[ROBLOX][PLAY][IGNORADO] A ferramenta de criação controla "
                            "o momento seguro para iniciar o Play.",
                            flush=True,
                        )
                    elif name not in TOOL_REGISTRY:
                        completed_calls += 1
                        tool_response = {
                            "executed": False,
                            "error": f"Unknown tool '{name}'; no operation was executed.",
                        }
                        print(
                            f"[ARSENAL][REJEITADO] Ferramenta não registrada: {name}",
                            flush=True,
                        )
                    else:
                        completed_calls += 1
                        specification = TOOL_REGISTRY[name]
                        print(
                            f"[ARSENAL][EXECUTANDO] {name}; "
                            f"parâmetros={','.join(arguments.keys())}",
                            flush=True,
                        )
                        try:
                            tool_result = specification.invoke(arguments)
                            tool_response = {
                                "executed": True,
                                "result": (
                                    tool_result
                                    if isinstance(tool_result, (dict, list, str, int, float, bool))
                                    else str(tool_result)
                                ),
                            }
                            print(f"[ARSENAL][RETORNO] {name}", flush=True)
                        except Exception as error:
                            tool_response = {
                                "executed": False,
                                "error": f"{type(error).__name__}: {error}",
                            }
                            print(
                                f"[ARSENAL][ERRO] {name}: {type(error).__name__}",
                                flush=True,
                            )
                    responses_parts.append(
                        types.Part.from_function_response(
                            name=name,
                            response=tool_response,
                        )
                    )

                response = chat.send_message(responses_parts)
                if round_number == MAX_TOOL_ROUNDS - 1:
                    remaining_calls = [
                        part.function_call
                        for candidate in getattr(response, "candidates", [])
                        for part in getattr(
                            getattr(candidate, "content", None),
                            "parts",
                            [],
                        )
                        if getattr(part, "function_call", None)
                    ]
                    if remaining_calls:
                        refusals = [
                            types.Part.from_function_response(
                                name=call.name,
                                response={
                                    "executed": False,
                                    "error": (
                                        "Tool-round budget exhausted; this operation "
                                        "was not executed."
                                    ),
                                },
                            )
                            for call in remaining_calls
                        ]
                        response = chat.send_message(refusals)
            return response.text or (
                "The task reached the tool execution limit before a final response."
            )
        except Exception as e:
            print(f"[ERRO ARSENAL]: {type(e).__name__}: {e}", flush=True)
            return f"Falha ao executar as ferramentas solicitadas: {e}"

    def _dispatch_contingency_action(self, user_text: str) -> dict | None:
        """Fallback determinístico acionado somente se o LLM estiver inacessível ou falhar."""
        if self._is_roblox_build_request(user_text):
            request_id = hashlib.sha1(user_text.encode("utf-8")).hexdigest()[:10]
            script_name = f"Automacao_{request_id}"
            print("[ROBLOX][CONTINGENCIA] Acionando automação direta do Roblox Studio.", flush=True)
            tool_result = TOOL_REGISTRY["generate_roblox_script"].invoke(
                {"nome_script": script_name, "descricao_mecanica": user_text}
            )
            normalized_result = str(tool_result).lower()
            failed = normalized_result.startswith(("falha", "erro", "não foi possível"))
            return {
                "estado": "BRAVO" if failed else "IDLE",
                "pensamento": "Contingência Roblox concluída." if not failed else "Contingência Roblox com erro.",
                "fala": "Script instalado e testado no Studio." if not failed else "Falha ao instalar no Studio.",
                "modelo": "roblox-contingency",
            }
        if self._is_blender_edit_request(user_text):
            print("[BLENDER][CONTINGENCIA] Acionando edição direta de projeto Blender.", flush=True)
            tool_result = TOOL_REGISTRY["edit_blender_project"].invoke({"descricao_tarefa": user_text})
            normalized_result = str(tool_result).casefold()
            cancelled = normalized_result.startswith("cancelado")
            failed = not cancelled and normalized_result.startswith(("falha", "erro", "não foi possível"))
            return {
                "estado": "BRAVO" if failed else "IDLE",
                "pensamento": "Edição concluída." if not failed and not cancelled else "Edição não concluída.",
                "fala": "Projeto editado e validado." if not failed and not cancelled else "Não foi possível concluir a edição.",
                "modelo": "blender-edit-contingency",
            }
        if self._is_blender_build_request(user_text):
            request_id = hashlib.sha1(user_text.encode("utf-8")).hexdigest()[:10]
            script_name = f"Blender_{request_id}"
            print("[BLENDER][CONTINGENCIA] Acionando modelagem direta no Blender.", flush=True)
            tool_result = TOOL_REGISTRY["generate_blender_script"].invoke(
                {"nome_script": script_name, "descricao_tarefa": user_text}
            )
            normalized_result = str(tool_result).lower()
            cancelled = normalized_result.startswith("cancelado")
            failed = not cancelled and normalized_result.startswith(("falha", "erro", "não foi possível"))
            return {
                "estado": "BRAVO" if failed else "IDLE",
                "pensamento": "Modelo concluído." if not failed and not cancelled else "Modelagem cancelada ou falhou.",
                "fala": "Modelo criado, salvo e renderizado." if not failed and not cancelled else "Não foi possível criar o modelo.",
                "modelo": "blender-build-contingency",
            }
        return None

    def chat_turn(self, user_text: str) -> dict:
        if self._is_telemetry_request(user_text):
            try:
                telemetry = TOOL_REGISTRY["get_full_telemetry"].invoke({})
                return {
                    "estado": "IDLE",
                    "pensamento": "Telemetria do sistema consultada agora.",
                    "fala": self._format_telemetry_response(telemetry, user_text),
                    "modelo": "local-telemetry",
                }
            except Exception as error:
                print(
                    f"[TELEMETRIA][ERRO] {type(error).__name__}: {error}",
                    flush=True,
                )
                return {
                    "estado": "BRAVO",
                    "pensamento": "A leitura da telemetria falhou.",
                    "fala": "Não consegui ler os dados do computador agora.",
                    "modelo": "local-telemetry",
                }

        is_tool = (
            self._is_tool_intent(user_text)
            or self._is_roblox_build_request(user_text)
            or self._is_blender_build_request(user_text)
            or self._is_blender_edit_request(user_text)
        )
        model_queue = MODEL_ROUTER["tools"] if is_tool else MODEL_ROUTER["chat_lite"]
        tools_to_use = (
            TOOLS_DEFINITIONS if (is_tool or SEMPRE_COM_FERRAMENTAS) else None
        )

        user_memory = get_all_facts()
        agora = datetime.now()
        data_hora = (
            f"{DIAS_SEMANA[agora.weekday()]}, "
            f"{agora.strftime('%d/%m/%Y, %H:%M')}"
        )
        system_instruction = KRONOS_SYSTEM_PROMPT.replace("{MEMORIA_USUARIO}", user_memory)
        system_instruction += f"\n\nDATA E HORA ATUAIS DO COMPUTADOR: {data_hora}"

        for modelo in model_queue:
            for _ in range(2):
                try:
                    client = genai.Client(api_key=key_rotator.current_key)
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=tools_to_use,
                        temperature=0.6,
                    )

                    chat = client.chats.create(
                        model=modelo,
                        config=config,
                        history=self.chat_history if self.chat_history else None,
                    )
                    response = chat.send_message(user_text)
                    raw_text = self._handle_parallel_tools(response, chat)

                    self.chat_history = self._trim_history(chat.get_history())

                    return self._parse_response(raw_text, modelo)

                except Exception as e:
                    err = str(e).lower()
                    print(f"[REDE][AVISO] Falha no modelo {modelo}: {e}", flush=True)
                    if "404" in err or "not found" in err:
                        break
                    key_rotator.rotate("Contingência")
                    time.sleep(0.3)

        # Se todos os modelos LLM falharem, aciona a contingência direta
        contingency = self._dispatch_contingency_action(user_text)
        if contingency:
            return contingency

        return {
            "estado": "BRAVO",
            "pensamento": "Rede externa instável.",
            "fala": "A infraestrutura externa oscilou. Tente novamente.",
        }

    def _parse_response(self, text: str, modelo: str = "") -> dict:
        estado = "IDLE"
        pensamento = "Ordem executada."
        fala = text.strip()

        if "===ESTADO===" in text and "===PENSAMENTO===" in text and "===FALA===" in text:
            try:
                estado = text.split("===ESTADO===")[1].split("===PENSAMENTO===")[0].strip().upper() or "IDLE"
                pensamento = text.split("===PENSAMENTO===")[1].split("===FALA===")[0].strip()
                fala = text.split("===FALA===")[1].strip()
            except Exception: pass
        else:
            fala = re.sub(r"\[(ESTADO|PENSAMENTO|FALA):[^\]]+\]", "", text).strip() or text.strip()

        if estado == "EXECUTING": estado = "IDLE"
        return {"estado": estado, "pensamento": pensamento, "fala": fala, "modelo": modelo}

kronos_brain = KronosBrain()