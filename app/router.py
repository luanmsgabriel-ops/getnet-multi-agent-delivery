"""Router demonstrativo determinístico, substituível por adaptador LLM."""
from app.intents import normalize, classify, natural_public_question
from app.contracts import Entrada, Plano

class RouterDemo:
    def planejar(self, entrada: Entrada) -> Plano:
        texto = normalize(entrada.message)
        from app.intents import request_facts
        facts = request_facts(entrada.message)
        if facts.unsupported_action or facts.account_migration:
            return Plano(rota='knowledge')
        if texto.strip().startswith('pesquise na web:'):
            return Plano(rota='knowledge')
        from app.public_intents import fixed_public_query
        if fixed_public_query(entrada.message) or natural_public_question(entrada.message):
            return Plano(rota='knowledge')
        intent = classify(entrada.message)
        suporte = intent.receivables or intent.terminal
        conhecimento = intent.knowledge
        rota = ("support_knowledge" if suporte and conhecimento else
                "support" if suporte else "knowledge" if conhecimento else "clarify")
        return Plano(rota=rota)
