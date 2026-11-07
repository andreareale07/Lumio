"""Mock locale dell'API Enable Banking, SOLO per la verifica manuale del flusso
nel browser (dati sintetici, nessuna credenziale reale, nessuna verifica del JWT).

Avvio (porta 9999):  python -I scripts/mock_enable_banking.py
Poi backend e worker con:
    OPEN_BANKING_ENABLED=true OPEN_BANKING_BASE_URL=http://localhost:9999 \
    OPEN_BANKING_REDIRECT_URI=http://localhost:5174/api/v1/open-banking/callback
e il frontend con `npx vite --port 5174` (VITE_DEV_API_PROXY_TARGET=<porta del backend>).
Usare SEMPRE Postgres/Redis effimeri (vedi .claude/memoria/guida-metodo-sviluppo-e-test.md).
La pagina "banca finta" (/fake-bank) offre i link Autorizza / Nega verso il callback.
"""
import uuid
from datetime import date, timedelta
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()
STATE: dict[str, str] = {}  # state -> redirect_url


@app.get("/aspsps")
async def aspsps(country: str = "IT"):
    banks = [
        {"name": "Poste Italiane", "country": "IT", "psu_types": ["personal"], "maximum_consent_validity": 15552000, "beta": False},
        {"name": "Intesa Sanpaolo", "country": "IT", "psu_types": ["personal", "business"], "maximum_consent_validity": 7776000, "beta": False},
        {"name": "Banca Esempio Beta", "country": "IT", "psu_types": ["personal"], "maximum_consent_validity": 15552000, "beta": True},
        {"name": "Solo Aziende SpA", "country": "IT", "psu_types": ["business"]},
    ]
    return {"aspsps": [b for b in banks if b["country"] == country.upper()]}


@app.post("/auth")
async def auth(request: Request):
    body = await request.json()
    STATE[body["state"]] = body["redirect_url"]
    url = f"http://localhost:9999/fake-bank?state={quote(body['state'])}&bank={quote(body['aspsp']['name'])}"
    return {"url": url, "authorization_id": str(uuid.uuid4())}


@app.get("/fake-bank", response_class=HTMLResponse)
async def fake_bank(state: str, bank: str):
    redirect = STATE.get(state, "")
    ok = f"{redirect}?code=fake-code&state={quote(state)}"
    denied = f"{redirect}?error=access_denied&state={quote(state)}"
    return f"""<html><body style="font-family:sans-serif;padding:24px">
    <h2>{bank} (banca finta)</h2><p>Autorizzi la lettura dei conti?</p>
    <p><a id="ok" href="{ok}">Autorizza</a></p><p><a id="no" href="{denied}">Nega</a></p></body></html>"""


@app.post("/sessions")
async def sessions(request: Request):
    return {
        "session_id": str(uuid.uuid4()),
        "access": {"valid_until": (date.today() + timedelta(days=170)).isoformat() + "T00:00:00Z"},
        "accounts": [
            {"uid": "uid-cc", "account_id": {"iban": "IT60X0542811101000000123456"}, "name": "Conto BancoPosta", "currency": "EUR", "cash_account_type": "CACC"},
            {"uid": "uid-pp", "account_id": {"iban": "IT28W8000000292100645211208"}, "name": "Postepay Evolution", "currency": "EUR", "cash_account_type": "CARD"},
        ],
    }


@app.get("/accounts/{uid}/transactions")
async def transactions(uid: str, request: Request):
    today = date.today()
    rows = [
        ("r1", "DBIT", "42.50", today - timedelta(days=9), ["PAGAMENTO POS SUPERMERCATO ROSSI"], "Supermercato Rossi"),
        ("r2", "CRDT", "1800.00", today - timedelta(days=8), ["STIPENDIO OTTOBRE"], "Azienda Verdi Srl"),
        ("r3", "DBIT", "9.99", today - timedelta(days=5), ["ABBONAMENTO STREAMING"], "Streaming SpA"),
        ("r4", "DBIT", "65.00", today - timedelta(days=2), ["RICARICA TELEFONICA"], "Telefonia Srl"),
    ]
    out = []
    for ref, ind, amount, d, remittance, name in rows:
        out.append({
            "entry_reference": f"{uid}-{ref}", "transaction_amount": {"currency": "EUR", "amount": amount},
            "credit_debit_indicator": ind, "status": "BOOK", "booking_date": d.isoformat(), "value_date": d.isoformat(),
            "remittance_information": remittance,
            "creditor" if ind == "DBIT" else "debtor": {"name": name},
        })
    if uid == "uid-pp":
        out = out[:2]
    return {"transactions": out}


@app.get("/accounts/{uid}/balances")
async def balances(uid: str):
    return {"balances": [{"name": "Booked", "balance_amount": {"currency": "EUR", "amount": "1234.56"}, "balance_type": "CLBD"}]}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    return JSONResponse(status_code=204, content=None)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="warning")
