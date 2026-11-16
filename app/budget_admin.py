"""Explicitly create a NEW model-budget ledger. Never resets an existing file."""
import argparse
import sys
from app.agentic_client import Budget

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',required=True)
    parser.add_argument('--max-calls',type=int,required=True)
    parser.add_argument('--max-cost',required=True,help='Authorized USD ceiling, at most 5')
    args=parser.parse_args(argv)
    try:Budget(args.ledger,max_calls=args.max_calls,max_cost=args.max_cost,initialize=True)
    except Exception:
        print('Budget initialization refused. Existing evidence is preserved.',file=sys.stderr)
        return 1
    print('New local budget initialized. No provider call was made; this does not grant spending authorization.')
    return 0

if __name__=='__main__':raise SystemExit(main())
