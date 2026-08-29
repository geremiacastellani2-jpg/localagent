# Maggiordomo Locale

Un agente personale che gira **interamente sul tuo Mac**: chat locale, note,
promemoria, memoria a lungo termine e **vista** (il modello guarda attraverso la
camera e ti dice cosa vede). Modelli **ibridi** — Ollama in locale, OpenRouter in
cloud — tramite un'unica API OpenAI-compatibile.

> Tutte le **6 fasi** del blueprint sono implementate. Questo è ancora uno
> scaffold: alcune parti (biometria offline pesante, e2ee Matrix) sono lasciate
> come irrobustimenti futuri, documentati sotto.

## Cosa c'è già

- 💬 **Chat web locale** (`http://127.0.0.1:8765`) — l'interfaccia da cui parli,
  a voce (🎤 Web Speech) o scritto; risposte lette ad alta voce (🔊 opzionale).
- 👁️ **Vista dal vivo** — feed live: riconoscimento **oggetti** in tempo reale e
  **volti** registrati (face-api.js nel browser); l'agente sa cosa/chi c'è
  *adesso* (`current_view`, `who_is_here`) o descrive con un VLM (`look`).
- 🔔 **Proattività** — promemoria che **scattano**, **rassegna del mattino** e
  avviso quando riconosce una persona; notifiche mostrate nella chat.
- 📅 **Calendario** — crea/sposta/elenca eventi; **sincronizza con CalDAV**.
- 🧠 **Memoria a due livelli** — fatti strutturati + **richiamo semantico**.
- ✉️ **Email** (IMAP/SMTP) e 💬 **Messaggi** (WhatsApp/SMS/iMessage via Matrix).
- ✅ **Coda di approvazioni** — ogni invio richiede la tua conferma.
- 🗒️ **Note** e ⏰ **promemoria** su archivio locale SQLite.
- 🔀 **Router ibrido vero** — con `DEFAULT_TIER=auto` la chat va in **locale**
  quando Ollama è attivo (privato, gratuito) e in cloud altrimenti; la **vista**
  preferisce il cloud (qualità) con fallback sul locale. Selettore
  auto/locale/cloud per singolo messaggio nella chat, e `/diag` per la
  diagnostica completa.

## Requisiti

- **Python 3.11 – 3.12 consigliato.** Su versioni molto recenti (es. 3.14) alcune
  dipendenze *opzionali* (numpy, matrix-nio) potrebbero non avere ancora un wheel
  pronto: il **nucleo** si installa comunque, le opzionali le aggiungi quando i
  wheel sono disponibili o usando Python 3.12.
- **Ollama** (per il tier locale): <https://ollama.com>
  ```bash
  ollama pull qwen2.5           # chat locale
  ollama pull llama3.2-vision   # vista locale (VLM)
  ollama pull nomic-embed-text  # embedding per la memoria semantica
  ```
- **Chiave OpenRouter** (per il tier cloud, facoltativa): <https://openrouter.ai/keys>

Serve almeno uno dei due tier. Con `DEFAULT_TIER=auto` usa il cloud se trova la
chiave, altrimenti il locale.

## Avvio

```bash
cp .env.example .env      # compila OPENROUTER_API_KEY e/o configura Ollama
./run.sh                  # crea la venv, sincronizza il nucleo, avvia il server

# funzioni opzionali (calendario CalDAV, memoria più veloce, Matrix/WhatsApp):
./.venv/bin/pip install -r requirements-optional.txt
```

Apri **http://127.0.0.1:8765** nel browser (sul Mac). Scrivi in italiano; premi
📷 per attivare la camera e poi 👁️ (o chiedi «cosa vedi?»).

### Configurare OpenRouter

1. Crea una chiave su <https://openrouter.ai/keys> (serve un po' di credito).
2. Mettila nel file **`.env`** (non in `.env.example`):
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   CLOUD_MODEL=anthropic/claude-3.5-sonnet
   ```
3. Verifica: apri <http://127.0.0.1:8765/health>. Se vedi `"cloud_configured": true`,
   la chiave è letta. Nota: con Ollama attivo la **chat resta in locale** (è
   l'ibrido: privato e gratuito per la routine); il cloud serve per la **vista**
   e quando il locale non è disponibile. Vuoi il cloud per un messaggio? Usa il
   selettore in alto nella chat. Diagnostica completa: <http://127.0.0.1:8765/diag>.
4. Prova indipendente della chiave:
   ```bash
   curl https://openrouter.ai/api/v1/models -H "Authorization: Bearer $OPENROUTER_API_KEY" | head
   ```

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
  db.py            SQLite: note, promemoria, fatti, eventi, vettori, coda azioni
  calendar_store.py archivio locale eventi (fonte di verità)
  caldav_sync.py   sincronizzazione con server CalDAV
  semantic_memory.py indice vettoriale + embedding locali (memoria livello 2)
  email_client.py  lettura IMAP e invio SMTP (Fase 4)
  matrix_client.py bridge Matrix in thread asincrono (Fase 5)
  outbox.py        coda di approvazioni per gli invii
  scheduler.py     promemoria che scattano + rassegna del mattino (Fase 6)
  briefing.py      compositore della rassegna
  notifications.py coda di notifiche proattive (polling dalla UI)
  presence.py      chi è davanti alla camera (arrivi vs presenza continua)
  state.py         frame live, oggetti e volti, per sessione (in memoria)
  tools/           note, promemoria, memoria, calendario, email, messaggi,
                   approvazioni, rassegna, vista, ora
  perception/      cattura frame camera (fallback headless)
  server.py        FastAPI: /chat + /frame + /notifications + chat web
web/
  index.html       la chat locale (camera live + rilevamento oggetti)
deploy/matrix/     docker-compose: Synapse + mautrix-whatsapp
docs/whatsapp.md   guida per collegare WhatsApp
```

## Sicurezza

- Gira solo su `127.0.0.1` (nessun servizio esposto).
- I segreti stanno in `.env` (git-ignored); i dati in `data/` (git-ignored).
- La biometria/immagini restano locali se usi il tier locale per la vista.
- Per l'accesso da remoto usa una VPN privata (es. Tailscale), mai una porta aperta.

## Proattività e percezione (Fase 6)

- **Scheduler** (`SCHEDULER_ENABLED`, `BRIEF_HOUR`): in background fa scattare i
  promemoria scaduti e manda la **rassegna del mattino** all'ora impostata. Le
  notifiche compaiono nella chat (la UI fa polling su `/notifications`). Chiedi
  «come sono messo oggi?» per la rassegna su richiesta (`daily_brief`).
- **Riconoscimento volti:** attiva la camera, premi **＋ registra volto**, dai un
  nome. I descrittori restano **nel tuo browser** (localStorage), non sul server.
  Quando una persona nota compare, l'agente te lo segnala; `who_is_here` dice chi
  c'è ora.
- **Voce:** 🎤 detta il messaggio (Web Speech, `it-IT`), 🔊 fa leggere le risposte
  ad alta voce (SpeechSynthesis). Tutto nel browser.

> Nota: volti e voce girano **nel browser** — niente modelli nativi da installare,
> tutto resta sul Mac. Per una biometria offline più robusta (InsightFace,
> whisper.cpp, speaker-ID) e per l'identificazione di *chi parla*, vedi il
> blueprint: è il naturale irrobustimento successivo.

## Email e messaggi

- **Email:** imposta `EMAIL_ADDRESS`/`EMAIL_PASSWORD` (per Gmail, una *password per
  le app*) e gli host IMAP/SMTP. L'agente legge la posta; gli invii finiscono in
  coda di approvazione e partono solo dopo il tuo ok.
- **WhatsApp/SMS/iMessage:** via Matrix + mautrix. Procedura completa in
  [`docs/whatsapp.md`](docs/whatsapp.md). ⚠️ Il bridge WhatsApp automatizza il tuo
  numero personale (contro i ToS, rischio ban): ogni invio richiede conferma.

## Irrobustimenti futuri

Le 6 fasi ci sono tutte. I prossimi passi sono di robustezza, non di funzioni
nuove: biometria offline più forte (InsightFace, whisper.cpp, speaker-ID),
supporto e2ee per le stanze Matrix cifrate, consolidamento automatico della
memoria (promuovere gli episodi a fatti), e un cruscotto web per la coda di
approvazioni. Vedi il blueprint dell'architettura.
