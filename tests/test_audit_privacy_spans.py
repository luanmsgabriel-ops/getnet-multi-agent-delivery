"""Compositional privacy regressions for audit 71; synthetic data, no network.

The spy exercises the real service/interpreter/store boundary. Captured log
records simulate downstream payload/state/response logging, not a production
request logger or a real provider.
"""
import copy
import io
import itertools
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.context_service import ContextService
from app.context_solo import SoloInterpreter
from app.context_store import Store
from app.privacy import clean_message


class PayloadSpy:
    def __init__(self):
        self.calls = []

    def complete(self, system, payload, schema):
        self.calls.append(copy.deepcopy(payload))
        if 'disputed' in payload:
            return {group: [
                {'index': i, 'verdict': 'supported', 'origin': 'customer'}
                for i in payload['disputed'][group]
            ] for group in ('devices', 'observations')}
        message = payload['message']
        refs = list(payload['state']['devices'])
        devices = []
        if 'A920' in message and not refs:
            refs = ['new1']
            devices = [{'ref': 'new1', 'label': 'A920', 'store': '',
                        'quote': message}]
        observations = []
        if 'não conecta' in message and refs:
            observations = [{'entity': refs[0], 'incident': '', 'field': 'symptom',
                             'value': 'não conecta', 'status': 'asserted',
                             'origin': 'customer', 'scope': 'entity',
                             'quote': message}]
        return {'devices': devices, 'observations': observations,
                'requests': [{'kind': 'summary', 'topic': 'other',
                              'entities': refs, 'quote': message}],
                'focus': refs, 'resolve_pending': []}


class PrivacySpans(unittest.TestCase):
    def assert_redacted(self, text, secrets, retained):
        safe, changed = clean_message(text)
        self.assertTrue(changed, text)
        for secret in secrets:
            self.assertNotIn(secret, safe)
        for piece in retained:
            self.assertIn(piece, safe)
        self.assertEqual(clean_message(safe), (safe, False))
        return safe

    def test_audit_s33_natural_disclosure(self):
        self.assert_redacted('Minha senha do WiFi SYN_NATURAL_73. A920 não conecta.',
                             ['SYN_NATURAL_73'], ['A920', 'não conecta'])

    def test_audit_s06_benign_network_name(self):
        text = 'Minha rede chama-se Senha Livre e a maquininha A920 não conecta.'
        self.assertEqual(clean_message(text), (text, False))

    def test_audit_s34_comma_starts_support_clause(self):
        self.assert_redacted('A senha é SYN_COMMA_84, minha A920 não conecta.',
                             ['SYN_COMMA_84'], ['minha A920 não conecta'])

    def test_qualifier_connector_and_clause_composition(self):
        heads = ('Minha senha', 'Minha senha do Wi-Fi', 'Minha senha da rede',
                 'A senha de acesso', 'Meu PIN', 'O código recebido por SMS',
                 'My password', 'My WiFi password', 'My verification code',
                 'My password for the network')
        connectors = (' ', ': ', ' = ', ' é ', ' is ', ' igual a ')
        clauses = (', minha A920 não conecta.', '; A920 não conecta.',
                   '. A920 não conecta.', ' e minha A920 não conecta.',
                   ' and my A920 is not connecting.')
        for head, connector, clause in itertools.product(heads, connectors, clauses):
            with self.subTest(head=head, connector=connector, clause=clause):
                self.assert_redacted(head + connector + 'SYN_COMPOSE_62' + clause,
                                     ['SYN_COMPOSE_62'], [clause])

    def test_quoted_multiword_and_punctuation_values(self):
        values = ('SYN_A SYN_B', 'SYN_A, SYN_B', 'SYN_A.ç!', 'incorrect', 'no aparelho')
        for value, quotes in itertools.product(values, (('"', '"'), ('“', '”'), ("'", "'"))):
            text = 'Minha senha do WiFi ' + quotes[0] + value + quotes[1]
            text += ', minha A920 não conecta.'
            with self.subTest(value=value, quotes=quotes):
                self.assert_redacted(text, [value], ['minha A920 não conecta'])

    def test_unquoted_value_does_not_stop_at_internal_punctuation(self):
        for value in ('SYN.a.b', 'SYN!part?part', 'SYN,part', 'SYN_ALPHA SYN_BRAVO'):
            with self.subTest(value=value):
                self.assert_redacted('My password ' + value + '; my terminal is offline.',
                                     [value], ['my terminal is offline'])

    def test_multiple_disclosures_and_issue_in_either_order(self):
        for left, right in itertools.product(
                ('Minha senha SYN_FIRST_11', 'My password is SYN_FIRST_11'),
                ('password SYN_SECOND_22', 'token = SYN_SECOND_22')):
            for clause in ('A920 não conecta. ', ''):
                message = clause + left + ' e ' + right + ', minha A920 não conecta.'
                self.assert_redacted(message, ['SYN_FIRST_11', 'SYN_SECOND_22'],
                                     ['minha A920 não conecta'])

    def test_network_names_with_authentication_words_are_not_values(self):
        for prefix, name, suffix in itertools.product(
                ('Minha rede chama-se ', 'Minha rede se chama ', 'The network is called ',
                 'The SSID name is '),
                ('Senha Livre', 'Password Guest', 'Token Cafe', 'PIN Aberto'),
                (' e a maquininha A920 não conecta.', ', my A920 is offline.')):
            text = prefix + name + suffix
            with self.subTest(text=text):
                self.assertEqual(clean_message(text), (text, False))

    def test_network_name_does_not_hide_later_real_disclosure(self):
        for separator in ('; ', '. ', ' e minha ', ', minha ', ' and my ', ' e ', ', ', ' and '):
            text = 'Minha rede chama-se Senha Livre' + separator
            text += 'senha do WiFi SYN_AFTER_NAME_55, minha A920 não conecta.'
            self.assert_redacted(text, ['SYN_AFTER_NAME_55'],
                                 ['Senha Livre', 'minha A920 não conecta'])

    def test_states_lengths_and_device_instructions_are_preserved(self):
        texts = (
            'A senha é incorreta.', 'Minha senha está incorreta.', 'Minha senha está errada.',
            'My password is incorrect.', 'My password is not accepted by the terminal.',
            'Minha A920 não conecta. O Wi-Fi é aberto, sem senha.',
            'A920 is offline; the network is open without a password.',
            'A senha é de seis dígitos ou oito?', 'O PIN é de 4 dígitos.',
            'A senha é digitada no aparelho.', 'Digite a senha no próprio aparelho.',
            'Não envie a senha no chat; digite no aparelho.',
            'Onde digito a senha do Wi-Fi?', 'Type your password on the device.',
            'Ainda não digitei a senha no aparelho.', 'Agora digitei a senha no aparelho.',
            'Minha senha não funciona; A920 não conecta.',
            'My password was entered on the device.',
            'Não apareceu pedido de senha na minha tela.',
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(clean_message(text), (text, False))

    def test_explicit_passphrases_with_prepositions_are_values(self):
        for head, value in (('Minha senha é ', 'para sempre'),
                            ('My password is ', 'in the clouds'),
                            ('My password = ', 'on a summer day')):
            self.assert_redacted(head + value + '; A920 não conecta.',
                                 [value], ['A920 não conecta'])

    def test_clause_subjects_do_not_depend_on_model_names(self):
        for clause in (', a Smart não conecta.', ', a impressora não imprime.',
                       ', preciso conectar minha A920.', ', the reader is offline.',
                       ', a QX123 não conecta.'):
            self.assert_redacted('Minha senha SYN_CLAUSE_83' + clause,
                                 ['SYN_CLAUSE_83'], [clause])

    def test_independent_multilingual_disclosures_are_now_regressions(self):
        cases = (
            ('minha credencial de Wi-Fi é a seguinte: «SYNTH-P1-Quartz!47»', 'SYNTH-P1-Quartz!47'),
            ('el PIN para entrar es SYNTH-P2-Lima!62', 'SYNTH-P2-Lima!62'),
            ('my Wi-Fi passphrase reads SYNTH-P3-Cedar!83', 'SYNTH-P3-Cedar!83'),
        )
        for disclosure, secret in cases:
            with self.subTest(disclosure=disclosure):
                self.assert_redacted(disclosure + '; minha A920 não conecta.',
                                     [secret], ['minha A920 não conecta'])

    def test_multilingual_heads_qualifiers_and_announcements_compose(self):
        families = (
            (('Minha credencial de Wi-Fi', 'A credencial de acesso'),
             (' ', ' é ', ' é a seguinte: ', ': ')),
            (('My Wi-Fi passphrase', 'The network passphrase', 'My passphrase for login'),
             (' ', ' reads ', ' is the following: ', ' is as follows: ')),
            (('El PIN para entrar', 'Mi clave de acceso', 'El código de autenticación'),
             (' ', ' es ', ' es la siguiente: ', ': ')),
        )
        for heads, connectors in families:
            for head, connector, quoted in itertools.product(heads, connectors, (False, True)):
                value = 'SYN_MULTILINGUAL_93'
                literal = '«' + value + '. with punctuation! »' if quoted else value
                with self.subTest(head=head, connector=connector, quoted=quoted):
                    self.assert_redacted(head + connector + literal + ', minha A920 não conecta.',
                                         [value], ['minha A920 não conecta'])

    def test_multilingual_instructions_states_and_network_names_remain(self):
        texts = (
            'A credencial é digitada no próprio aparelho.',
            'Digite a credencial no dispositivo.', 'Onde digito a credencial de Wi-Fi?',
            'My Wi-Fi passphrase is incorrect.', 'Type the passphrase on the device.',
            'El PIN para entrar es incorrecto.', 'Escriba el PIN en el dispositivo.',
            'El PIN es introducido en el terminal.', 'Mi contraseña está incorrecta.',
            'A rede é aberta, sem credencial.', 'The network is open without a passphrase.',
            'Minha rede chama-se Credencial Livre e a maquininha A920 não conecta.',
            'The network is called Passphrase Guest and my A920 is offline.',
            'Mi red se llama PIN Libre, el terminal no conecta.',
            'Mi red se llama Clave Libre, el terminal no conecta.',
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(clean_message(text), (text, False))

    def test_multilingual_network_name_does_not_hide_disclosure(self):
        for message in (
            'Minha rede chama-se Credencial Livre e credencial SYN_NAMED_94',
            'The network is called Passphrase Guest and passphrase reads SYN_NAMED_94',
            'Mi red se llama PIN Libre y PIN para entrar es SYN_NAMED_94',
        ):
            self.assert_redacted(message + '; A920 não conecta.',
                                 ['SYN_NAMED_94'], ['A920 não conecta'])

    def test_multilingual_disclosures_do_not_enter_simulated_surfaces(self):
        disclosures = (
            ('minha credencial de Wi-Fi é a seguinte: «SYNTH-P1-Quartz!47»', 'SYNTH-P1-Quartz!47'),
            ('el PIN para entrar es SYNTH-P2-Lima!62', 'SYNTH-P2-Lima!62'),
            ('my Wi-Fi passphrase reads SYNTH-P3-Cedar!83', 'SYNTH-P3-Cedar!83'),
        )
        with tempfile.TemporaryDirectory() as directory:
            spy = PayloadSpy()
            service = ContextService(Store(Path(directory) / 'state.db'), SoloInterpreter(spy))
            sid = service.create('privacy_multilingual_synthetic')
            captured = []
            with patch('socket.create_connection', side_effect=AssertionError('No network')), \
                 patch('socket.socket.connect', side_effect=AssertionError('No network')):
                for disclosure, secret in disclosures:
                    result = service.step('privacy_multilingual_synthetic', sid,
                                          disclosure + '; A920 não conecta.')
                    self.assertEqual(result['mode'], 'semantic_interpretation_reviewed_response')
                    captured.append({'response': result, 'payloads': copy.deepcopy(spy.calls),
                                     'memory': service.state('privacy_multilingual_synthetic', sid)})
            simulated_log = json.dumps(captured, ensure_ascii=False)
            with service.store.connection() as database:
                persisted = database.execute('SELECT state FROM sessions').fetchone()[0]
            for _, secret in disclosures:
                self.assertNotIn(secret, simulated_log)
                self.assertNotIn(secret, persisted)
            self.assertIn('A920', simulated_log)
            self.assertIn('não conecta', simulated_log)


    def test_coordinated_english_clause_reaches_payload_and_memory(self):
        cases = (
            ('DX8000', ', and the DX8000 at checkout still refuses every card transaction even though the internet works.'),
            ('DX8000', ' and the DX8000 at checkout still refuses every card transaction even though the internet works.'),
            ('QX77', ', and the QX77 near reception already stopped accepting cards.'),
            ('QX77', ' and the QX77 near reception already stopped accepting cards.'),
        )
        for model, suffix in cases:
            with self.subTest(model=model, suffix=suffix), tempfile.TemporaryDirectory() as directory:
                secret = 'SYNTH-P3-Cedar!83'
                message = 'my Wi-Fi passphrase reads ' + secret + suffix
                self.assert_redacted(message, [secret], [suffix])

                class ClauseSpy(PayloadSpy):
                    def complete(self, system, payload, schema):
                        self.calls.append(copy.deepcopy(payload))
                        if 'disputed' in payload:
                            return {group: [{'index': i, 'verdict': 'supported',
                                             'origin': 'customer'} for i in payload['disputed'][group]]
                                    for group in ('devices', 'observations')}
                        quote = payload['message']
                        return {'devices': [{'ref': 'new1', 'label': model, 'store': '', 'quote': quote}],
                                'observations': [{'entity': 'new1', 'incident': '', 'field': 'symptom',
                                                  'value': suffix.lstrip(', '), 'status': 'asserted',
                                                  'origin': 'customer', 'scope': 'entity', 'quote': quote}],
                                'requests': [{'kind': 'summary', 'topic': 'other',
                                              'entities': ['new1'], 'quote': quote}],
                                'focus': ['new1'], 'resolve_pending': []}

                spy = ClauseSpy()
                service = ContextService(Store(Path(directory) / 'state.db'), SoloInterpreter(spy))
                sid = service.create('english_clause_synthetic')
                with patch('socket.create_connection', side_effect=AssertionError('No network')), \
                     patch('socket.socket.connect', side_effect=AssertionError('No network')):
                    result = service.step('english_clause_synthetic', sid, message)
                self.assertEqual(result['mode'], 'semantic_interpretation_reviewed_response')
                self.assertIn(suffix, spy.calls[0]['message'])
                self.assertEqual(result['state']['devices']['new1']['label'], model)
                self.assertTrue(any(f['value'] == suffix.lstrip(', ')
                                    for f in result['state']['facts'].values()))
                self.assertNotIn(secret, json.dumps(spy.calls) + json.dumps(result))

    def test_english_and_inside_values_or_benign_guidance_is_not_a_clause_cut(self):
        for value in ('SYN_ALPHA and SYN_BRAVO', 'sunrise and warm sunsets',
                      '«SYN_ALPHA and the device still refuses SYN_BRAVO»'):
            self.assert_redacted('My passphrase reads ' + value + '; A920 não conecta.',
                                 ['SYN_ALPHA', 'SYN_BRAVO'] if 'SYN_ALPHA' in value else [value],
                                 ['A920 não conecta'])
        for text in (
            'My passphrase is incorrect and the DX8000 at checkout still refuses cards.',
            'Type the passphrase on the device and the terminal will reconnect.',
            'The network is called Passphrase Guest and the DX8000 at checkout still refuses cards.',
        ):
            self.assertEqual(clean_message(text), (text, False))

    def test_ex21_dash_clause_is_idempotent_and_retains_supported_facts(self):
        clause = 'a A920 do estoque no Brasil continua offline.'
        heads = ('No terminal Getnet, o código de autenticação recebido por SMS é ',
                 'Meu código de acesso por SMS é ')
        for head, separator in itertools.product(heads, (' — ', '.— ', ' – ')):
            with self.subTest(head=head, separator=separator), tempfile.TemporaryDirectory() as directory:
                secret = 'SYNTH-E1-Ruby#29'
                message = head + '«' + secret + '»' + separator + clause
                self.assert_redacted(message, [secret], [separator + clause])

                class FactsSpy(PayloadSpy):
                    def complete(self, system, payload, schema):
                        self.calls.append(copy.deepcopy(payload))
                        if 'disputed' in payload:
                            return {group: [{'index': i, 'verdict': 'supported',
                                             'origin': 'customer'} for i in payload['disputed'][group]]
                                    for group in ('devices', 'observations')}
                        quote = payload['message']
                        observations = [
                            {'entity': 'new1', 'incident': '', 'field': field,
                             'value': value, 'status': 'asserted', 'origin': 'customer',
                             'scope': 'entity', 'quote': quote}
                            for field, value in (('country', 'Brasil'), ('symptom', 'offline'))]
                        return {'devices': [{'ref': 'new1', 'label': 'A920',
                                             'store': 'estoque', 'quote': quote}],
                                'observations': observations,
                                'requests': [{'kind': 'summary', 'topic': 'other',
                                              'entities': ['new1'], 'quote': quote}],
                                'focus': ['new1'], 'resolve_pending': []}

                spy = FactsSpy()
                service = ContextService(Store(Path(directory) / 'state.db'), SoloInterpreter(spy))
                sid = service.create('dash_clause_synthetic')
                with patch('socket.create_connection', side_effect=AssertionError('No network')), \
                     patch('socket.socket.connect', side_effect=AssertionError('No network')):
                    result = service.step('dash_clause_synthetic', sid, message)
                self.assertEqual(result['mode'], 'semantic_interpretation_reviewed_response')
                self.assertFalse(result['validation']['rejected'])
                self.assertEqual(result['state']['devices']['new1']['label'], 'A920')
                self.assertEqual(result['state']['devices']['new1']['store'], 'estoque')
                values = {f['field']: f['value'] for f in result['state']['facts'].values()}
                self.assertEqual(values['country'], 'Brasil')
                self.assertEqual(values['symptom'], 'offline')
                self.assertNotIn(secret, json.dumps(spy.calls) + json.dumps(result))

    def test_marker_and_dash_do_not_authorize_arbitrary_unredacted_value(self):
        for separator in (' — ', '.— ', ' – ', ' '):
            self.assert_redacted('Minha senha [credencial removida]' + separator + 'SYN_UNSAFE_96.',
                                 ['SYN_UNSAFE_96'], ['Minha senha'])

    def test_labels_survive_redaction_for_downstream_search_guards(self):
        for label in ('senha', 'password', 'token', 'PIN'):
            safe = self.assert_redacted('Pesquise Getnet ' + label + ' SYN_WEB_61.',
                                        ['SYN_WEB_61'], [label])
            self.assertIn('[credencial removida]', safe)

    def test_device_instructions_containing_values_are_disclosures(self):
        for message in ('Digite a senha SYN_TYPED_92; A920 não conecta.',
                        'Type your password SYN_TYPED_92; A920 não conecta.'):
            self.assert_redacted(message, ['SYN_TYPED_92'], ['A920 não conecta'])

    def test_marker_cannot_hide_unsanitized_suffix(self):
        self.assert_redacted('Minha senha [credencial removida] SYN_TRAIL_58.',
                             ['SYN_TRAIL_58'], ['Minha senha'])

    def test_conjunction_without_value_preserves_support_clause(self):
        for message in ('Não sei a senha e minha A920 não conecta.',
                        'Digite a senha e a maquininha A920 deve conectar.'):
            self.assertEqual(clean_message(message), (message, False))

    def test_multiturn_payload_memory_response_and_simulated_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            spy = PayloadSpy()
            service = ContextService(Store(Path(directory) / 'state.db'), SoloInterpreter(spy))
            sid = service.create('privacy_synthetic')
            log = io.StringIO()
            logger = logging.Logger('privacy_test')
            logger.addHandler(logging.StreamHandler(log))
            secrets = ('SYN_TURN_ONE_63', 'SYN_TURN_TWO_74')
            messages = (
                'Minha senha do WiFi ' + secrets[0] + '. A920 não conecta.',
                'A senha correta é ' + secrets[1] + ', minha A920 não conecta.',
                'Minha rede chama-se Senha Livre e a maquininha A920 não conecta.',
                'Resuma meu aparelho.',
            )
            with patch('socket.create_connection', side_effect=AssertionError('No network')), \
                 patch('socket.socket.connect', side_effect=AssertionError('No network')):
                for message in messages:
                    result = service.step('privacy_synthetic', sid, message)
                    self.assertEqual(result['mode'], 'semantic_interpretation_reviewed_response')
                    state = service.state('privacy_synthetic', sid)
                    logger.info(json.dumps({'payloads': spy.calls, 'response': result,
                                            'memory': state}, ensure_ascii=False))
            wire = json.dumps(spy.calls, ensure_ascii=False)
            state = service.state('privacy_synthetic', sid)
            for surface in (wire, json.dumps(state, ensure_ascii=False), log.getvalue()):
                for secret in secrets:
                    self.assertNotIn(secret, surface)
            with service.store.connection() as database:
                stored = database.execute('SELECT state FROM sessions').fetchone()[0]
            for secret in secrets:
                self.assertNotIn(secret, stored)
            self.assertEqual(state['devices']['new1']['label'], 'A920')
            self.assertTrue(any(f['value'] == 'não conecta' for f in state['facts'].values()))
            for call in spy.calls:
                self.assertNotIn('SYN_TURN_', json.dumps(call))
            self.assertIn('Senha Livre', wire)
            self.assertTrue(spy.calls[-1]['state']['devices'])
            self.assertIn('Não envie senhas', log.getvalue())

    def test_provider_failure_uses_safe_message_and_preserves_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            spy = PayloadSpy()
            service = ContextService(Store(Path(directory) / 'state.db'), SoloInterpreter(spy))
            sid = service.create('privacy_synthetic')
            service.step('privacy_synthetic', sid, 'A920 não conecta.')
            before = service.state('privacy_synthetic', sid)
            with patch.object(spy, 'complete', side_effect=TimeoutError('synthetic provider')), \
                 patch.object(service, '_core', return_value=('Fallback público.', [], [])) as core:
                result = service.step('privacy_synthetic', sid,
                                      'Minha senha do WiFi SYN_FAILED_85, minha A920 não conecta.')
            self.assertEqual(result['mode'], 'fallback_extractive')
            self.assertEqual(service.state('privacy_synthetic', sid), before)
            self.assertNotIn('SYN_FAILED_85', json.dumps(core.call_args.args))
            self.assertIn('A920 não conecta', core.call_args.args[0])
            self.assertNotIn('SYN_FAILED_85', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
