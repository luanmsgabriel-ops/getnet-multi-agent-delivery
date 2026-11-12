import unittest
from concurrent.futures import ThreadPoolExecutor
from pydantic import ValidationError
from app.contracts import Plano, RespostaEspecialista
from app.orchestration import Orquestrador

class GrafoTest(unittest.TestCase):
    def setUp(self):
        self.app = Orquestrador()

    def executar(self, texto):
        return self.app.executar({"user_id": "demo_A", "message": texto})

    def test_rotas(self):
        for texto, rota in [("Como usar Pix?", "knowledge"), ("Meus recebíveis", "support"),
                            ("Como configurar wifi na minha maquininha?", "support_knowledge"),
                            ("oi", "clarify")]:
            with self.subTest(rota=rota):
                self.assertEqual(self.executar(texto).route, rota)

    def test_sequencia_limitada(self):
        r = self.executar("Como configurar minha maquininha?")
        self.assertEqual([e.agente for e in r.eventos], ["router", "support", "knowledge"])
        self.assertEqual(r.status, "simulado")
        self.assertTrue(all(e.ferramenta is None for e in r.eventos))

    def test_validacao(self):
        for dados in [{"user_id": "a", "message": " "}, {"user_id": "../a", "message": "x"},
                      {"user_id": "a", "message": "a"*4001},
                      {"user_id": "a", "message": "x", "rota": "support"},
                      {"user_id": 12, "message": "x"}]:
            with self.subTest(dados=str(dados)[:30]), self.assertRaises(ValidationError):
                self.app.executar(dados)

    def test_falha_router_sem_vazamento(self):
        class Falha:
            def planejar(self, entrada):
                raise RuntimeError("SEGREDO_CANARIO")
        r = Orquestrador(router=Falha()).executar({"user_id": "demo_A", "message": "CANARIO"})
        self.assertEqual(r.status, "indisponivel")
        self.assertNotIn("CANARIO", r.model_dump_json())
        self.assertEqual(len(r.eventos), 1)

    def test_plano_invalido_falha_fechado(self):
        class Invalido:
            def planejar(self, entrada):
                return {"rota": "shell"}
        r = Orquestrador(router=Invalido()).executar({"user_id": "a", "message": "x"})
        self.assertEqual(r.status, "indisponivel")

    def test_falha_support_nao_chama_knowledge(self):
        class Falha:
            def responder(self, entrada, contexto):
                raise RuntimeError("CANARIO")
        class Proibido:
            def responder(self, entrada, contexto):
                raise AssertionError("nao deveria executar")
        r = Orquestrador(support=Falha(), knowledge=Proibido()).executar(
            {"user_id": "a", "message": "Como usar minha maquininha?"})
        self.assertEqual([e.agente for e in r.eventos], ["router", "support"])
        self.assertEqual(r.status, "indisponivel")

    def test_contexto_preserva_caracteres(self):
        texto = "cliente_123 email_a@example.com https://example.com/a_b"
        class Suporte:
            def responder(self, entrada, contexto):
                return RespostaEspecialista(texto=texto)
        class Conhecimento:
            def responder(self, entrada, contexto):
                assert contexto[0].texto == texto
                return RespostaEspecialista(texto=texto)
        r = Orquestrador(support=Suporte(), knowledge=Conhecimento()).executar(
            {"user_id": "a", "message": "Como usar minha maquininha?"})
        self.assertEqual(r.answer, texto+"\n"+texto)

    def test_sem_estado_cruzado(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            saidas = list(pool.map(self.executar, ["Meus recebíveis", "Como usar Pix?"]))
        self.assertNotEqual(saidas[0].request_id, saidas[1].request_id)
        self.assertEqual([e.agente for e in saidas[0].eventos], ["router", "support"])
        self.assertEqual([e.agente for e in saidas[1].eventos], ["router", "knowledge"])

    def test_trace_nao_contem_conteudo(self):
        r = self.executar("Como usar Pix? CANARIO_123")
        self.assertNotIn("CANARIO_123", r.model_dump_json())
        self.assertTrue(all(e.duracao_ms >= 0 for e in r.eventos))


    def test_contrato_saida(self):
        dados = self.executar("Como usar Pix?").model_dump()
        self.assertTrue({"request_id", "status", "route", "answer", "sources", "simulated_data"} <= dados.keys())
        self.assertEqual(dados["sources"], [])
        self.assertIs(dados["simulated_data"], True)

    def test_indisponibilidade_interrompe_sequencia(self):
        class Indisponivel:
            def responder(self, entrada, contexto):
                return RespostaEspecialista(texto="CANARIO", status="indisponivel")
        r = Orquestrador(support=Indisponivel()).executar(
            {"user_id": "a", "message": "Como usar minha maquininha?"})
        self.assertEqual(r.status, "indisponivel")
        self.assertEqual(r.eventos[-1].status, "falha")
        self.assertEqual(len(r.eventos), 2)
        self.assertNotIn("CANARIO", r.model_dump_json())

    def test_resposta_vazia_e_extra_rejeitadas(self):
        for resultado in [{"texto": " "}, {"texto": "ok", "comando": "shell"}]:
            class Invalido:
                def responder(self, entrada, contexto):
                    return resultado
            r = Orquestrador(knowledge=Invalido()).executar(
                {"user_id": "a", "message": "Como usar Pix?"})
            self.assertEqual(r.status, "indisponivel")

    def test_limites_inclusivos(self):
        self.app.executar({"user_id": "a"*64, "message": "x"*4000})
        with self.assertRaises(ValidationError):
            self.app.executar({"user_id": "a"*65, "message": "x"})

    def test_falha_knowledge_descarta_resposta_parcial(self):
        class Suporte:
            def responder(self, entrada, contexto):
                return RespostaEspecialista(texto="PARCIAL_CANARIO")
        class Falha:
            def responder(self, entrada, contexto):
                raise RuntimeError("CANARIO")
        r = Orquestrador(support=Suporte(), knowledge=Falha()).executar(
            {"user_id": "a", "message": "Como usar minha maquininha?"})
        self.assertEqual(r.status, "indisponivel")
        self.assertEqual(len(r.eventos), 3)
        self.assertNotIn("CANARIO", r.model_dump_json())

    def test_entrada_preservada_apos_falha(self):
        class Falha:
            def planejar(self, entrada):
                raise RuntimeError()
        dados = {"user_id": "a", "message": "conteudo_original"}
        Orquestrador(router=Falha()).executar(dados)
        self.assertEqual(dados, {"user_id": "a", "message": "conteudo_original"})

if __name__ == "__main__":
    unittest.main()
