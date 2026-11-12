"""Configuração compartilhada: sem retries do Agent nem do transporte SDK."""


def model_without_sdk_retries(model):
    from pydantic_ai.models import infer_model
    from pydantic_ai.models.openrouter import OpenRouterModel

    resolved = infer_model(model)
    if isinstance(resolved, OpenRouterModel):
        # Configurar antes da primeira chamada, inclusive para modelos injetados.
        resolved.provider.client.max_retries = 0
    return resolved
