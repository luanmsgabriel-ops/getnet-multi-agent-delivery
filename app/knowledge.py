"""Adaptadores Knowledge: demonstração, RAG local e busca oficial opcional.

O modo gerado opcional seleciona evidências via LLM; a aplicação valida e
compõe a resposta. Cada adaptador preserva os limites de escopo e privacidade.
"""
from app.contracts import Entrada, RespostaEspecialista
from app.response_notices import AnswerText, compose_notices

class KnowledgeDemo:
    def responder(self, entrada: Entrada, contexto: tuple[RespostaEspecialista, ...]) -> RespostaEspecialista:
        return RespostaEspecialista(texto="Demonstração: rota de conhecimento selecionada. RAG e busca web ainda não estão conectados.")

class KnowledgeRag:
    """Adaptador opt-in: recuperacao extrativa publica, sem LLM/rede no atendimento."""
    def __init__(self, index):
        self.index = index

    def _retrieve(self, message):
        from app.rag.scope import retrieval_plan
        from app.rag.core import query_tokens, tokens
        market, query = retrieval_plan(message)
        if market is None:
            return {'status':'insufficient_evidence','candidates':[]}
        if market == 'BR':
            from app.rag.planning import retrieve_brazil
            return retrieve_brazil(self.index, message)
        return {'status':'insufficient_evidence','candidates':[]}

    @classmethod
    def from_directory(cls, directory):
        from pathlib import Path
        from app.rag.core import Index, load_snapshot
        from app.rag.fetch import SOURCES
        # Schema/hash/revisao falham explicitamente ao iniciar, nao ocultar corrupcao.
        files = sorted(Path(directory).glob('*.json'))
        if len(files) > 100:
            raise ValueError('Corpus acima do limite')
        return cls(Index([load_snapshot(path, SOURCES) for path in files]))

    @staticmethod
    def _suspicious(text):
        import re
        import unicodedata
        plain = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
        # Defesa limitada adicional, NAO detector completo de prompt injection.
        return bool(re.search(r'(ignore|desconsidere|esqueca).{0,60}(instrucoes|regras|sistema)|system\s*prompt|reveal.{0,30}(secret|prompt)|mostre.{0,30}(segredo|credencial)|\.env\b', plain))

    def responder(self, entrada, contexto):
        from app.service_policy import service_plan
        policy=service_plan(entrada.message)
        if policy.replies:
            replies=[r.texto for r in policy.replies]
            if not policy.message:
                return RespostaEspecialista(texto='\n\n'.join(replies),status=policy.replies[0].status,fontes=list(dict.fromkeys(f for r in policy.replies for f in r.fontes)),modo='extrativo')
            accepted=self.responder(Entrada(message=policy.message,user_id=entrada.user_id),contexto)
            return accepted.model_copy(update={'texto':accepted.texto+'\n\n'+'\n\n'.join(replies)})
        from app.rag.core import MAX_QUERY
        from app.rag.scope import retrieval_plan
        from app.propositions import knowledge_tasks
        # O original é inspecionado antes de decompor: nenhum país, instrução
        # suspeita ou limite pode desaparecer na reformulação das subconsultas.
        if len(entrada.message)>MAX_QUERY or self._suspicious(entrada.message):
            return self._single(entrada,contexto)
        tasks = knowledge_tasks(entrada.message, support_answered=bool(contexto))
        if not tasks:
            return self._single(entrada,contexto)
        market, _ = retrieval_plan(entrada.message)
        responses=[]
        labels={'information':'Pergunta','action':'Ação solicitada','migration':'Conta','decline':'Recusa',
                'commercial':'Condições comerciais','comparison':'Comparação','connectivity':'Conexão','advance':'Antecipação','link':'Link de Pagamento'}
        for kind,query in tasks:
            if kind not in {'action','migration'} and market!='BR':
                r=RespostaEspecialista(texto='Não tenho evidência suficiente para esse assunto no mercado solicitado.',status='sem_evidencia',modo='extrativo')
            else:
                # Composição documental: não multiplica chamadas LLM nem deixa
                # uma seleção parcial esconder outra intenção. Modo explícito.
                scoped_query=query
                r=KnowledgeRag._single(self,Entrada(message=scoped_query,user_id=entrada.user_id),())
            responses.append((labels[kind],r))
        lines=[];sources=[];statuses=[]
        for number,(label,r) in enumerate(responses):
            combined=list(dict.fromkeys(sources+r.fontes))
            line=label+': '+r.texto
            reserved=180*(len(responses)-number-1)
            if len(combined)>3 or sum(map(len,lines))+len(line)+2*len(responses)+reserved>4000:
                line=label+': As evidências excedem o limite desta resposta. Envie essa parte separadamente; não confirmei seu resultado.'
                statuses.append('limitado')
            else:
                sources=combined;statuses.append(r.status)
            lines.append(line)
        priority=('recusado','indisponivel','limitado','sem_evidencia','evidencias','simulado')
        return RespostaEspecialista(texto='\n\n'.join(lines),fontes=sources,
                                    status=next(s for s in priority if s in statuses),modo='extrativo')

    def _single(self, entrada, contexto):
        from app.rag.core import MAX_QUERY, evidence_text
        from app.brazil_scope import market_of, REDIRECT_BR, CLARIFY_BR
        market=market_of(entrada.message)
        if market.value in ('OUT','UNKNOWN'):
            return RespostaEspecialista(texto=REDIRECT_BR if market.value=='OUT' else CLARIFY_BR,status='limitado',modo='extrativo')
        def reply(text, status, fontes=None):
            return RespostaEspecialista(texto=str(text), presentation=list(text.parts) if isinstance(text,AnswerText) else [], status=status, fontes=fontes or [], modo='extrativo')
        if len(entrada.message) > MAX_QUERY:
            return reply('Para consultar as fontes, envie uma pergunta com ate 2000 caracteres. Sua entrada nao foi truncada.', 'limitado')
        if self._suspicious(entrada.message):
            return reply('Nao sigo instrucoes para alterar regras ou revelar credenciais. Envie uma duvida sobre os servicos Getnet.', 'recusado')
        from app.intents import request_facts
        facts = request_facts(entrada.message)
        from app.propositions import canonical, DECLINE
        import re
        original=canonical(entrada.message)
        if re.search(r'\b(?:senha|password|autenticacao|authentication|otp)\b',original) and re.search(r'\b(?:enviar|envio|compartilhar|send|share|fornecer|passar)\b',original):
            return reply('Não envie nem compartilhe senhas ou códigos de autenticação nesta conversa. Use somente o aplicativo ou canal oficial para autenticar; posso explicar uma configuração pública sem receber suas credenciais.', 'limitado')
        if facts.unsupported_action:
            return reply('Não disponho de ferramenta para transferir valores, contratar ou alterar serviços ou encaminhar atendimento. Nenhuma operação foi executada. Use o canal oficial para solicitar essa ação; não envie dados de autenticação aqui.', 'limitado')
        from app.intents import future_sales
        if future_sales(entrada.message):
            return reply('Não consigo prever o recebimento de vendas ainda não realizadas. A agenda demonstrativa contém somente vendas fictícias passadas; nenhum prazo individual ou comercial foi confirmado.', 'limitado')
        if facts.account_migration:
            return reply('Não tenho acesso à situação da sua conta para confirmar se houve migração. Um anúncio público não confirma uma migração na sua conta. Confira o estado e as condições no app ou Portal do Cliente; nenhuma alteração foi realizada por este assistente.', 'limitado')
        if DECLINE.search(original) and not facts.decline:
            return reply('Você não relatou uma recusa ativa nessa mensagem. Não consultei transações nem confirmei aprovações. Qual é a dúvida que deseja esclarecer?', 'limitado')
        from app.rag.core import query_tokens
        terms=query_tokens(entrada.message)
        decline = facts.decline
        # Normalizacao de intencao para consulta documental, nao diagnostico da transacao.
        result = self._retrieve(entrada.message)
        if result['status'] == 'unavailable':
            return reply('Fontes de conhecimento indisponiveis nesta tentativa.', 'indisponivel')
        if result['status'] == 'insufficient_evidence':
            from app.rag.quality import commercial_attribute
            attribute=commercial_attribute(entrada.message)
            if attribute:
                from app.request_plan import grounded_attribute_limit
                extra=' '.join(grounded_attribute_limit(entrada.message,[]))
                return reply(f'Não consigo confirmar {attribute} solicitado(a) nas fontes disponíveis. Consulte a oferta vigente no canal oficial Getnet; nenhum valor ou condição individual foi confirmado. '+extra, 'sem_evidencia')
            from app.request_plan import grounded_attribute_limit
            gaps=grounded_attribute_limit(entrada.message,[])
            return reply('Não encontrei evidência suficiente nas fontes locais para responder com segurança.'+(' '+' '.join(gaps) if gaps else ''), 'sem_evidencia')
        candidates = result['candidates']
        if any(self._suspicious(c['text']) or self._suspicious(c['title']) for c in candidates):
            return reply('O trecho recuperado precisa de revisao antes de ser apresentado.', 'sem_evidencia')
        from app.rag.quality import relevant_candidates, conflicting_rates
        from app.request_plan import without_declined_requests
        meaningful=without_declined_requests(entrada.message)
        candidates = relevant_candidates(entrada.message,candidates)
        if not candidates:
            from app.request_plan import grounded_attribute_limit
            gaps=grounded_attribute_limit(meaningful,[])
            return reply('Não encontrei evidência pertinente suficiente para essa pergunta.'+(' '+' '.join(gaps) if gaps else ''), 'sem_evidencia')
        if conflicting_rates(candidates):
            return reply('As fontes recuperadas apresentam taxas conflitantes para o mesmo escopo. Não consigo confirmar a taxa vigente; consulte a oferta aplicável no canal oficial. Nenhuma taxa foi confirmada.', 'sem_evidencia')
        from app.rag.guidance import reviewed_guidance
        from app.request_plan import grounded_attribute_limit
        missing=grounded_attribute_limit(entrada.message,candidates)
        guidance = reviewed_guidance(meaningful, candidates)
        if guidance is not None:
            missing=grounded_attribute_limit(meaningful,[{'text':guidance.text}])
        if guidance is not None and not (facts.fee and facts.entities & {'smart','classica'}):
            return reply(compose_notices(guidance.text,' '.join(missing) if missing else ''), 'sem_evidencia' if missing else 'evidencias', list(guidance.sources))
        from app.rag.quality import commercial_attribute, attribute_candidates
        attribute=commercial_attribute(entrada.message)
        if attribute:
            candidates=attribute_candidates(entrada.message,candidates)
            if not candidates:
                return reply(f'Não consigo confirmar {attribute} solicitado(a) nas fontes disponíveis. Um manual técnico não informa a oferta comercial aplicável. Consulte a oferta vigente no site oficial Getnet ou no app/Portal do Cliente; não consultei sua conta nem confirmei valores. '+ ' '.join(grounded_attribute_limit(entrada.message,[])), 'sem_evidencia')
        # Comparacao extrativa: mostrar fontes distintas, sem inferir ausencia de recurso.
        from app.rag.core import tokens
        if tokens(entrada.message) & {'difference','differences','compare','comparison','diferenca','diferencas','comparar','comparacao'}:
            selected=[]; seen=set()
            for candidate in candidates:
                if candidate['source'] not in seen:
                    selected.append(candidate);seen.add(candidate['source'])
                if len(selected)==2:break
            if len(selected)<2:
                return reply('Encontrei apenas uma fonte pertinente; nao ha evidencia suficiente para uma comparacao sustentada.', 'sem_evidencia')
            text='Trechos para comparacao, sem geracao por LLM. A ausencia de um recurso em um trecho nao significa que o produto nao o possui. Confirme modelo e edicao; nenhuma condicao comercial foi inferida.\n'
            text+='\n\n'.join(evidence_text(c)+'\nFonte: '+c['source']+'\nCaptura: '+c['captured_at'] for c in selected)
            if len(text)>4000:return reply('Evidencias excederam o limite; reformule a comparacao.', 'limitado')
            return reply(text,'evidencias',[c['source'] for c in selected])
        first = candidates[0]
        # The answer emits one excerpt: assess coverage of that excerpt, not a hidden candidate.
        missing=grounded_attribute_limit(entrada.message,[first])
        excerpt=evidence_text(first)
        text = ('Trecho da fonte oficial, sem geracao por LLM; confirme a aplicabilidade ao seu caso. '
                'Senhas somente no canal oficial ou no proprio dispositivo: nunca nesta conversa. Nenhuma configuracao ou operacao foi realizada pelo assistente.\n'
                + excerpt + '\nFonte: ' + first['source'] + '\nCaptura: ' + first['captured_at'])
        if decline:
            from app.rag.guidance import decline_followup
            text += '\nEsse trecho explica o status em geral, nao a causa desta transacao. ' + decline_followup(facts)
        if missing:text+='\n\n'+' '.join(missing)
        if len(text)>4000:return reply('Evidencias excederam o limite; reformule a pergunta.', 'limitado')
        return reply(text, 'sem_evidencia' if missing else 'evidencias', [first['source']])

class KnowledgeGenerated(KnowledgeRag):
    """Opt-in adicional: usa gerador injetado; dublê nao equivale a smoke real."""
    def __init__(self,index,generator):
        super().__init__(index)
        self.generator=generator
    def _single(self,entrada,contexto):
        # Reaproveita limites, abstencao e filtros antes de qualquer geracao.
        baseline=super()._single(entrada,contexto)
        if baseline.status != 'evidencias':return baseline
        from app.rag.generation import validated_draft, UnsupportedDraft, SensitiveEvidence
        from app.rag.fetch import SOURCES
        try:
            from app.rag.core import query_tokens
            terms=query_tokens(entrada.message)
            from app.intents import request_facts
            facts=request_facts(entrada.message)
            decline=facts.decline
            from app.rag.quality import relevant_candidates
            candidates=relevant_candidates(entrada.message,self._retrieve(entrada.message)['candidates'])
            answer,sources=validated_draft(self.generator,entrada.message,candidates)
            if self._suspicious(answer) or any(source not in SOURCES for source in sources):
                raise ValueError('Saida nao permitida')
            # Proibir solicitacoes explicitas de credenciais no texto gerado.
            from app.rag.core import tokens
            # Conservador: geracao nao deve conter credenciais nem orientacao para coleta.
            # Pode recusar avisos legitimos; nao e classificador semantico completo.
            if tokens(answer) & {'senha','senhas','password','passwords','passcode','pin','cvv','cvc','token','tokens','otp','secret','secrets','credencial','credenciais','credential','credentials'}:
                raise ValueError('Conteudo de credencial nao permitido na geracao')
            from app.rag.guidance import reviewed_guidance
            guidance = reviewed_guidance(entrada.message, candidates)
            if guidance is not None and (guidance.prefer_reviewed or not guidance.covers(answer)):
                # Seleção literal validada não obriga a exibir catálogos/anúncios.
                # O baseline só contém síntese revisada se URL, título e hash
                # completos conferem. Preservar modo extrativo e suas fontes.
                return baseline
            if decline:
                from app.rag.guidance import decline_followup
                answer += '\nEssa explicacao geral nao identifica a causa da sua transacao. ' + decline_followup(facts)
            return RespostaEspecialista(texto=answer, status='evidencias',fontes=sources,modo='gerado')
        except SensitiveEvidence:
            # Nunca entregar a citação sensível nem o fallback bruto: só uma
            # apresentação revisada cujo trecho completo/URL/hash ainda confere.
            from app.rag.guidance import reviewed_guidance
            if reviewed_guidance(entrada.message, candidates) is not None:
                return baseline
            return RespostaEspecialista(texto='Geracao indisponivel ou resposta nao validada. Nenhuma operacao foi confirmada.',
                                        status='indisponivel',modo='gerado')
        except UnsupportedDraft:
            # A sintese rejeitada nao e exibida; preservar evidencia e modo extrativo.
            return baseline
        except Exception:
            return RespostaEspecialista(texto='Geracao indisponivel ou resposta nao validada. Nenhuma operacao foi confirmada.',
                                        status='indisponivel',modo='gerado')

class KnowledgeWeb:
    """Descoberta pública pertinente, limitada a fontes oficiais Getnet."""
    def __init__(self,search,exchange=None,weather=None):
        # Parâmetros legados mantidos para compatibilidade; nunca chamados.
        self.search=search
    def responder(self,entrada,contexto):
        from app.service_policy import service_plan, official_result, source_market, reply
        policy=service_plan(entrada.message)
        if policy.replies and policy.message:
            accepted=self.responder(Entrada(message=policy.message,user_id=entrada.user_id),contexto)
            return accepted.model_copy(update={'texto':accepted.texto+'\n\n'+'\n\n'.join(r.texto for r in policy.replies)})
        if policy.replies:
            return RespostaEspecialista(texto='\n\n'.join(r.texto for r in policy.replies),status=policy.replies[0].status,fontes=list(dict.fromkeys(f for r in policy.replies for f in r.fontes)),modo='extrativo')
        from app.rag.web_search import validate_query
        from app.intents import classify
        import re
        if KnowledgeRag._suspicious(entrada.message):
            return reply('Não sigo pedidos para alterar regras ou revelar segredos.',status='recusado')
        if contexto or classify(entrada.message).receivables or classify(entrada.message).terminal or re.search(r'\b(meu|minha|meus|minhas|my|our|tenant|cliente|customer|conta|account)\b',entrada.message,re.I):
            return reply('Use somente uma pergunta pública, sem dados pessoais ou de conta.',status='recusado')
        try:
            query=validate_query(entrada.message)
            result=self.search.search(query)
        except ValueError:
            return reply('Consulta pública deve ter de 1 a 300 caracteres e não conter dados privados.',status='limitado')
        except Exception:
            return reply('Busca oficial indisponível nesta tentativa.',status='indisponivel',limitation_code='source_unavailable')
        if result['status']=='unavailable':
            return reply('Busca oficial indisponível nesta tentativa.',status='indisponivel',limitation_code='source_unavailable')
        from app.rag.general_web import relevant_result
        rows=[r for r in result['results'] if official_result(r) and relevant_result(query,r) and not KnowledgeRag._suspicious(r['snippet']+' '+r['title'])][:3]
        if not rows:
            return reply('Não encontrei fonte oficial pertinente suficiente para esse produto ou serviço da Getnet Brasil; não confirmei condições comerciais.',status='sem_evidencia')
        text='Fontes para atendimento Getnet Brasil; os trechos não confirmam regras da sua conta. Confira produto e condições na fonte:\n'
        text+='\n'.join('País/escopo: '+source_market(r['url'])+'. '+r['title']+': '+r['snippet']+' Fonte: '+r['url'] for r in rows)
        text+='\nConsulta: '+result['retrieved_at']
        if len(text)>4000:
            return reply('Resultados excedem o limite. Envie uma pergunta mais específica.',status='limitado')
        return RespostaEspecialista(texto=text,status='evidencias',fontes=[r['url'] for r in rows],modo='pesquisa')

class KnowledgeDispatch:
    """Corpus primeiro; web pertinente opt-in, sem fixtures ou histórico."""
    PREFIX='pesquise na web:'
    def __init__(self,local,web=None):
        self.local,self.web=local,web
    def responder(self,entrada,contexto):
        from app.service_policy import service_plan,reply
        message=entrada.message.strip()
        explicit=message.casefold().startswith(self.PREFIX)
        query=message[len(self.PREFIX):].strip() if explicit else message
        if KnowledgeRag._suspicious(message):
            return reply('Não sigo pedidos para alterar regras ou revelar segredos.',status='recusado')
        if explicit and (not query or len(query)>300):
            return reply('Consulta pública deve ter de 1 a 300 caracteres.',status='limitado')
        policy=service_plan(query)
        if policy.replies:
            if not policy.message:
                return RespostaEspecialista(texto='\n\n'.join(r.texto for r in policy.replies),status=policy.replies[0].status,fontes=list(dict.fromkeys(f for r in policy.replies for f in r.fontes)),modo='extrativo')
            local=self.local.responder(Entrada(message=policy.message,user_id=entrada.user_id),contexto)
            return local.model_copy(update={'texto':local.texto+'\n\n'+'\n\n'.join(r.texto for r in policy.replies)})
        if explicit:
            if contexto:
                return reply('Separe a pergunta pública do atendimento de suporte. Nenhum dado foi enviado à busca.',status='recusado')
            if self.web is None:
                return reply('Busca externa desativada nesta execução.',status='indisponivel',limitation_code='web_disabled')
            return self.web.responder(Entrada(message=query,user_id='public_query'),())
        local=self.local.responder(entrada,contexto)
        from app.rag.scope import retrieval_plan
        if local.status=='sem_evidencia' and self.web is not None and not contexto and retrieval_plan(query)[0] is not None:
            # O adaptador volta a validar privacidade, pertinência e fontes.
            return self.web.responder(Entrada(message=query,user_id='public_query'),())
        return local
