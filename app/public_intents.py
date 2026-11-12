"""Gramatica conservadora para fontes fixas; nunca envia a pergunta recebida."""
import re,unicodedata
COMMON=set('what whats s is the in of for a an do does please tell me qual e o a os as de do da em para por favor informe diga esta estara sera como how'.split())
WEATHER=set('weather forecast temperature clima tempo previsao temperatura porto alegre rs tomorrow amanha'.split())
EXCHANGE=set('euro eur brl real reais cotacao cambio exchange rate today hoje atual current referencia reference do dia'.split())

def fixed_public_query(message):
    if not isinstance(message,str) or not 1<=len(message)<=300:return None
    plain=''.join(c for c in unicodedata.normalize('NFKD',message.casefold()) if not unicodedata.combining(c))
    # URLs, IDs, emails, valores, comandos e formas nao reconhecidas falham fechadas.
    if re.search(r"[^a-z\s?'.,!-]",plain):return None
    words=set(re.findall('[a-z]+',plain))
    if not words:return None
    if words <= COMMON|WEATHER and {'porto','alegre'}.issubset(words) and words & {'amanha','tomorrow'} and words & {'weather','forecast','temperature','clima','previsao','temperatura','tempo'}:
        return 'previsao Porto Alegre amanha'
    if words <= COMMON|EXCHANGE and words & {'euro','eur'} and words & {'cotacao','cambio','exchange','rate'}:
        return 'cotacao euro hoje'
    return None
