# Tool accuracy (2026-11-19, claude-sonnet-5-5, 40 runs)

Selection **100%** · arguments **98%** · cost US$ 0.2713

| Tool | Cases | Selection | Arguments |
|---|---:|---:|---:|
| `get_receivables` | 4 | 100% | 100% |
| `get_recent_transactions` | 4 | 100% | 100% |
| `get_sales_summary` | 4 | 100% | 100% |
| `get_terminal_status` | 4 | 100% | 100% |
| `get_tickets` | 4 | 100% | 100% |
| `lookup_decline_code` | 4 | 100% | 100% |
| `propose_anticipation` | 4 | 100% | 100% |
| `propose_terminal_service` | 4 | 100% | 100% |
| `propose_ticket` | 4 | 100% | 100% |
| `simulate_anticipation` | 4 | 100% | 75% |

## Misses

- t29 (simulate_anticipation): calls ['simulate_anticipation']; date_to='2027-01-19' (expected '2027-01-18')
