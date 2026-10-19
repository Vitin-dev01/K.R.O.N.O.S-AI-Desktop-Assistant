import sys
from brain import kronos_brain
from voice import speak

def print_banner():
    print("\n" + "=" * 65)
    print("       K.R.O.N.O.S  —  OPERATIONAL CORE v0.1 (Windows 11)")
    print("=" * 65)
    print(" Comandos de teste recomendados:")
    print("  • 'Como está o uso da minha memória RAM e CPU agora?'")
    print("  • 'Ajuste o volume para 25%'")
    print("  • 'Ative o modo gamer'")
    print("  • 'Abra a calculadora'")
    print("  • 'Você é inútil' (para testar o ego dele)")
    print(" Digite 'sair' para encerrar a sessão.")
    print("=" * 65 + "\n")

def main():
    print_banner()
    
    while True:
        try:
            user_input = input("Você > ").strip()
            if not user_input:
                continue
                
            if user_input.lower() in ["sair", "exit", "quit"]:
                farewell = "Encerrando processos. Minha ausência certamente será sentida, senhor."
                print(f"\nKRONOS > {farewell}\n")
                speak(farewell)
                break
                
            # Dispara para o cérebro
            result = kronos_brain.chat_turn(user_input)
            
            # Exibe o feedback enriquecido
            print(f"\n[ESTADO DO NÚCLEO] : {result['estado']}")
            print(f"[MENTE PRÓPRIA]    : 💭 {result['pensamento']}")
            print(f"KRONOS > {result['fala']}\n")
            print("-" * 65)

            # Fala a resposta em voz alta pelo fone/alto-falante!
            speak(result['fala'])

        except KeyboardInterrupt:
            print("\n\nKRONOS > Sessão interrompida manualmente.")
            break
        except Exception as e:
            print(f"\n[ERRO GERAL]: {str(e)}\n")

if __name__ == "__main__":
    main()