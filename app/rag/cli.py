"""CLI separada do grafo: captura publica, revisao e consulta extrativa local."""
import argparse
import json
from pathlib import Path
from .core import snapshot,save_snapshot,load_snapshot,Index
from .fetch import fetch_bounded,SOURCES

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',default='corpus_publico')
    sub=parser.add_subparsers(dest='command',required=True)
    capture=sub.add_parser('capture');capture.add_argument('url',choices=SOURCES)
    query=sub.add_parser('query');query.add_argument('message');query.add_argument('--market',choices=('BR','GLOBAL'),default='BR')
    review=sub.add_parser('review');review.add_argument('filename');review.add_argument('--approve',action='store_true')
    args=parser.parse_args()
    directory=Path(args.corpus)
    if args.command=='capture':
        from .pdf_source import PDF_SOURCES, capture_bounded, as_snapshot
        doc=as_snapshot(capture_bounded(args.url)) if args.url in PDF_SOURCES else snapshot(fetch_bounded(args.url))
        path=save_snapshot(doc,directory)
        print(json.dumps({'saved':str(path),'reviewed':False,'title':doc['title'],'chunks':len(doc['chunks'])},ensure_ascii=False));return
    if args.command=='review':
        # Nome simples somente; jamais aceitar caminho de usuario como arquivo.
        if Path(args.filename).name!=args.filename or '/' in args.filename or '\\' in args.filename:
            raise ValueError('Use nome do snapshot, nao caminho')
        doc=load_snapshot(directory/args.filename,SOURCES)
        if args.approve:
            doc['reviewed']=True;save_snapshot(doc,directory)
        print(json.dumps(doc,ensure_ascii=False,indent=2));return
    documents=[load_snapshot(p,SOURCES) for p in sorted(directory.glob('*.json'))]
    print(json.dumps(Index(documents).answer_extractive(args.message,market=args.market),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
