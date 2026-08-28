# Maggiordomo Locale

Un agente personale che gira **interamente sul tuo Mac**: chat locale, note,
promemoria, memoria a lungo termine e **vista** (il modello guarda attraverso la
camera e ti dice cosa vede). Modelli **ibridi** — Ollama in locale, OpenRouter in
cloud — tramite un'unica API OpenAI-compatibile.

> Fasi **1–3** completate. Architettura di riferimento completa (bus messaggi
> Matrix, WhatsApp/SMS/iMessage, riconoscimento volti/voce, scheduler proattivo):
> vedi il blueprint collegato in fondo.

## Cosa c'è già

- 💬 **Chat web locale** (`http://127.0.0.1:8765`) — l'interfaccia da cui parli.
- 👁️ **Vista dal vivo** — la camera è un feed live: il browser riconosce gli
  oggetti in tempo reale (bounding box) e l'agente sa cosa c'è in vista *adesso*
  (`current_view`) o ne dà una descrizione dettagliata con un VLM (`look`).
- 📅 **Calendario** — crea, sposta ed elenca eventi; archivio locale che si
  **sincronizza con CalDAV** (iCloud/Google/Fastmail) se configurato.
- 🧠 **Memoria a due livelli** — fatti strutturati (livello 1) + **richiamo
  semantico** per significato con embedding locali (livello 2).
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

## Come funziona la vista (dal vivo)

La camera è un **feed live**, non una foto singola:

1. Nel browser gira un rilevatore di oggetti in tempo reale (TensorFlow.js
   coco-ssd): disegna i riquadri e tiene aggiornato l'elenco di cosa è in vista.
2. Ogni ~1,2 s il browser invia al server il frame corrente e gli oggetti
   rilevati (`POST /frame`). Il server tiene solo l'**ultimo** frame in memoria.
3. L'agente ha due strumenti: `current_view` (cosa c'è adesso, istantaneo, senza
   modello) e `look` (descrizione ricca del frame corrente tramite VLM).

**I modelli locali riescono a vedere le immagini?** Sì, ma solo quelli
*multimodali* (llava, `llama3.2-vision`, qwen2-vl, moondream…). Per il tier
locale usiamo l'**API nativa di Ollama** (`/api/chat` con `images`), che accetta
le immagini in modo affidabile. La qualità di un VLM locale è più bassa di quella
cloud (testo piccolo, dettagli): per questo `VISION_TIER` ti fa scegliere —
`local` per privacy totale, `cloud` per il riconoscimento migliore.

**Il video grezzo non viene mai salvato su disco.** Con `VISION_TIER=local` le
immagini non lasciano mai il Mac. Senza UI, c'è un fallback lato server via
OpenCV (`pip install opencv-python`).

## Come funziona la memoria

- **Livello 1 — fatti:** righe esplicite e modificabili (`remember_fact`).
- **Livello 2 — semantico:** ogni fatto viene indicizzato come embedding locale
  (`nomic-embed-text` via Ollama) e `recall` cerca per **significato** (coseno).
  Se Ollama non è attivo, `recall` ricade sulla ricerca per parole chiave, e
  `reindex_memory` ricostruisce l'indice quando gli embedding tornano disponibili.

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
  db.py            SQLite: note, promemoria, fatti, eventi, vettori
  calendar_store.py archivio locale eventi (fonte di verità)
  caldav_sync.py   sincronizzazione con server CalDAV
  semantic_memory.py indice vettoriale + embedding locali (memoria livello 2)
  state.py         frame live e oggetti rilevati, per sessione (in memoria)
  tools/           note, promemoria, memoria, calendario, vista, ora
  perception/      cattura frame camera (fallback headless)
  server.py        FastAPI: /chat + /frame + chat web
web/
  index.html       la chat locale (camera live + rilevamento oggetti)
```

## Sicurezza

- Gira solo su `127.0.0.1` (nessun servizio esposto).
- I segreti stanno in `.env` (git-ignored); i dati in `data/` (git-ignored).
- La biometria/immagini restano locali se usi il tier locale per la vista.
- Per l'accesso da remoto usa una VPN privata (es. Tailscale), mai una porta aperta.

## Prossime fasi

Email (Fase 4), bus messaggi Matrix con bridge WhatsApp/SMS/iMessage (Fase 5),
riconoscimento volti/voce e scheduler proattivo (Fase 6). Vedi il blueprint
dell'architettura per il percorso completo.
