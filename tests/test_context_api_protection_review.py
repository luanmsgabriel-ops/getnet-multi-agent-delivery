import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.context_store import Conflict, Store
from app.context_service import ContextService
from app.context_state import clean_message


class ApiProtectionReview(unittest.TestCase):
    def client(self):
        # Importing the module must not create persistent files during this focused test.
        with patch('app.context_store.Store'):
            from app.context_api import create_app
            service = MagicMock()
            return TestClient(create_app(service=service), raise_server_exceptions=False), service

    def test_blank_context_is_client_error(self):
        client, service = self.client()
        for message in ('', '   ', '\n\t'):
            with self.subTest(message=message):
                result = client.post('/context/chat', json={'message': message, 'user_id': 'cliente1988'})
                self.assertEqual(result.status_code, 422)
        service.create.assert_not_called()
        service.step.assert_not_called()

    def test_reset_errors_are_controlled(self):
        client, service = self.client()
        for error, code in ((PermissionError('private detail'), 403), (Conflict('private detail'), 409), (ValueError('private detail'), 503)):
            service.reset.side_effect = error
            result = client.post('/context/reset', json={'message': 'reset', 'user_id': 'cliente1988', 'session_id': 's' * 24})
            self.assertEqual(result.status_code, code)
            self.assertNotIn('private detail', result.text)
            self.assertIn('detail', result.json())

    def test_alphabetic_and_english_credentials_removed(self):
        for message, secret in (('Minha senha é segredo. Como configurar Wi-Fi?', 'segredo'), ('A senha é exemplo. Como configurar Wi-Fi?', 'exemplo'), ('My password is example123. How to connect?', 'example123'), ('Meu token é abcdef. Como funciona Link?', 'abcdef')):
            with self.subTest(message=message):
                safe, redacted = clean_message(message)
                self.assertTrue(redacted)
                self.assertNotIn(secret, safe)
                self.assertIn('?', safe)

    def test_credential_instructions_not_disclosures(self):
        for message in ('A senha é digitada no aparelho.', 'A senha é necessária?', 'My password is incorrect.', 'Onde digito a senha do Wi-Fi?'):
            self.assertEqual(clean_message(message), (message, False))

    def test_wifi_market_guard_precedes_retrieval(self):
        service = ContextService.__new__(ContextService)
        service.local = MagicMock()
        state = Store.empty()
        state['devices'] = {'a': {'label': 'Smart'}}
        state['context'] = {'country': {'value': 'Chile', 'origin': 'customer', 'status': 'asserted'}}
        answer, sources = service._wifi(state, 'a')
        self.assertIn('Getnet Brasil', answer)
        self.assertNotIn('Procurar Redes', answer)
        self.assertEqual(sources, [])
        service.local._retrieve.assert_not_called()
        state['context']['country']['status'] = 'uncertain'
        answer, sources = service._wifi(state, 'a')
        self.assertIn('Brasil?', answer)
        self.assertEqual(sources, [])

    def test_wifi_entity_country_overrides_conversation(self):
        service = ContextService.__new__(ContextService)
        service.local = MagicMock()
        state = Store.empty()
        state['context'] = {'country': {'value': 'Brasil', 'origin': 'customer', 'status': 'asserted'}}
        state['facts'] = {'country': {'entity': 'a', 'field': 'country', 'incident': '', 'subject': 'device', 'value': 'Chile', 'origin': 'customer', 'status': 'asserted'}}
        answer, sources = service._wifi(state, 'a')
        self.assertIn('Getnet Brasil', answer)
        self.assertEqual(sources, [])
        service.local._retrieve.assert_not_called()

if __name__ == '__main__':
    unittest.main()
