from datetime import datetime, timezone
import base64
import binascii
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import transcription


# CODIGO QUE IRIA PRO SCRIPT PRA PEGAR NUMERO DA MENSAGEM
#  //  var extra_params = {teste: "teste"};

#   // (function captureWidgetPhone() {
#   //   var originalOpen = XMLHttpRequest.prototype.open;
#   //   var originalSend = XMLHttpRequest.prototype.send;

#   //   XMLHttpRequest.prototype.open = function(method, url) {
#   //     this.__tifluxUrl = String(url);
#   //     return originalOpen.apply(this, arguments);
#   //   };

#   //   XMLHttpRequest.prototype.send = function(body) {
#   //     if (
#   //       this.__tifluxUrl &&
#   //       this.__tifluxUrl.includes("/widget/") &&
#   //       (this.__tifluxUrl.includes("/start") ||
#   //         this.__tifluxUrl.includes("/message")) &&
#   //       typeof body === "string"
#   //     ) {
#   //       try {
#   //         var payload = JSON.parse(body);
#   //         var telefone = payload.phone || payload.visitor_phone;

#   //         if (telefone) {
#   //           console.log(telefone)
#   //           fetch("/api/telefones", {
#   //             method: "POST",
#   //             headers: { "Content-Type": "application/json" },
#   //             body: JSON.stringify({ telefone: telefone }),
#   //           }).catch(function(error) {
#   //             console.error("Não foi possível atualizar o telefone:", error);
#   //           });
#   //         }
#   //       } catch (error) {
#   //         console.error("Não foi possível ler o telefone do widget:", error);
#   //       }
#   //     }

#   //     return originalSend.apply(this, arguments);
#   //   };
#   // })();

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "num.db"
MAX_TRANSCRIPTION_BYTES = 20 * 1024 * 1024

app = FastAPI()


def initialize_database():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telefones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT NOT NULL UNIQUE,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
        """)


class TelefonePayload(BaseModel):
    telefone: str


class TranscriptionPayload(BaseModel):
    data_base64: str
    mime_type: str = "audio/webm"
    filename: str = "audio.webm"


@app.on_event("startup")
def startup():
    initialize_database()


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.post("/api/telefones")
def salvar(payload: TelefonePayload):
    print("DO_POST:", payload.telefone, flush=True)

    telefone = payload.telefone.strip()
    if not telefone:
        raise HTTPException(400, "Telefone ausente")

    agora = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DATABASE) as conn:
        updated = conn.execute(
            "UPDATE telefones SET atualizado_em=? WHERE telefone=?",
            (agora, telefone),
        ).rowcount

        if not updated:
            conn.execute(
                """
                INSERT INTO telefones
                (telefone, criado_em, atualizado_em)
                VALUES (?, ?, ?)
                """,
                (telefone, agora, agora),
            )

    return {"ok": True}


@app.post("/api/transcription")
def transcribe_recording(payload: TranscriptionPayload):
    if len(payload.data_base64) > 28 * 1024 * 1024:
        raise HTTPException(413, "Áudio grande demais para transcrever.")
    try:
        audio = base64.b64decode(payload.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Arquivo de áudio inválido.")
    if len(audio) > MAX_TRANSCRIPTION_BYTES:
        raise HTTPException(413, "O áudio excede o limite de 20 MB.")
    try:
        text = transcription.transcribe_bytes(audio, payload.mime_type, payload.filename)
    except transcription.TranscriptionError as exc:
        raise HTTPException(503, str(exc))
    return {"ok": True, "text": text}


@app.get("/api/transcription/status")
def transcription_status():
    return {"ok": True}


app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
