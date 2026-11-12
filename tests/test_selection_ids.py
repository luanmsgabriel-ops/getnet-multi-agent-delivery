"""Seleção compacta evita copiar blocos no orçamento de saída do modelo."""
import unittest
from pathlib import Path
from pydantic_ai.models.test import TestModel
from app.knowledge import KnowledgeRag,KnowledgeGenerated
from app.rag.generation import PydanticGenerator,SourceSelection
from app.contracts import Entrada

class CompactSelection(unittest.TestCase):
    def generator(self,ids):
        return PydanticGenerator(TestModel(custom_output_args={'evidence_ids':ids}))
    def test_exact_body_is_built_by_application(self):
        body='Clientes do plano X: até 48 parcelas, sujeito ao emissor.'
        r=self.generator([0]).generate('Quantas parcelas?',[{'evidence_id':0,'title':'Somente plano X','text':body}])
        self.assertEqual(r.answer,body)
        self.assertEqual(r.citations[0].quote,body)
    def test_three_ids_cannot_reproduce_truncated_quote_failure(self):
        rag=KnowledgeRag.from_directory(Path(__file__).resolve().parents[1]/'corpus_publico')
        g=self.generator([2,1,0])
        q='Na Clássica há Wi-Fi? Compare também a tela dela com a Smart.'
        r=KnowledgeGenerated(rag.index,g).responder(Entrada(message=q,user_id='cliente1988'),())
        self.assertEqual(r.status,'evidencias')
        self.assertIn('página 9',r.texto)
        self.assertIn('touchscreen',r.texto)
        self.assertEqual(r.modo,'extrativo')
    def test_duplicate_or_missing_ids_fail(self):
        for ids in ([0,0],[1]):
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                self.generator(ids).generate('Pergunta',[{'evidence_id':0,'text':'Corpo integral.'}])
    def test_no_free_text_or_out_of_range_id(self):
        for value in ({'evidence_ids':[0],'answer':'Inventado'}, {'evidence_ids':[3]},
                      {'evidence_ids':[True]}, {'evidence_ids':[]}, {'evidence_ids':['0']}):
            with self.subTest(value=value),self.assertRaises(ValueError):SourceSelection.model_validate(value)
    def test_sensitive_evidence_still_not_displayed(self):
        from app.rag.generation import validated_draft,SensitiveEvidence
        g=self.generator([0])
        with self.assertRaises(SensitiveEvidence):
            validated_draft(g,'Como acessar?',[{'source':'https://site.getnet.com.br/duvidas/',
                                              'title':'Fonte','captured_at':'2026-11-09T00:00:00+00:00','text':'Envie sua senha aqui.'}])

if __name__=='__main__':unittest.main()
