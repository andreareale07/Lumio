"""Elenco delle valute di sistema (sistema di valute, sostituisce il campo
`currency` libero a 3 lettere). Dato puro, nessuna dipendenza da DB/FastAPI
— stessa natura di `app/classification/taxonomy.py`, e per lo stesso motivo
SOLA fonte di verita' sia per il seed di produzione (migration
`0029_currencies.py`) sia per il reseed di test (`tests/conftest.py`): un
`TRUNCATE ... CASCADE` di `workspaces` svuota anche `currencies` (ha una FK
su `workspace_id`), comprese le righe di sistema seedate dalla migration —
vanno reinserite subito dopo con la STESSA lista, mai una copia separata che
potrebbe divergere.

Non esaustivo (ISO-4217 ha ~180 codici attivi): le piu' comuni per un
investitore retail europeo. Un workspace puo' aggiungerne altre come righe
non di sistema (vedi `app/models/currency.py`) senza toccare questo elenco.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedCurrency:
    code: str
    name: str
    symbol: str
    decimal_digits: int = 2


SEED_CURRENCIES: list[SeedCurrency] = [
    SeedCurrency("EUR", "Euro", "€"),
    SeedCurrency("USD", "Dollaro USA", "$"),
    SeedCurrency("GBP", "Sterlina britannica", "£"),
    SeedCurrency("CHF", "Franco svizzero", "CHF"),
    SeedCurrency("JPY", "Yen giapponese", "¥", 0),
    SeedCurrency("CNY", "Yuan cinese", "¥"),
    SeedCurrency("CAD", "Dollaro canadese", "$"),
    SeedCurrency("AUD", "Dollaro australiano", "$"),
    SeedCurrency("NZD", "Dollaro neozelandese", "$"),
    SeedCurrency("HKD", "Dollaro di Hong Kong", "$"),
    SeedCurrency("SGD", "Dollaro di Singapore", "$"),
    SeedCurrency("SEK", "Corona svedese", "kr"),
    SeedCurrency("NOK", "Corona norvegese", "kr"),
    SeedCurrency("DKK", "Corona danese", "kr"),
    SeedCurrency("PLN", "Złoty polacco", "zł"),
    SeedCurrency("CZK", "Corona ceca", "Kč"),
    SeedCurrency("HUF", "Fiorino ungherese", "Ft"),
    SeedCurrency("RON", "Leu rumeno", "lei"),
    SeedCurrency("BGN", "Lev bulgaro", "лв"),
    SeedCurrency("ISK", "Corona islandese", "kr", 0),
    SeedCurrency("TRY", "Lira turca", "₺"),
    SeedCurrency("RUB", "Rublo russo", "₽"),
    SeedCurrency("INR", "Rupia indiana", "₹"),
    SeedCurrency("BRL", "Real brasiliano", "R$"),
    SeedCurrency("MXN", "Peso messicano", "$"),
    SeedCurrency("ZAR", "Rand sudafricano", "R"),
    SeedCurrency("KRW", "Won sudcoreano", "₩", 0),
    SeedCurrency("THB", "Baht thailandese", "฿"),
    SeedCurrency("IDR", "Rupia indonesiana", "Rp", 0),
    SeedCurrency("MYR", "Ringgit malese", "RM"),
    SeedCurrency("PHP", "Peso filippino", "₱"),
    SeedCurrency("ILS", "Nuovo shekel israeliano", "₪"),
    SeedCurrency("AED", "Dirham degli Emirati Arabi Uniti", "د.إ"),
    SeedCurrency("SAR", "Riyal saudita", "﷼"),
    SeedCurrency("EGP", "Sterlina egiziana", "E£"),
    SeedCurrency("VND", "Dong vietnamita", "₫", 0),
    SeedCurrency("UAH", "Hryvnia ucraina", "₴"),
    SeedCurrency("ARS", "Peso argentino", "$"),
    SeedCurrency("CLP", "Peso cileno", "$", 0),
    SeedCurrency("COP", "Peso colombiano", "$"),
    SeedCurrency("TWD", "Nuovo dollaro taiwanese", "NT$"),
]
