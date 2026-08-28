"""Maggiordomo Locale — un agente personale che gira sul tuo Mac.

Sottopacchetti:
    config      impostazioni e routing dei modelli
    llm         client OpenAI-compatibile (Ollama locale / OpenRouter cloud)
    core        loop dell'agente con tool-calling
    tools       le capacità (note, promemoria, memoria, vista, ora)
    perception  cattura dei frame dalla camera
    server      API FastAPI + chat web locale
"""

__version__ = "0.1.0"
