"""Demonstração sem LLM, dados reais, chaves ou leitura do .env."""
from app.orchestration import Orquestrador

if __name__ == "__main__":
    entrada = {"user_id": "demo_A", "message": "Como configurar Wi-Fi na minha maquininha?"}
    print(Orquestrador().executar(entrada).model_dump_json(indent=2))
