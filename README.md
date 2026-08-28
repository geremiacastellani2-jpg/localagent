# Maggiordomo Locale

Un agente personale che gira **interamente sul tuo Mac**: chat locale, note,
promemoria, memoria a lungo termine e **vista** (il modello guarda attraverso la
camera e ti dice cosa vede). Modelli **ibridi** — Ollama in locale, OpenRouter in
cloud — tramite un'unica API OpenAI-compatibile.

> Fasi **1–2** completate. Architettura di riferimento completa (memoria a
> vettori, bus messaggi Matrix, WhatsApp/SMS/iMessage, riconoscimento volti/voce,
> scheduler proattivo): vedi il blueprint collegato in fondo.

## Cosa c'è già

- 💬 **Chat web locale** (`http://127.0.0.1:8765`) — l'interfaccia da cui parli.
- 👁️ **Vista** — attivi la camera nel browser e chiedi «cosa vedi?»: il frame
  viene mandato a un modello multimodale (VLM) e l'agente descrive scena e oggetti.
- 📅 **Calendario** — crea, sposta ed elenca eventi; archivio locale che si
  **sincronizza con CalDAV** (iCloud/Google/Fastmail) se configurato.
- 🧠 **Memoria** livello 1 — fatti durevoli su di te, salvati e richiamati.
- 🗒️ **Note** e ⏰ **promemoria** su archivio locale SQLite.
- 🔀 **Router ibrido** — stesso codice per locale e cloud, cambia solo il `base_url`.

## Requisiti

- **Python 3.11+**
- **Ollama** (per il tier locale): <https://ollama.com>
  ```bash
  ollama pull qwen2.5           # modello di chat locale
  ollama pull llama3.2-vision   # modello di vista locale (VLM)
  ```
- **Chiave OpenRouter** (per il tier cloud, facoltativa): <https://openrouter.ai/keys>

Serve almeno uno dei due tier. Con `DEFAULT_TIER=auto` usa il cloud se trova la
chiave, altrimenti il locale.

## Avvio

```bash
cp .env.example .env      # compila OPENROUTER_API_KEY e/o configura Ollama
./run.sh                  # crea la venv, installa, avvia il server
```

Apri **http://127.0.0.1:8765** nel browser (sul Mac). Scrivi in italiano; premi
📷 per attivare la camera e poi 👁️ (o chiedi «cosa vedi?»).

## Come funziona la vista

Il browser cattura il frame corrente della webcam (`getUserMedia`), lo riduce e lo
invia insieme al messaggio. Il server lo tiene in memoria per la sessione; quando
l'agente chiama lo strumento `look`, l'immagine va al modello multimodale. **Il
video grezzo non viene mai salvato su disco** e, se usi il tier locale per la
vista (`VISION_TIER=local`), non lascia mai il Mac.

Senza UI, c'è un fallback lato server via OpenCV (`pip install opencv-python`).

## Come funziona il calendario

L'archivio locale SQLite è la **fonte di verità**: crei e sposti eventi lì, sempre
e comunque. Se imposti le variabili `CALDAV_*` nel `.env`, ogni modifica viene
**rispecchiata sul server CalDAV** (iCloud/Google/Fastmail) e `sync_calendar` tira
giù gli eventi esistenti nell'archivio locale. Senza CalDAV, il calendario resta
pienamente funzionante ma solo sul Mac.

Le date si passano in **ISO 8601**; per "domani alle 15" l'agente chiama prima
`get_current_time` e calcola la data giusta. Nella chat trovi il pulsante 📅 per
l'agenda di oggi.

## Struttura

```
agent/
  config.py        impostazioni + routing dei modelli
  llm.py           client OpenAI-compatibile (Ollama / OpenRouter)
  core.py          loop dell'agente con tool-calling
  db.py            SQLite: note, promemoria, fatti, eventi
  calendar_store.py archivio locale eventi (fonte di verità)
  caldav_sync.py   sincronizzazione con server CalDAV
  state.py         ultimo frame camera per sessione (in memoria)
  tools/           note, promemoria, memoria, calendario, vista, ora
  perception/      cattura frame camera (fallback headless)
  server.py        FastAPI: /chat + chat web
web/
  index.html       la chat locale (con camera e agenda)
```

## Sicurezza

- Gira solo su `127.0.0.1` (nessun servizio esposto).
- I segreti stanno in `.env` (git-ignored); i dati in `data/` (git-ignored).
- La biometria/immagini restano locali se usi il tier locale per la vista.
- Per l'accesso da remoto usa una VPN privata (es. Tailscale), mai una porta aperta.

## Prossime fasi

Memoria a vettori (sqlite-vec), email, bus messaggi Matrix con bridge
WhatsApp/SMS/iMessage, riconoscimento volti/voce e scheduler proattivo.
Vedi il blueprint dell'architettura per il percorso completo.
