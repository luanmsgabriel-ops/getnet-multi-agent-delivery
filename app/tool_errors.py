"""Closed, sanitized read-tool failures. Never retains adapter exceptions/data."""
from typing import Literal
ToolErrorCode = Literal['tool_permission_denied','tool_invalid_result','tool_timeout','tool_provider_failure']
MESSAGES = {
 'tool_permission_denied': 'Consulta nao autorizada neste contexto. Nenhum resultado foi confirmado.',
 'tool_invalid_result': 'O retorno da consulta e incompleto ou invalido; nenhum dado dessa consulta foi confirmado.',
 'tool_timeout': 'A consulta excedeu o prazo de espera; nenhum resultado dessa consulta foi confirmado.',
 'tool_provider_failure': 'Consulta indisponivel; nenhum resultado dessa consulta foi confirmado.',
}
class ToolFailure(RuntimeError):
 def __init__(self, code: ToolErrorCode):
  if code not in MESSAGES: raise ValueError('Unknown tool failure')
  self.code=code
  super().__init__(MESSAGES[code])
 @property
 def blocked(self): return self.code=='tool_permission_denied'

def tool_failure(error):
 if isinstance(error,ToolFailure): return ToolFailure(error.code)
 if isinstance(error,PermissionError): return ToolFailure('tool_permission_denied')
 if isinstance(error,TimeoutError): return ToolFailure('tool_timeout')
 return ToolFailure('tool_provider_failure')
