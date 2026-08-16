"""Alias di normalizzazione merchant — dato puro, stesso principio del
catalogo di pattern (`app/classification/catalog.py`): una stringa grezza
riconosciuta viene sostituita con un nome leggibile e stabile, invece di
mostrare all'utente il residuo tecnico della descrizione bancaria
("AMZN MKTP IT" -> "Amazon").

Nessuna tabella DB: gli alias fanno parte della logica di normalizzazione,
non un dato di dominio che l'utente deve poter modificare in questa
milestone (una futura UI per fondere/rinominare merchant a mano e' fuori
scope, richiederebbe una tabella con RLS propria — non necessaria oggi).

Chiave = prefisso normalizzato (maiuscolo, senza accenti) da cercare
nel testo GIA' ripulito da `merchant_extraction.py`; il primo alias il cui
`key` e' contenuto nel testo vince (ordine di dichiarazione = priorita').
"""

MERCHANT_ALIASES: dict[str, str] = {
    "AMZN MKTP": "Amazon",
    "AMAZON": "Amazon",
    "ESSELUNGA": "Esselunga",
    "LIDL": "Lidl",
    "CONAD": "Conad",
    "COOP": "Coop",
    "CARREFOUR": "Carrefour",
    "EUROSPIN": "Eurospin",
    "PENNY MARKET": "Penny Market",
    "NETFLIX": "Netflix",
    "SPOTIFY": "Spotify",
    "DISNEY PLUS": "Disney+",
    "DISNEY+": "Disney+",
    "APPLE MUSIC": "Apple Music",
    "APPLE.COM": "Apple",
    "GOOGLE": "Google",
    "MICROSOFT": "Microsoft",
    "PAYPAL": "PayPal",
    "ENI STAZIONE": "Eni",
    "Q8": "Q8",
    "TAMOIL": "Tamoil",
    "TOTALERG": "TotalErg",
    "FARMACIA": "Farmacia",
    "JUST EAT": "Just Eat",
    "GLOVO": "Glovo",
    "DELIVEROO": "Deliveroo",
    "UBER EATS": "Uber Eats",
    "UBER": "Uber",
}
