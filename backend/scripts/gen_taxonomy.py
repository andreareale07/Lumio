import uuid

# Reused UUIDs (existing 14 system categories, must never change)
REUSE = {
    "casa": "cdfe5c4e-13bd-42a6-8314-04df906e1669",
    "casa.affitto": "dd65a3f5-0537-4d61-869c-5a7b1c04b9e5",
    "utenze": "73cda961-a3b1-430c-81fb-03c0642cc842",  # was casa.bollette, promoted to root
    "casa.manutenzione": "0028dc60-8d54-41c2-933c-0def7f9973c6",
    "alimentari": "124e2b3d-02d0-4a8b-9c5e-8b6e83bb2550",
    "alimentari.supermercato": "0b4f2db6-bcbb-4401-a707-c61dcec68c35",
    "alimentari.mercato": "9137698b-7626-40ee-ac62-7a20c5c009df",
    "tempo_libero": "fee4bffb-85f7-4ad1-bbfc-37c911978e30",
    "bar_ristoranti.ristorante": "1e6352dc-878d-4feb-bae2-51cb21be2f4e",  # was tempo_libero.ristoranti
    "tempo_libero.cinema": "dc0ba4a3-55d9-46ab-990b-9b73ee265eea",
    "tempo_libero.sport": "12e31f65-feed-4bf4-96a4-128d566ed3eb",
    "abbonamenti": "9d1ce192-c4f4-48b2-9d38-9e7412014e56",
    "abbonamenti.streaming": "a8493dbc-1dc0-4875-bd1e-d7e36a220cbf",
    "abbonamenti.software": "fc21248e-72b0-4e21-9733-e6b008b8b91e",
}

STRUCTURE = [
    ("casa", "Casa", "expense", [
        ("affitto", "Affitto"),
        ("mutuo", "Mutuo"),
        ("condominio", "Spese condominiali"),
        ("manutenzione", "Manutenzione e riparazioni"),
        ("arredamento", "Arredamento"),
        ("elettrodomestici", "Elettrodomestici"),
        ("servizi_domestici", "Pulizie e servizi domestici"),
    ]),
    ("utenze", "Utenze", "expense", [
        ("energia_elettrica", "Energia elettrica"),
        ("gas", "Gas"),
        ("acqua", "Acqua"),
        ("riscaldamento", "Riscaldamento"),
        ("internet", "Internet"),
        ("telefonia", "Telefonia"),
        ("rifiuti", "Rifiuti (TARI)"),
    ]),
    ("alimentari", "Alimentari", "expense", [
        ("supermercato", "Supermercato"),
        ("mercato", "Mercato"),
        ("panetteria_macelleria", "Panetteria e macelleria"),
        ("bevande", "Bevande ed enoteca"),
        ("spesa_online", "Spesa online"),
    ]),
    ("bar_ristoranti", "Bar e ristoranti", "expense", [
        ("ristorante", "Ristorante"),
        ("bar_caffetteria", "Bar e caffetteria"),
        ("fast_food", "Fast food"),
        ("delivery", "Delivery"),
        ("mensa", "Mensa aziendale"),
    ]),
    ("trasporti", "Trasporti", "expense", [
        ("carburante", "Carburante"),
        ("ricarica_elettrica", "Ricarica elettrica"),
        ("pedaggi", "Pedaggi"),
        ("parcheggi", "Parcheggi"),
        ("mezzi_pubblici", "Mezzi pubblici"),
        ("taxi_ncc", "Taxi e NCC"),
        ("sharing", "Sharing (auto/bici/monopattini)"),
        ("treno", "Treno"),
        ("aereo", "Aereo"),
        ("noleggio_auto", "Noleggio auto"),
        ("manutenzione_veicolo", "Manutenzione veicolo"),
        ("bollo_multe", "Bollo e multe"),
    ]),
    ("salute", "Salute e cura della persona", "expense", [
        ("farmacia", "Farmacia"),
        ("visite_mediche", "Visite mediche"),
        ("dentista", "Dentista"),
        ("analisi_esami", "Analisi ed esami"),
        ("ottica", "Ottica"),
        ("terapie", "Fisioterapia e psicoterapia"),
        ("parrucchiere_estetica", "Parrucchiere ed estetica"),
    ]),
    ("shopping", "Shopping", "expense", [
        ("abbigliamento", "Abbigliamento"),
        ("accessori", "Accessori e gioielli"),
        ("elettronica", "Elettronica"),
        ("informatica", "Informatica"),
        ("libri_musica", "Libri, musica e film"),
        ("giochi", "Giochi e videogiochi"),
        ("regali", "Regali"),
    ]),
    ("tempo_libero", "Tempo libero", "expense", [
        ("cinema", "Cinema"),
        ("teatro_concerti", "Teatro e concerti"),
        ("musei_eventi", "Musei ed eventi"),
        ("palestra_fitness", "Palestra e fitness"),
        ("sport", "Sport e attività"),
        ("hobby", "Hobby"),
    ]),
    ("abbonamenti", "Abbonamenti", "expense", [
        ("streaming", "Streaming"),
        ("streaming_musica", "Streaming musica"),
        ("software", "Software"),
        ("cloud_storage", "Cloud e storage"),
    ]),
    ("viaggi", "Viaggi e vacanze", "expense", [
        ("alloggio", "Alloggio"),
        ("pacchetti_viaggio", "Pacchetti viaggio"),
        ("escursioni", "Escursioni e attività"),
    ]),
    ("istruzione", "Istruzione e formazione", "expense", [
        ("asilo_nido", "Asilo nido"),
        ("retta_scolastica", "Retta scolastica"),
        ("universita", "Università"),
        ("corsi_formazione", "Corsi di formazione"),
        ("libri_testo", "Libri di testo"),
    ]),
    ("famiglia", "Famiglia e figli", "expense", [
        ("babysitter", "Babysitter"),
        ("abbigliamento_bambini", "Abbigliamento bambini"),
        ("attivita_extrascolastiche", "Attività extrascolastiche"),
        ("mantenimento", "Assegni di mantenimento"),
    ]),
    ("animali", "Animali domestici", "expense", [
        ("cibo", "Cibo"),
        ("veterinario", "Veterinario"),
        ("toelettatura", "Toelettatura"),
    ]),
    ("lavoro", "Lavoro e professione", "expense", [
        ("spese_professionali", "Spese professionali"),
        ("attrezzatura", "Attrezzatura di lavoro"),
        ("trasferte", "Trasferte di lavoro"),
        ("contributi_previdenziali", "Contributi previdenziali"),
        ("consulenze", "Consulenze e commercialista"),
    ]),
    ("tasse", "Tasse e imposte", "expense", [
        ("irpef", "IRPEF (saldo e acconti)"),
        ("addizionali", "Addizionali regionali e comunali"),
        ("imu_tari", "IMU e tributi locali"),
        ("imposta_bollo", "Imposta di bollo"),
        ("capital_gain", "Imposta capital gain"),
    ]),
    ("assicurazioni", "Assicurazioni", "expense", [
        ("auto", "Auto e moto"),
        ("casa", "Casa"),
        ("salute", "Salute"),
        ("vita", "Vita"),
    ]),
    ("commissioni", "Commissioni e spese bancarie", "expense", [
        ("canone_conto", "Canone conto"),
        ("canone_carta", "Canone carta"),
        ("bonifico", "Commissione bonifico"),
        ("prelievo", "Commissione prelievo"),
        ("cambio_valuta", "Commissione cambio valuta"),
        ("negoziazione", "Commissione di negoziazione"),
        ("interessi_passivi", "Interessi passivi"),
    ]),
    ("finanziamenti", "Prestiti e finanziamenti", "expense", [
        ("rata_mutuo", "Rata mutuo"),
        ("interessi_mutuo", "Interessi mutuo"),
        ("rata_prestito", "Rata prestito personale"),
    ]),
    ("donazioni", "Donazioni e beneficenza", "expense", [
        ("beneficenza", "Beneficenza"),
    ]),
    ("entrate", "Entrate", "income", [
        ("stipendio", "Stipendio"),
        ("tredicesima", "Tredicesima e quattordicesima"),
        ("bonus_premi", "Bonus e premi"),
        ("pensione", "Pensione"),
        ("freelance", "Compensi freelance"),
        ("affitti_attivi", "Affitti attivi"),
        ("dividendi", "Dividendi"),
        ("interessi_attivi", "Interessi attivi"),
        ("rimborsi_spese", "Rimborsi spese"),
        ("rimborsi_fiscali", "Rimborsi fiscali"),
        ("altro", "Entrate - altro"),
    ]),
    ("trasferimenti", "Trasferimenti", "transfer", [
        ("giroconto", "Giroconto tra conti propri"),
        ("prelievo_contanti", "Prelievo contanti"),
        ("versamento_contanti", "Versamento contanti"),
        ("ricarica_carta", "Ricarica carta"),
    ]),
    ("investimenti", "Investimenti", "investment", [
        ("acquisto_titoli", "Acquisto titoli"),
        ("vendita_titoli", "Vendita titoli"),
        ("versamento_pac", "Versamento PAC"),
        ("acquisto_cripto", "Acquisto criptovalute"),
        ("vendita_cripto", "Vendita criptovalute"),
        ("deposito_conto_titoli", "Deposito su conto titoli"),
        ("prelievo_conto_titoli", "Prelievo da conto titoli"),
    ]),
    ("altro", "Altro", "neutral", [
        ("da_classificare", "Da classificare"),
        ("bonifico_a_terzi", "Bonifico a terzi (scopo non specificato)"),
        ("bonifico_ricevuto", "Bonifico ricevuto (origine non specificata)"),
        ("contanti", "Contanti non tracciati"),
    ]),
]

used_ids = set(REUSE.values())


def get_id(code):
    if code in REUSE:
        return REUSE[code]
    while True:
        new_id = str(uuid.uuid4())
        if new_id not in used_ids:
            used_ids.add(new_id)
            return new_id


HEADER = '''"""Tassonomia viva delle categorie di sistema (rework post-M11.5).

Dato puro, nessuna dipendenza da DB/FastAPI -- stessa natura di
`app/ai/prompt.py` e dei registri in `app/parsers/__init__.py`. E' la SOLA
fonte di verita' per: il reseed di produzione (migration 0022), il reseed di
test (conftest.py), la costruzione del prompt AI (gerarchia + hint) e il
livello deterministico "system" della pipeline di classificazione
(app/services/classification_pipeline.py).

23 radici, ~126 figli, profondita' 2 fissa. `code` e' sempre
`"{parent_code}.{suffix}"` per un figlio, lo slug della radice altrimenti.
`sort_order`: radice = indice*100, figli = radice+1..+99 -- un
`ORDER BY sort_order` numerico produce direttamente l'albero anche con ~150
righe (il vecchio schema 10/11/12.../20/21/22... andava bene solo per 14
righe; il bug del vecchio frontend che ordinava le LABEL con `localeCompare`
invece che i sort_order come numeri e' descritto in
`frontend/src/features/categories/utils.ts`).

UUID: 14 riusati dalle categorie di sistema gia' esistenti in
`app/db/seed_data.SYSTEM_CATEGORIES_V1` (nessuna transazione/regola/
classificazione storica cambia riferimento), gli altri fissi generati una
volta sola e congelati qui -- MAI rigenerarli: romperebbero la migration 0022
se ri-eseguita e ogni test che li referenzia per stringa.
"""
from dataclasses import dataclass

CATEGORY_KINDS = ("expense", "income", "transfer", "investment", "neutral")


@dataclass(frozen=True)
class TaxonomyCategory:
    id: str
    code: str
    name: str
    kind: str
    parent_code: str | None
    sort_order: int


TAXONOMY: list[TaxonomyCategory] = [
'''

FOOTER = ''']

TAXONOMY_BY_CODE: dict[str, TaxonomyCategory] = {c.code: c for c in TAXONOMY}
'''

body_lines = []
for root_idx, (root_code, root_name, kind, children) in enumerate(STRUCTURE, start=1):
    root_sort = root_idx * 100
    root_id = get_id(root_code)
    body_lines.append(
        '    TaxonomyCategory(id="{}", code="{}", name="{}", kind="{}", parent_code=None, sort_order={}),'.format(
            root_id, root_code, root_name, kind, root_sort
        )
    )
    for child_idx, (suffix, name) in enumerate(children, start=1):
        child_code = "{}.{}".format(root_code, suffix)
        child_id = get_id(child_code)
        child_sort = root_sort + child_idx
        body_lines.append(
            '    TaxonomyCategory(id="{}", code="{}", name="{}", kind="{}", parent_code="{}", sort_order={}),'.format(
                child_id, child_code, name, kind, root_code, child_sort
            )
        )

content = HEADER + "\n".join(body_lines) + "\n" + FOOTER

out_path = "app/classification/taxonomy.py"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)

print("roots:", len(STRUCTURE))
print("total data rows:", len(body_lines))
print("written to", out_path)
