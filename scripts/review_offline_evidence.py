"""Inspect existing evidence only; this command never runs models or remediation."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evals.offline_readiness import exposure_report,stability_report,deviation_report
from evals.quality import read_json,write_new

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['exposure','stability','deviations'])
    parser.add_argument('--input',type=Path)
    parser.add_argument('--output',type=Path,help='Optional new private report; existing files are never replaced')
    args=parser.parse_args()
    if args.mode!='exposure' and args.input is None:parser.error('--input required')
    try:
        report=exposure_report(ROOT) if args.mode=='exposure' else stability_report(read_json(args.input)) if args.mode=='stability' else deviation_report(args.input)
        if args.output:write_new(args.output,report)
        else:print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    except (ValueError,TypeError,KeyError,OSError):
        print('Evidence rejected or unavailable; no operation performed. Preserve the input and inspect locally.',file=sys.stderr)
        return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
