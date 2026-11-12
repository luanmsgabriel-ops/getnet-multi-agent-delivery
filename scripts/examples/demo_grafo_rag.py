"""Demonstra o grafo com recuperacao extrativa real, sem rede ou LLM."""
import json
import sys
from pathlib import Path
from app.knowledge import KnowledgeRag
from app.orchestration import Orquestrador
if __name__ == '__main__':
    corpus = Path(__file__).resolve().parents[2] / 'corpus_publico'
    graph = Orquestrador(knowledge=KnowledgeRag.from_directory(corpus))
    question = ' '.join(sys.argv[1:]) or 'Como habilitar Pix pelo portal?'
    print(json.dumps(graph.executar({'user_id':'demo_A','message':question}).model_dump(), ensure_ascii=False, indent=2))
