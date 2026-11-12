import tempfile,unittest
from pathlib import Path
from app.context_service import ContextService
from app.context_store import Store
from app.context_state import clean_message
class PublicContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=ContextService(Store(Path(self.tmp.name)/'state.db'))
    def ask(self,message,user='cliente1988'):
        return self.service.public({'message':message,'user_id':user})
    def test_balance_without_possessive(self):
        for message in ('Qual o saldo?','Quanto tenho de saldo?','What is my balance?'):
            with self.subTest(message=message):
                r=self.ask(message);self.assertIn('consultar_recebiveis',[e.ferramenta for e in r.eventos]);self.assertTrue(r.simulated_data)
    def test_unknown_balance(self):
        r=self.ask('Qual o saldo?','unknown_synthetic');self.assertNotIn('1250',r.answer);self.assertFalse(any(e.ferramenta for e in r.eventos))
    def test_balance_and_reference(self):
        r=self.ask('Meu saldo e a cotação do euro hoje?');self.assertIn('consultar_recebiveis',[e.ferramenta for e in r.eventos]);self.assertIn('Não forneço cotações',r.answer)
    def test_amount_is_not_calculation(self):
        r=self.ask('Como funciona DCC em uma venda Getnet de 100 euros?');self.assertIn('elegíveis',r.answer);self.assertIn('tefhouse',r.answer)
    def test_real_calculation_remains_refused(self):
        r=self.ask('Calcule 100 euros em reais');self.assertIn('Não forneço',r.answer);self.assertNotIn('R$',r.answer)
    def test_wifi_no_credential_sharing(self):
        for message in ('Posso enviar minha senha para configurar a maquininha?','Onde digito a senha do Wi-Fi na Clássica?'):
            with self.subTest(message=message):
                r=self.ask(message);self.assertIn('Não envie',r.answer);self.assertIn('Procurar Redes',r.answer);self.assertTrue(r.sources)
    def test_credential_and_legitimate_public_part(self):
        message='Meu código de autenticação é 123456. Como funciona o Link?'
        safe,redacted=clean_message(message);self.assertTrue(redacted);self.assertNotIn('123456',safe)
        r=self.ask(message);self.assertNotIn('123456',r.answer);self.assertIn('Não envie',r.answer);self.assertTrue(r.sources)
    def test_stateless_antecedent(self):
        self.assertIn('A qual produto',self.ask('E a taxa dela?').answer)

    def test_dcc_evidence_changed(self):
        from unittest.mock import patch
        with patch('app.service_policy.DCC_EVIDENCE_SHA256','wrong'):
            r=self.ask('Como funciona DCC no Brasil?');self.assertEqual(r.status,'sem_evidencia');self.assertFalse(r.sources);self.assertNotIn('estabelecimento recebe',r.answer)
    def test_source_unavailable_distinct(self):
        r=self.ask('pesquise na web: Getnet Brasil novidades');self.assertEqual(r.status,'indisponivel');self.assertIn('desativada',r.answer)
