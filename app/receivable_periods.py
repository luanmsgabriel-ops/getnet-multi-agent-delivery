"""Períodos explícitos da simulação; não inferem prazos comerciais."""
from dataclasses import dataclass
from datetime import date, timedelta
import re

MAX_PERIOD_DAYS = 366


@dataclass(frozen=True)
class DatePeriod:
    start: str
    end: str

    def resolve(self, reference):
        if type(reference) is not date:
            raise ValueError('A fixture não informa data de referência válida.')
        def day(value):
            offsets = {'today': 0, 'yesterday': -1, 'tomorrow': 1}
            if value in offsets:
                return reference + timedelta(days=offsets[value])
            if value.startswith('offset:'):
                return reference + timedelta(days=int(value.split(':')[1]))
            return date.fromisoformat(value)
        start, end = day(self.start), day(self.end)
        if start > end:
            raise ValueError('O início do período é posterior ao fim; confirme as datas.')
        if (end-start).days >= MAX_PERIOD_DAYS:
            raise ValueError('Consulte um intervalo de até 366 dias por vez.')
        return start, end


_MONTHS = 'janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro'.split()
_MONTH_PATTERN = '|'.join(_MONTHS)
_DATE = re.compile(
    r'\b(?:nos?\s+)?ultimos?\s+(?P<last>\d+)\s+dias?\b|'
    r'\b(?:ha|faz)\s+(?P<ago>\d+)\s+dias?\b|'
    r'\b(?P<iso>\d{4}-\d{1,2}-\d{1,2})\b|'
    r'\b(?P<br>\d{1,2}/\d{1,2}/\d{4})\b|'
    r'\b(?P<written>\d{1,2}\s+de\s+(?:'+_MONTH_PATTERN+r')\s+de\s+\d{4})\b|'
    r'\b(?P<relative>anteontem|ontem|hoje|amanha|today|yesterday|tomorrow)\b')
_ROLE = re.compile(
    r'\b(?P<sale>vendas?|sales?|vendi|vendidas?|vendidos?|fiz|fizemos|realizei|realizamos|efetuei|efetuamos)\b|'
    r'\b(?P<settlement>recebiveis|recebivel|receivables?|recebimentos?|receb(?:o|er|erei)|receberemos|'
    r'creditos?(?=\s+(?:previstos?|em|para))|creditad[oa]s?|deposit(?:o|os|ad[oa]s?|ed)?|cai|caem|cair|caira|receive|settlement)\b')
_UNSUPPORTED = re.compile(
    r'\b\d{1,2}/\d{1,2}(?:/\d{2})?\b|\b\d{4}-\d{1,2}(?:-\d{1,2})?\b|'
    r'\b(?:semana|semanas|mes|meses|ano|anos|week|month|year|recentes|recentemente)\b|'
    r'\b(?:segunda|terca|quarta|quinta|sexta|sabado|domingo|janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b|'
    r'\b(?:ultimos?|proximos?|entre|desde|ate|periodo|datas?)\b|\b(?:dia|em|a|e)\s+\d{1,2}\b')


def temporal_periods(text, default_role):
    """Retorna venda, recebimento e eventual necessidade de esclarecimento.

    Dois limites só formam intervalo com conector explícito. Sem isso não
    descartamos uma data nem reinterpretamos um pedido restrito como total.
    """
    # A single explicit month/year scopes both day bounds; never infer the year.
    text=re.sub(r'\b(entre|de)\s+(\d{1,2})\s+(e|a|ate)\s+(\d{1,2})\s+de\s+('+_MONTH_PATTERN+r')\s+de\s+(\d{4})\b',lambda m:f'{m[1]} {m[2]} de {m[5]} de {m[6]} {m[3]} {m[4]} de {m[5]} de {m[6]}',text)
    # 'mesmo quando/even when' describes inclusive background, not an additional date constraint.
    text=re.split(r'\b(?:mesmo quando|even when|independentemente de quando|regardless of when)\b',text,maxsplit=1)[0]
    matches = list(_DATE.finditer(text))
    remaining = list(text)
    for match in matches:
        remaining[match.start():match.end()] = ' ' * (match.end()-match.start())
    # Conectores são válidos apenas entre limites reconhecidos.
    masked = ''.join(remaining)
    if matches:
        masked = re.sub(r'\b(?:periodo|datas?)\b', ' ', masked)
    if len(matches) >= 2:
        masked = re.sub(r'\b(?:de|entre|a|ate|e|from|to|through|and)\b|[-–—]', ' ', masked)
    if _UNSUPPORTED.search(masked):
        return None, None, 'Informe datas completas (DD/MM/AAAA ou AAAA-MM-DD), hoje, ontem, há N dias ou últimos N dias; esclareça o período solicitado.'
    grouped = {'sale': [], 'settlement': []}
    roles = list(_ROLE.finditer(text))
    for match in matches:
        before = [cue for cue in roles if cue.end() <= match.start()]
        after = [cue for cue in roles if cue.start() >= match.end()]
        cue = before[-1] if before else after[0] if after else None
        role = cue.lastgroup if cue else default_role
        try:
            if match['last']:
                count = int(match['last'])
                if not 1 <= count <= MAX_PERIOD_DAYS:
                    raise ValueError('Informe uma quantidade entre 1 e 366 dias.')
                period = DatePeriod(f'offset:{1-count}', 'today')
            elif match['ago']:
                count = int(match['ago'])
                if not 0 <= count <= MAX_PERIOD_DAYS:
                    raise ValueError('Informe uma quantidade entre 0 e 366 dias.')
                period = DatePeriod(f'offset:{-count}', f'offset:{-count}')
            else:
                if match['iso']:
                    year, month, day = map(int, match['iso'].split('-'))
                    value = date(year, month, day).isoformat()
                elif match['br']:
                    day, month, year = map(int, match['br'].split('/'))
                    value = date(year, month, day).isoformat()
                elif match['written']:
                    day, month, year = match['written'].split(' de ')
                    value = date(int(year), _MONTHS.index(month)+1, int(day)).isoformat()
                else:
                    value = {'hoje':'today','ontem':'yesterday','anteontem':'offset:-2','amanha':'tomorrow'}.get(match['relative'],match['relative'])
                period = DatePeriod(value, value)
        except (ValueError, OverflowError) as error:
            return None, None, ('Data inválida; confirme o dia, mês e ano.' if not match['last'] and not match['ago'] else str(error))
        grouped[role].append((match,period))
    periods = {}
    for role, entries in grouped.items():
        if not entries:
            periods[role] = None
        elif len(entries)==1:
            periods[role] = entries[0][1]
        elif len(entries)==2:
            (first,left),(second,right) = entries
            connector = text[first.end():second.start()].strip()
            is_range = bool(re.fullmatch(r'(?:a|ate|to|through|[-–—])',connector)) or (
                connector in {'e','and'} and bool(re.search(r'\b(?:entre|between)\s*$',text[:first.start()])))
            if not is_range or left.start != left.end or right.start != right.end:
                return None,None,'Há mais de uma data possível; informe um intervalo explícito e se ele é de venda ou recebimento.'
            periods[role] = DatePeriod(left.start,right.end)
        else:
            return None,None,'Há mais de duas datas para a mesma consulta; informe um intervalo por vez.'
        period = periods[role]
        if period and re.fullmatch(r'\d{4}-\d{2}-\d{2}',period.start) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',period.end):
            try:
                period.resolve(date(2000,1,1))
            except (ValueError,OverflowError) as error:
                return None,None,str(error)
    return periods['sale'],periods['settlement'],None
