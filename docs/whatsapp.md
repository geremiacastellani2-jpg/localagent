# Collegare WhatsApp (e SMS/iMessage) via Matrix

Il Maggiordomo non parla direttamente con WhatsApp: si collega a un **homeserver
Matrix** (Synapse) sul quale gira il **bridge mautrix-whatsapp**. Ogni chat
diventa una stanza Matrix che l'agente legge e scrive.

> ⚠️ **Onestà sui rischi.** mautrix-whatsapp collega il tuo **numero personale**
> come dispositivo compagno (come WhatsApp Web). Automatizzarlo **viola i ToS di
> WhatsApp** e comporta un **rischio reale di ban**. Per un uso personale e "umano"
> è basso, non nullo. Il Maggiordomo mitiga mettendo **ogni invio in coda di
> approvazione** (nessun messaggio parte senza il tuo ok). Alternativa pulita:
> WhatsApp Cloud API ufficiale su un numero business separato.

## 1. Avvia homeserver + bridge

```bash
cd deploy/matrix

# 1a. genera la config di Synapse (una volta)
docker compose run --rm synapse generate

# 1b. genera la config del bridge (una volta): crea ./whatsapp/config.yaml
docker compose run --rm mautrix-whatsapp
```

Nel **`whatsapp/config.yaml`** imposta:
- `homeserver.address: http://synapse:8008` e `homeserver.domain: localhost`
- in `bridge.permissions` dai il livello `admin` al tuo utente:
  `"@tu:localhost": admin`
- lascia la cifratura **disattivata** (default) — vedi nota e2ee in fondo.

Rigenera il file di registrazione e collegalo a Synapse:
- il bridge crea `./whatsapp/registration.yaml`;
- in **`synapse/homeserver.yaml`** aggiungi:
  ```yaml
  app_service_config_files:
    - /data/registration.yaml
  ```
  e copia/monta `whatsapp/registration.yaml` come `synapse/registration.yaml`.
- abilita la registrazione utenti per creare il tuo account (o usa il comando sotto).

Poi:
```bash
docker compose up -d
```

## 2. Crea il tuo utente Matrix

```bash
docker compose exec synapse register_new_matrix_user \
  -c /data/homeserver.yaml -u tu -p LA_TUA_PASSWORD -a http://localhost:8008
```

## 3. Collega WhatsApp

1. Apri un client Matrix (**Element**, app desktop) e accedi come `@tu:localhost`
   (homeserver `http://localhost:8008`).
2. Avvia una chat con **`@whatsappbot:localhost`** e invia `login`.
3. Scansiona il **QR code** dal telefono:
   WhatsApp → **Dispositivi collegati → Collega un dispositivo**.
4. Fatto: le tue chat WhatsApp compaiono come stanze Matrix.

## 4. Dai le credenziali al Maggiordomo

Ottieni un access token per l'agente (login via API, oppure da Element:
Impostazioni → Aiuto e informazioni → Token di accesso). Poi nel `.env`:

```
MATRIX_HOMESERVER=http://localhost:8008
MATRIX_USER=@tu:localhost
MATRIX_TOKEN=<access token>
```

Installa il client Matrix e riavvia il Maggiordomo:
```bash
./.venv/bin/pip install -r requirements-optional.txt   # include matrix-nio
./run.sh
```

In chat: «quali chat ho?», «leggi gli ultimi messaggi di Marco», «scrivi a Marco
che arrivo alle 20» → l'agente prepara il messaggio e chiede conferma prima di
inviarlo.

## Nota su cifratura (e2ee)

Se abiliti la cifratura lato bridge, le stanze sono e2ee e servono le estensioni
crypto: `pip install "matrix-nio[e2e]"` (richiede **libolm**). Per iniziare è più
semplice tenere la cifratura **disattivata** sul bridge.

## SMS e iMessage

Stesso schema con `mautrix-imessage` (gira sul Mac, porta SMS+iMessage in Matrix).
Si aggiunge come secondo bridge nello stesso homeserver.
