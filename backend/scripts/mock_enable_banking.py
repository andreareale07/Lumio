"""Mock locale dell'API Enable Banking, SOLO per la verifica manuale del flusso
nel browser (dati sintetici, nessuna credenziale reale, nessuna verifica del JWT).

Avvio (porta 9999):  python -I scripts/mock_enable_banking.py
Poi backend e worker con:
    OPEN_BANKING_ENABLED=true OPEN_BANKING_BASE_URL=http://localhost:9999 \
    OPEN_BANKING_REDIRECT_URI=http://localhost:5174/api/v1/open-banking/callback
e il frontend con `npx vite --port 5174` (VITE_DEV_API_PROXY_TARGET=<porta del backend>).
Usare SEMPRE Postgres/Redis effimeri (vedi .claude/memoria/guida-metodo-sviluppo-e-test.md).
La pagina "banca finta" (/fake-bank) offre i link Autorizza / Nega verso il callback.

Scenari-banca per `/accounts/{uid}/transactions` (default `basic`): si scelgono all'avvio con
`MOCK_SCENARIO=<nome>` oppure a caldo con `curl -X POST localhost:9999/__scenario/<nome>`:
  basic, unstable_ids (entry_reference diverso a ogni lettura), placeholder_ref ("0"),
  reused_ids (stesso id con importi diversi), dup_in_response, late_booking (booking_date di 20
  giorni prima), malformed (payload rotti), old_date_4xx (422 WRONG_TRANSACTIONS_PERIOD su
  date_from vecchio), repeating_key (continuation_key sempre uguale), no_booking_date,
  no_indicator, pending_survives (PDNG nonostante transaction_status=BOOK).
"""
import os
import uuid
from datetime import date, timedelta
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()
STATE: dict[str, str] = {}  # state -> redirect_url
SCENARIO = {"name": os.environ.get("MOCK_SCENARIO", "basic")}
READS: dict[str, int] = {}  # uid -> numero di letture (per gli scenari che cambiano nel tempo)


@app.post("/__scenario/{name}")
async def set_scenario(name: str):
    SCENARIO["name"] = name
    READS.clear()
    return {"scenario": name}


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


def _raw(uid: str, ref: str, ind: str, amount: str, d: date, remittance: list[str], name: str) -> dict:
    return {
        "entry_reference": f"{uid}-{ref}", "transaction_amount": {"currency": "EUR", "amount": amount},
        "credit_debit_indicator": ind, "status": "BOOK", "booking_date": d.isoformat(), "value_date": d.isoformat(),
        "remittance_information": remittance,
        "creditor" if ind == "DBIT" else "debtor": {"name": name},
    }


def _base_rows(uid: str) -> list[dict]:
    today = date.today()
    rows = [
        _raw(uid, "r1", "DBIT", "42.50", today - timedelta(days=9), ["PAGAMENTO POS SUPERMERCATO ROSSI"], "Supermercato Rossi"),
        _raw(uid, "r2", "CRDT", "1800.00", today - timedelta(days=8), ["STIPENDIO OTTOBRE"], "Azienda Verdi Srl"),
        _raw(uid, "r3", "DBIT", "9.99", today - timedelta(days=5), ["ABBONAMENTO STREAMING"], "Streaming SpA"),
        _raw(uid, "r4", "DBIT", "65.00", today - timedelta(days=2), ["RICARICA TELEFONICA"], "Telefonia Srl"),
    ]
    return rows[:2] if uid == "uid-pp" else rows


@app.get("/accounts/{uid}/transactions")
async def transactions(uid: str, request: Request):
    name = SCENARIO["name"]
    reads = READS[uid] = READS.get(uid, 0) + 1
    today = date.today()
    out = _base_rows(uid)
    extra: dict = {}
    date_from = request.query_params.get("date_from")

    if name == "unstable_ids":
        for row in out:
            row["entry_reference"] = f"{row['entry_reference']}-read{reads}"
    elif name == "placeholder_ref":
        for row in out:
            row["entry_reference"] = "0"
    elif name == "reused_ids":
        out.append(_raw(uid, "r1", "DBIT", "77.00", today - timedelta(days=1), ["ADDEBITO DIVERSO"], "Altro"))
    elif name == "dup_in_response":
        out = out + [dict(out[0])]
    elif name == "late_booking":
        out.append(_raw(uid, f"late{reads}", "DBIT", "120.00", today - timedelta(days=20), ["ADDEBITO SDD IN RITARDO"], "Energia Spa"))
    elif name == "malformed":
        out += [{"entry_reference": "bad1", "transaction_amount": "12", "credit_debit_indicator": "DBIT"}, "garbage", None,
                {"entry_reference": "bad2", "transaction_amount": {"currency": "EURO", "amount": "1"}, "booking_date": today.isoformat()}]
    elif name == "old_date_4xx":
        if date_from and date_from < (today - timedelta(days=40)).isoformat():
            return JSONResponse(status_code=422, content={"error": "WRONG_TRANSACTIONS_PERIOD"})
    elif name == "repeating_key":
        extra["continuation_key"] = "same-key"
    elif name == "no_booking_date":
        for row in out:
            row.pop("booking_date")
    elif name == "no_indicator":
        for row in out:
            row.pop("credit_debit_indicator")
    elif name == "pending_survives":
        pending = _raw(uid, "p1", "DBIT", "15.00", today, ["IN ELABORAZIONE"], "Bar")
        pending["status"] = "PDNG"
        out.append(pending)
    return {"transactions": out, **extra}


@app.get("/accounts/{uid}/balances")
async def balances(uid: str):
    return {"balances": [{"name": "Booked", "balance_amount": {"currency": "EUR", "amount": "1234.56"}, "balance_type": "CLBD"}]}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    return JSONResponse(status_code=204, content=None)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="warning")
