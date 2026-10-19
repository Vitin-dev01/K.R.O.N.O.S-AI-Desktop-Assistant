import base64
import io
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import brain
import voice


class KronosPersonalityTests(unittest.TestCase):
    def test_personality_is_confident_without_insulting_the_user(self):
        prompt = brain.KRONOS_SYSTEM_PROMPT.casefold()

        self.assertIn("arrogância elegante", prompt)
        self.assertIn("nunca a pessoa", prompt)
        self.assertIn("português brasileiro natural", prompt)
        self.assertNotIn("detesta a mediocridade humana", prompt)


class KronosTelemetryRoutingTests(unittest.TestCase):
    def setUp(self):
        self.telemetry = {
            "cpu_percent": 17.5,
            "ram_percent": 63,
            "ram_used_gb": 10.08,
            "ram_total_gb": 16.0,
            "disk_percent": 70,
            "disk_free_gb": 120.0,
            "net_down_kbs": 4.2,
            "net_up_kbs": 1.1,
            "active_mode": "PADRAO",
            "weather": {
                "cidade": "CURITIBA",
                "temperatura": "20°C",
                "condicao": "Nublado",
                "umidade": "60%",
            },
        }

    def test_legacy_pc_health_questions_are_recognized_as_tool_requests(self):
        brain_instance = brain.KronosBrain()
        for command in (
            "Como está meu PC?",
            "Quero ver como está o uso da minha memória RAM e CPU agora",
            "Me mostra o status do computador",
        ):
            with self.subTest(command=command):
                self.assertTrue(brain_instance._is_telemetry_request(command))
                self.assertTrue(brain_instance._is_tool_intent(command))

    def test_pc_health_question_reads_and_reports_live_telemetry_directly(self):
        telemetry_tool = SimpleNamespace(
            invoke=MagicMock(return_value=self.telemetry)
        )
        with patch.object(
            brain,
            "TOOL_REGISTRY",
            {"get_full_telemetry": telemetry_tool},
        ):
            result = brain.KronosBrain().chat_turn("Como está meu PC?")

        telemetry_tool.invoke.assert_called_once_with({})
        self.assertEqual(result["modelo"], "local-telemetry")
        self.assertIn("CPU em 17.5%", result["fala"])
        self.assertIn("RAM em 63%", result["fala"])
        self.assertIn("120.0 GB livres", result["fala"])

    def test_component_temperature_question_does_not_claim_weather_is_cpu_temperature(self):
        answer = brain.KronosBrain._format_telemetry_response(
            self.telemetry, "Qual a temperatura do processador?"
        )

        self.assertIn("não mede a temperatura física", answer)
        self.assertNotIn("Clima em", answer)


class KronosVoiceTests(unittest.TestCase):
    def test_text_cleanup_preserves_question_and_exclamation_prosody(self):
        self.assertEqual(
            voice._prepare_text("Você conseguiu? Excelente!"),
            "Você conseguiu? Excelente!",
        )

    def test_gemini_tts_uses_transcript_metadata_and_native_wav_output(self):
        audio_bytes = b"RIFFmock-wav-data"
        client = MagicMock()
        client.interactions.create.return_value = SimpleNamespace(
            output_audio=SimpleNamespace(
                data=base64.b64encode(audio_bytes).decode("ascii")
            )
        )

        result = voice._generate_tts_audio(
            client, "gemini-3.8-flash-tts", "Você conseguiu?"
        )

        self.assertEqual(base64.b64decode(result), audio_bytes)
        request = client.interactions.create.call_args.kwargs
        speech_text = request["input"][0]["content"][0]
        self.assertEqual(speech_text["text"], "Você conseguiu?")
        self.assertEqual(
            speech_text["annotations"][0]["type"], "speech_metadata"
        )
        self.assertIn(
            "português brasileiro",
            speech_text["annotations"][0]["style"].casefold(),
        )
        self.assertEqual(
            request["generation_config"]["speech_config"][0]["voice"],
            voice.KRONOS_VOICE,
        )

    def test_legacy_tts_fallback_uses_charon_and_the_updated_style(self):
        client = MagicMock()
        pcm = b"\x00\x00" * 100
        client.models.generate_content.return_value = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                inline_data=SimpleNamespace(data=pcm)
                            )
                        ]
                    )
                )
            ]
        )

        voice._generate_tts_audio(
            client, "gemini-2.5-flash-preview-tts", "Teste de voz."
        )

        config = client.models.generate_content.call_args.kwargs["config"]
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(
            config.speech_config.voice_config.prebuilt_voice_config.voice_name,
            voice.KRONOS_VOICE,
        )
        self.assertIn("português brasileiro natural", contents.casefold())
        self.assertIn("arrogância elegante", contents.casefold())

    def test_primary_tts_voice_is_charon(self):
        self.assertEqual(voice.KRONOS_VOICE, "Charon")

    def test_pcm_fallback_keeps_native_rate_without_pitch_speedup(self):
        wav_bytes = voice._save_pcm_to_wav_bytes(b"\x00\x00" * 200)

        with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
            self.assertEqual(audio.getframerate(), 24000)


if __name__ == "__main__":
    unittest.main()
