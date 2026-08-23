"""Tassonomia viva delle categorie di sistema (rework post-M11.5).

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
    # Suggerimento breve per il prompt AI (rework pipeline, step "prompt
    # ridisegnato"): disambigua le categorie il cui nome da solo non basta
    # a un LLM per scegliere bene (es. "Ristorante" vs "Supermercato" sul
    # confine cibo pronto/materia prima). Popolato solo dove serve
    # davvero — None altrove, mai un riempimento meccanico per tutte le 149
    # righe. Vive qui (non in una tabella DB) perche' e' parte
    # dell'ingegneria del prompt, non un dato di dominio che l'utente deve
    # poter modificare.
    hint: str | None = None
    # Traduzione inglese di `name`, SOLO per le categorie di sistema (i18n
    # UI, PLAN_TAXONOMY_I18N.md) — `code` resta l'identita' stabile in
    # entrambe le lingue, `name`/`name_en` sono le due rese testuali. Le
    # categorie utente (`is_system=false`) non hanno equivalente: il loro
    # `name` e' testo libero, mai tradotto.
    name_en: str | None = None
    # Traduzione inglese di `hint` (fetta 2, lingua di classificazione AI
    # per conto): un prompt in inglese con un hint italiano confonderebbe
    # il modello — valorizzato solo per le 7 categorie che hanno gia' un
    # `hint`, mai un riempimento meccanico.
    hint_en: str | None = None


TAXONOMY: list[TaxonomyCategory] = [
    TaxonomyCategory(id="cdfe5c4e-13bd-42a6-8314-04df906e1669", code="casa", name="Casa", name_en="Home", kind="expense", parent_code=None, sort_order=100),
    TaxonomyCategory(id="dd65a3f5-0537-4d61-869c-5a7b1c04b9e5", code="casa.affitto", name="Affitto", name_en="Rent", kind="expense", parent_code="casa", sort_order=101),
    TaxonomyCategory(id="89bd89ad-659f-45f6-8cce-b1baf1283fb4", code="casa.mutuo", name="Mutuo", name_en="Mortgage", kind="expense", parent_code="casa", sort_order=102),
    TaxonomyCategory(id="1540e6e8-3d17-460f-a359-b6eeaa0c29eb", code="casa.condominio", name="Spese condominiali", name_en="Condominium fees", kind="expense", parent_code="casa", sort_order=103),
    TaxonomyCategory(id="0028dc60-8d54-41c2-933c-0def7f9973c6", code="casa.manutenzione", name="Manutenzione e riparazioni", name_en="Maintenance and repairs", kind="expense", parent_code="casa", sort_order=104),
    TaxonomyCategory(id="d06d35c5-93b4-4cdf-8469-7d728467e05c", code="casa.arredamento", name="Arredamento", name_en="Furniture", kind="expense", parent_code="casa", sort_order=105),
    TaxonomyCategory(id="83165081-4c1c-48f7-932e-f5c5e5684080", code="casa.elettrodomestici", name="Elettrodomestici", name_en="Appliances", kind="expense", parent_code="casa", sort_order=106),
    TaxonomyCategory(id="74b682ed-5666-4449-97d7-e96265120f5d", code="casa.servizi_domestici", name="Pulizie e servizi domestici", name_en="Cleaning and home services", kind="expense", parent_code="casa", sort_order=107),
    TaxonomyCategory(id="73cda961-a3b1-430c-81fb-03c0642cc842", code="utenze", name="Utenze", name_en="Utilities", kind="expense", parent_code=None, sort_order=200),
    TaxonomyCategory(id="6d35e2fe-28ae-4dd7-ae8b-746b05c861c6", code="utenze.energia_elettrica", name="Energia elettrica", name_en="Electricity", kind="expense", parent_code="utenze", sort_order=201),
    TaxonomyCategory(id="d19270a9-f39d-4e04-8c46-856ebd7903ec", code="utenze.gas", name="Gas", name_en="Gas", kind="expense", parent_code="utenze", sort_order=202),
    TaxonomyCategory(id="db2968cb-bf20-4d8e-9f7b-ed6441a628a7", code="utenze.acqua", name="Acqua", name_en="Water", kind="expense", parent_code="utenze", sort_order=203),
    TaxonomyCategory(id="97c2dcfa-fd26-4424-b90e-8d8856a56508", code="utenze.riscaldamento", name="Riscaldamento", name_en="Heating", kind="expense", parent_code="utenze", sort_order=204),
    TaxonomyCategory(id="7363cd9a-77a4-4f42-9788-30de9cc62b27", code="utenze.internet", name="Internet", name_en="Internet", kind="expense", parent_code="utenze", sort_order=205),
    TaxonomyCategory(id="83f9977e-9d67-4469-89d8-09545e9d6327", code="utenze.telefonia", name="Telefonia", name_en="Phone", kind="expense", parent_code="utenze", sort_order=206),
    TaxonomyCategory(id="aedab3da-b3cf-480e-b2df-d49aacee12ca", code="utenze.rifiuti", name="Rifiuti (TARI)", name_en="Waste collection tax", kind="expense", parent_code="utenze", sort_order=207),
    TaxonomyCategory(id="124e2b3d-02d0-4a8b-9c5e-8b6e83bb2550", code="alimentari", name="Alimentari", name_en="Groceries", kind="expense", parent_code=None, sort_order=300),
    TaxonomyCategory(id="0b4f2db6-bcbb-4401-a707-c61dcec68c35", code="alimentari.supermercato", name="Supermercato", name_en="Supermarket", kind="expense", parent_code="alimentari", sort_order=301, hint="spesa, materie prime, non cibo gia' pronto/consumato fuori casa", hint_en="groceries, raw ingredients, not ready-to-eat food or food consumed out"),
    TaxonomyCategory(id="9137698b-7626-40ee-ac62-7a20c5c009df", code="alimentari.mercato", name="Mercato", name_en="Market", kind="expense", parent_code="alimentari", sort_order=302),
    TaxonomyCategory(id="2aa5a75b-173b-407b-aab8-f730c0b53e96", code="alimentari.panetteria_macelleria", name="Panetteria e macelleria", name_en="Bakery and butcher", kind="expense", parent_code="alimentari", sort_order=303),
    TaxonomyCategory(id="88032f7f-3897-4c87-9696-d9213f5e5cf4", code="alimentari.bevande", name="Bevande ed enoteca", name_en="Beverages and wine shop", kind="expense", parent_code="alimentari", sort_order=304),
    TaxonomyCategory(id="d016787d-3ebd-43b4-9ce1-0504c6e68c51", code="alimentari.spesa_online", name="Spesa online", name_en="Online groceries", kind="expense", parent_code="alimentari", sort_order=305),
    TaxonomyCategory(id="e5108a5e-cdce-4a0c-bbf9-2e4c3b271ee8", code="bar_ristoranti", name="Bar e ristoranti", name_en="Bars and restaurants", kind="expense", parent_code=None, sort_order=400),
    TaxonomyCategory(id="1e6352dc-878d-4feb-bae2-51cb21be2f4e", code="bar_ristoranti.ristorante", name="Ristorante", name_en="Restaurant", kind="expense", parent_code="bar_ristoranti", sort_order=401, hint="cibo consumato o ordinato pronto, non la spesa al supermercato", hint_en="food eaten out or ordered ready-to-eat, not grocery shopping"),
    TaxonomyCategory(id="c66abf04-f458-4eab-a84f-c1c2bd94ec0b", code="bar_ristoranti.bar_caffetteria", name="Bar e caffetteria", name_en="Bar and coffee shop", kind="expense", parent_code="bar_ristoranti", sort_order=402),
    TaxonomyCategory(id="d1b97945-f683-4548-8ba6-15450c2979ac", code="bar_ristoranti.fast_food", name="Fast food", name_en="Fast food", kind="expense", parent_code="bar_ristoranti", sort_order=403),
    TaxonomyCategory(id="243420bb-ca3e-4844-baa6-664e0c7e692a", code="bar_ristoranti.delivery", name="Delivery", name_en="Delivery", kind="expense", parent_code="bar_ristoranti", sort_order=404),
    TaxonomyCategory(id="86d0811d-585c-49d9-9919-e453211f2664", code="bar_ristoranti.mensa", name="Mensa aziendale", name_en="Company canteen", kind="expense", parent_code="bar_ristoranti", sort_order=405),
    TaxonomyCategory(id="cec3c5b0-22fb-45b8-a7e6-d7ad1d1a6b27", code="trasporti", name="Trasporti", name_en="Transport", kind="expense", parent_code=None, sort_order=500),
    TaxonomyCategory(id="8bc9c730-a478-4377-a52a-3954e7c1c2cd", code="trasporti.carburante", name="Carburante", name_en="Fuel", kind="expense", parent_code="trasporti", sort_order=501, hint="benzina, diesel, GPL, colonnine di ricarica elettrica", hint_en="petrol, diesel, LPG, electric charging stations"),
    TaxonomyCategory(id="fc20ab4a-976f-4955-a4f3-4dbdfa6e51d2", code="trasporti.ricarica_elettrica", name="Ricarica elettrica", name_en="Electric charging", kind="expense", parent_code="trasporti", sort_order=502),
    TaxonomyCategory(id="93c37b55-bd1b-456d-a70f-b305cb60c623", code="trasporti.pedaggi", name="Pedaggi", name_en="Tolls", kind="expense", parent_code="trasporti", sort_order=503),
    TaxonomyCategory(id="e055b9c1-c03f-4a04-93ce-39227018353d", code="trasporti.parcheggi", name="Parcheggi", name_en="Parking", kind="expense", parent_code="trasporti", sort_order=504),
    TaxonomyCategory(id="1c22d099-c832-44f3-ad90-01fb6dedd337", code="trasporti.mezzi_pubblici", name="Mezzi pubblici", name_en="Public transport", kind="expense", parent_code="trasporti", sort_order=505),
    TaxonomyCategory(id="ef3fa413-1e41-4f01-90b0-0ff641fa81b0", code="trasporti.taxi_ncc", name="Taxi e NCC", name_en="Taxi and ride-hailing", kind="expense", parent_code="trasporti", sort_order=506),
    TaxonomyCategory(id="059bfad1-b59b-4685-97a3-01ad03684afd", code="trasporti.sharing", name="Sharing (auto/bici/monopattini)", name_en="Sharing (car/bike/scooter)", kind="expense", parent_code="trasporti", sort_order=507),
    TaxonomyCategory(id="cad20a71-79ab-4dba-81e8-b449b930388f", code="trasporti.treno", name="Treno", name_en="Train", kind="expense", parent_code="trasporti", sort_order=508),
    TaxonomyCategory(id="eacda5b1-6334-4286-a162-63e308d6deba", code="trasporti.aereo", name="Aereo", name_en="Flights", kind="expense", parent_code="trasporti", sort_order=509),
    TaxonomyCategory(id="d855a858-c771-429c-be35-e79c11b6e936", code="trasporti.noleggio_auto", name="Noleggio auto", name_en="Car rental", kind="expense", parent_code="trasporti", sort_order=510),
    TaxonomyCategory(id="ccf0fabc-2f38-48c8-a336-1b6ca90a6feb", code="trasporti.manutenzione_veicolo", name="Manutenzione veicolo", name_en="Vehicle maintenance", kind="expense", parent_code="trasporti", sort_order=511),
    TaxonomyCategory(id="71f8d997-ac08-419e-9fda-189633750ca0", code="trasporti.bollo_multe", name="Bollo e multe", name_en="Road tax and fines", kind="expense", parent_code="trasporti", sort_order=512),
    TaxonomyCategory(id="c9d50464-3ccb-4842-9c9e-cdb33f974128", code="salute", name="Salute e cura della persona", name_en="Health and personal care", kind="expense", parent_code=None, sort_order=600),
    TaxonomyCategory(id="b885ca78-b503-493c-bbe6-e5b0c1638464", code="salute.farmacia", name="Farmacia", name_en="Pharmacy", kind="expense", parent_code="salute", sort_order=601, hint="farmaci, parafarmaco, prodotti da farmacia", hint_en="medicines, over-the-counter health products, pharmacy items"),
    TaxonomyCategory(id="c615f6e8-6767-4f71-b65a-8f7656965ea6", code="salute.visite_mediche", name="Visite mediche", name_en="Medical visits", kind="expense", parent_code="salute", sort_order=602),
    TaxonomyCategory(id="207e77a6-4176-476c-bb9a-9feb249ab995", code="salute.dentista", name="Dentista", name_en="Dentist", kind="expense", parent_code="salute", sort_order=603),
    TaxonomyCategory(id="4e556332-3594-4bff-9cd3-60f7d41c53de", code="salute.analisi_esami", name="Analisi ed esami", name_en="Lab tests and exams", kind="expense", parent_code="salute", sort_order=604),
    TaxonomyCategory(id="4c0143f0-e43a-469e-995b-adc5928f13a2", code="salute.ottica", name="Ottica", name_en="Optician", kind="expense", parent_code="salute", sort_order=605),
    TaxonomyCategory(id="bdd5412e-7fa6-42cd-9a3a-3fabea743b20", code="salute.terapie", name="Fisioterapia e psicoterapia", name_en="Physiotherapy and psychotherapy", kind="expense", parent_code="salute", sort_order=606),
    TaxonomyCategory(id="a510dec0-528f-46e9-92c4-de4ade4ea1b5", code="salute.parrucchiere_estetica", name="Parrucchiere ed estetica", name_en="Hairdresser and beauty", kind="expense", parent_code="salute", sort_order=607),
    TaxonomyCategory(id="486d8da2-07ae-4827-90e9-a92f5809bfb2", code="shopping", name="Shopping", name_en="Shopping", kind="expense", parent_code=None, sort_order=700),
    TaxonomyCategory(id="cd4e8319-dc78-4a79-8256-806afa9b7f08", code="shopping.abbigliamento", name="Abbigliamento", name_en="Clothing", kind="expense", parent_code="shopping", sort_order=701),
    TaxonomyCategory(id="5fccf93c-de5d-4d76-92d2-bfcb7a296536", code="shopping.accessori", name="Accessori e gioielli", name_en="Accessories and jewelry", kind="expense", parent_code="shopping", sort_order=702),
    TaxonomyCategory(id="89129469-6e90-42b6-b627-c9da82fcfe08", code="shopping.elettronica", name="Elettronica", name_en="Electronics", kind="expense", parent_code="shopping", sort_order=703),
    TaxonomyCategory(id="83fcdb92-4a4b-4a36-afb6-0c4b52d0bbc3", code="shopping.informatica", name="Informatica", name_en="Computers", kind="expense", parent_code="shopping", sort_order=704),
    TaxonomyCategory(id="89451f8a-3ead-4379-9145-f1fd03289d69", code="shopping.libri_musica", name="Libri, musica e film", name_en="Books, music and movies", kind="expense", parent_code="shopping", sort_order=705),
    TaxonomyCategory(id="f4e1366d-421f-4461-8477-c6152a2b6bac", code="shopping.giochi", name="Giochi e videogiochi", name_en="Games and video games", kind="expense", parent_code="shopping", sort_order=706),
    TaxonomyCategory(id="eb64dcc1-ca66-405b-aec8-a2a023fad513", code="shopping.regali", name="Regali", name_en="Gifts", kind="expense", parent_code="shopping", sort_order=707),
    TaxonomyCategory(id="fee4bffb-85f7-4ad1-bbfc-37c911978e30", code="tempo_libero", name="Tempo libero", name_en="Leisure", kind="expense", parent_code=None, sort_order=800),
    TaxonomyCategory(id="dc0ba4a3-55d9-46ab-990b-9b73ee265eea", code="tempo_libero.cinema", name="Cinema", name_en="Cinema", kind="expense", parent_code="tempo_libero", sort_order=801),
    TaxonomyCategory(id="42f54d14-058f-437b-af15-120b9ee3073a", code="tempo_libero.teatro_concerti", name="Teatro e concerti", name_en="Theater and concerts", kind="expense", parent_code="tempo_libero", sort_order=802),
    TaxonomyCategory(id="f964ff19-61fc-4350-9fc6-df689b8878d2", code="tempo_libero.musei_eventi", name="Musei ed eventi", name_en="Museums and events", kind="expense", parent_code="tempo_libero", sort_order=803),
    TaxonomyCategory(id="e53ceba3-d225-4c9a-b85a-839203b7e6e5", code="tempo_libero.palestra_fitness", name="Palestra e fitness", name_en="Gym and fitness", kind="expense", parent_code="tempo_libero", sort_order=804),
    TaxonomyCategory(id="12e31f65-feed-4bf4-96a4-128d566ed3eb", code="tempo_libero.sport", name="Sport e attività", name_en="Sports and activities", kind="expense", parent_code="tempo_libero", sort_order=805),
    TaxonomyCategory(id="fe3c3b21-330d-4345-a74f-fbca3ffb638e", code="tempo_libero.hobby", name="Hobby", name_en="Hobbies", kind="expense", parent_code="tempo_libero", sort_order=806),
    TaxonomyCategory(id="9d1ce192-c4f4-48b2-9d38-9e7412014e56", code="abbonamenti", name="Abbonamenti", name_en="Subscriptions", kind="expense", parent_code=None, sort_order=900),
    TaxonomyCategory(id="a8493dbc-1dc0-4875-bd1e-d7e36a220cbf", code="abbonamenti.streaming", name="Streaming", name_en="Streaming", kind="expense", parent_code="abbonamenti", sort_order=901, hint="abbonamento video ricorrente (Netflix, Disney+, Prime Video)", hint_en="recurring video subscription (Netflix, Disney+, Prime Video)"),
    TaxonomyCategory(id="b3eb4eb8-4fea-4960-9fab-f19c40285bf5", code="abbonamenti.streaming_musica", name="Streaming musica", name_en="Music streaming", kind="expense", parent_code="abbonamenti", sort_order=902),
    TaxonomyCategory(id="fc21248e-72b0-4e21-9733-e6b008b8b91e", code="abbonamenti.software", name="Software", name_en="Software", kind="expense", parent_code="abbonamenti", sort_order=903),
    TaxonomyCategory(id="846abf8b-e8a7-425e-95ca-c66221056f95", code="abbonamenti.cloud_storage", name="Cloud e storage", name_en="Cloud and storage", kind="expense", parent_code="abbonamenti", sort_order=904),
    TaxonomyCategory(id="5215a297-caf5-465c-a9a9-19d494b8500d", code="viaggi", name="Viaggi e vacanze", name_en="Travel and vacations", kind="expense", parent_code=None, sort_order=1000),
    TaxonomyCategory(id="43a2d6a7-a783-4244-a24b-903fd8302e01", code="viaggi.alloggio", name="Alloggio", name_en="Lodging", kind="expense", parent_code="viaggi", sort_order=1001),
    TaxonomyCategory(id="9bc5570a-d2fd-4382-af85-f302a4fea1b4", code="viaggi.pacchetti_viaggio", name="Pacchetti viaggio", name_en="Travel packages", kind="expense", parent_code="viaggi", sort_order=1002),
    TaxonomyCategory(id="20f26540-04a1-4bde-9071-187c92bfbd4b", code="viaggi.escursioni", name="Escursioni e attività", name_en="Excursions and activities", kind="expense", parent_code="viaggi", sort_order=1003),
    TaxonomyCategory(id="92fc1b5d-e998-4009-a74c-25d5e2308c0c", code="istruzione", name="Istruzione e formazione", name_en="Education and training", kind="expense", parent_code=None, sort_order=1100),
    TaxonomyCategory(id="ea7e5f41-4770-47bc-b614-d4d4cbdf324b", code="istruzione.asilo_nido", name="Asilo nido", name_en="Nursery", kind="expense", parent_code="istruzione", sort_order=1101),
    TaxonomyCategory(id="5a8c1256-9dec-4222-b4b0-ac33767f7af0", code="istruzione.retta_scolastica", name="Retta scolastica", name_en="School fees", kind="expense", parent_code="istruzione", sort_order=1102),
    TaxonomyCategory(id="8363a5e5-903a-48f1-9f58-bfcf06181538", code="istruzione.universita", name="Università", name_en="University", kind="expense", parent_code="istruzione", sort_order=1103),
    TaxonomyCategory(id="61535915-2709-4dcd-b697-2340120ed8e3", code="istruzione.corsi_formazione", name="Corsi di formazione", name_en="Training courses", kind="expense", parent_code="istruzione", sort_order=1104),
    TaxonomyCategory(id="f36ce589-2a9f-4aa4-9d4e-fb9ef2de27f4", code="istruzione.libri_testo", name="Libri di testo", name_en="Textbooks", kind="expense", parent_code="istruzione", sort_order=1105),
    TaxonomyCategory(id="e43f8e26-79a9-41bb-9077-9ffd73c9253e", code="famiglia", name="Famiglia e figli", name_en="Family and children", kind="expense", parent_code=None, sort_order=1200),
    TaxonomyCategory(id="1ac1144c-75c1-4f4d-ba25-00428e6ad4ce", code="famiglia.babysitter", name="Babysitter", name_en="Babysitter", kind="expense", parent_code="famiglia", sort_order=1201),
    TaxonomyCategory(id="fea446af-a735-432d-bf1c-e7639ae87115", code="famiglia.abbigliamento_bambini", name="Abbigliamento bambini", name_en="Children's clothing", kind="expense", parent_code="famiglia", sort_order=1202),
    TaxonomyCategory(id="c28cd1c3-c599-40b5-9eb5-670acadc62ed", code="famiglia.attivita_extrascolastiche", name="Attività extrascolastiche", name_en="Extracurricular activities", kind="expense", parent_code="famiglia", sort_order=1203),
    TaxonomyCategory(id="8d1fb829-13bb-454b-9528-ded183bd16a6", code="famiglia.mantenimento", name="Assegni di mantenimento", name_en="Child/spousal support", kind="expense", parent_code="famiglia", sort_order=1204),
    TaxonomyCategory(id="a825b779-fecc-4131-a43f-a94dec73e21f", code="animali", name="Animali domestici", name_en="Pets", kind="expense", parent_code=None, sort_order=1300),
    TaxonomyCategory(id="48919563-e3b9-4346-8c95-a4b84b5994fc", code="animali.cibo", name="Cibo", name_en="Food", kind="expense", parent_code="animali", sort_order=1301),
    TaxonomyCategory(id="f3519df6-1573-4aa3-80b3-5a1ebf74e2a0", code="animali.veterinario", name="Veterinario", name_en="Veterinarian", kind="expense", parent_code="animali", sort_order=1302),
    TaxonomyCategory(id="eedf61df-af3a-4e88-b350-12866e425c3e", code="animali.toelettatura", name="Toelettatura", name_en="Grooming", kind="expense", parent_code="animali", sort_order=1303),
    TaxonomyCategory(id="4345f037-7e0d-4701-9c37-a6b13d1aea30", code="lavoro", name="Lavoro e professione", name_en="Work and profession", kind="expense", parent_code=None, sort_order=1400),
    TaxonomyCategory(id="8bbbfaf0-c090-4951-87da-07d2438914e5", code="lavoro.spese_professionali", name="Spese professionali", name_en="Professional expenses", kind="expense", parent_code="lavoro", sort_order=1401),
    TaxonomyCategory(id="9376ad72-3b85-4eb0-ae3b-e31131ea936c", code="lavoro.attrezzatura", name="Attrezzatura di lavoro", name_en="Work equipment", kind="expense", parent_code="lavoro", sort_order=1402),
    TaxonomyCategory(id="d58f1d22-6c5d-4443-b844-12a155206da2", code="lavoro.trasferte", name="Trasferte di lavoro", name_en="Business trips", kind="expense", parent_code="lavoro", sort_order=1403),
    TaxonomyCategory(id="b62743ce-8ab9-43cf-a85a-cc11a1f29c77", code="lavoro.contributi_previdenziali", name="Contributi previdenziali", name_en="Social security contributions", kind="expense", parent_code="lavoro", sort_order=1404),
    TaxonomyCategory(id="42dc2c77-4232-4b9f-b1f5-e8eae77e0c9d", code="lavoro.consulenze", name="Consulenze e commercialista", name_en="Consulting and accounting fees", kind="expense", parent_code="lavoro", sort_order=1405),
    TaxonomyCategory(id="963347b3-8853-465f-bd77-8515b5e51ded", code="tasse", name="Tasse e imposte", name_en="Taxes", kind="expense", parent_code=None, sort_order=1500),
    TaxonomyCategory(id="8b5a14da-36a9-49f3-beaf-80bc25a885b9", code="tasse.irpef", name="IRPEF (saldo e acconti)", name_en="Income tax (balance and advance payments)", kind="expense", parent_code="tasse", sort_order=1501),
    TaxonomyCategory(id="30ac667f-368d-4f78-9f35-aec0a54666f4", code="tasse.addizionali", name="Addizionali regionali e comunali", name_en="Regional and municipal surtaxes", kind="expense", parent_code="tasse", sort_order=1502),
    TaxonomyCategory(id="e17f8dda-bb8d-41bc-9361-bdc4eb4151ec", code="tasse.imu_tari", name="IMU e tributi locali", name_en="Property tax and local levies", kind="expense", parent_code="tasse", sort_order=1503),
    TaxonomyCategory(id="5642f897-378f-4455-a873-55f325324e65", code="tasse.imposta_bollo", name="Imposta di bollo", name_en="Stamp duty", kind="expense", parent_code="tasse", sort_order=1504),
    TaxonomyCategory(id="fb9b922c-c3fc-479d-88de-a069a7d5b41a", code="tasse.capital_gain", name="Imposta capital gain", name_en="Capital gains tax", kind="expense", parent_code="tasse", sort_order=1505),
    TaxonomyCategory(id="d78f1e91-fc64-4811-abc7-079476b93f34", code="assicurazioni", name="Assicurazioni", name_en="Insurance", kind="expense", parent_code=None, sort_order=1600),
    TaxonomyCategory(id="e02f1bd4-72ac-43c1-ad0e-2cc225bfe460", code="assicurazioni.auto", name="Auto e moto", name_en="Car and motorcycle", kind="expense", parent_code="assicurazioni", sort_order=1601),
    TaxonomyCategory(id="5ddc572b-5d99-4392-8874-c29e1520139c", code="assicurazioni.casa", name="Casa", name_en="Home", kind="expense", parent_code="assicurazioni", sort_order=1602),
    TaxonomyCategory(id="7a6a2598-7e09-43c3-9b7e-3c0285a7f11b", code="assicurazioni.salute", name="Salute", name_en="Health", kind="expense", parent_code="assicurazioni", sort_order=1603),
    TaxonomyCategory(id="20f877b7-3d29-4046-b592-6d3cddda0f95", code="assicurazioni.vita", name="Vita", name_en="Life", kind="expense", parent_code="assicurazioni", sort_order=1604),
    TaxonomyCategory(id="7bef0559-8115-46ea-8efc-8805accaeb9b", code="commissioni", name="Commissioni e spese bancarie", name_en="Fees and bank charges", kind="expense", parent_code=None, sort_order=1700),
    TaxonomyCategory(id="fe093e30-d51d-4d44-89d5-961d83d990d2", code="commissioni.canone_conto", name="Canone conto", name_en="Account fee", kind="expense", parent_code="commissioni", sort_order=1701),
    TaxonomyCategory(id="63ccdc1f-e8f2-4247-a8c7-013c129befd8", code="commissioni.canone_carta", name="Canone carta", name_en="Card fee", kind="expense", parent_code="commissioni", sort_order=1702),
    TaxonomyCategory(id="22a102da-9b40-44f4-9564-c43e36fba5af", code="commissioni.bonifico", name="Commissione bonifico", name_en="Transfer fee", kind="expense", parent_code="commissioni", sort_order=1703),
    TaxonomyCategory(id="26f2002b-e552-4657-ac04-f463c994dae8", code="commissioni.prelievo", name="Commissione prelievo", name_en="Withdrawal fee", kind="expense", parent_code="commissioni", sort_order=1704),
    TaxonomyCategory(id="313cf8bb-af01-446d-826c-abd04fa988b9", code="commissioni.cambio_valuta", name="Commissione cambio valuta", name_en="Currency exchange fee", kind="expense", parent_code="commissioni", sort_order=1705),
    TaxonomyCategory(id="87adb404-6883-4c26-94f2-bc6c24a053c4", code="commissioni.negoziazione", name="Commissione di negoziazione", name_en="Trading fee", kind="expense", parent_code="commissioni", sort_order=1706),
    TaxonomyCategory(id="1b0a5db0-b5a7-4772-b052-2b041f0d5ca6", code="commissioni.interessi_passivi", name="Interessi passivi", name_en="Interest paid", kind="expense", parent_code="commissioni", sort_order=1707),
    TaxonomyCategory(id="b886502c-826a-4710-9e75-7919437a20af", code="finanziamenti", name="Prestiti e finanziamenti", name_en="Loans and financing", kind="expense", parent_code=None, sort_order=1800),
    TaxonomyCategory(id="5e65fb5c-0b55-433f-b010-382c119c587c", code="finanziamenti.rata_mutuo", name="Rata mutuo", name_en="Mortgage installment", kind="expense", parent_code="finanziamenti", sort_order=1801),
    TaxonomyCategory(id="d3b5d61c-879b-4660-9c37-4a4f765ddb84", code="finanziamenti.interessi_mutuo", name="Interessi mutuo", name_en="Mortgage interest", kind="expense", parent_code="finanziamenti", sort_order=1802),
    TaxonomyCategory(id="47902544-0804-4b0f-8751-1a92d689f128", code="finanziamenti.rata_prestito", name="Rata prestito personale", name_en="Personal loan installment", kind="expense", parent_code="finanziamenti", sort_order=1803),
    TaxonomyCategory(id="171d8616-885d-4b7c-ba6b-d5ff00d65521", code="donazioni", name="Donazioni e beneficenza", name_en="Donations and charity", kind="expense", parent_code=None, sort_order=1900),
    TaxonomyCategory(id="5f13d4ca-09e5-482e-85e0-e5b8539b8886", code="donazioni.beneficenza", name="Beneficenza", name_en="Charity", kind="expense", parent_code="donazioni", sort_order=1901),
    TaxonomyCategory(id="b4d72698-ee85-4ec6-8e3b-f800021b6028", code="entrate", name="Entrate", name_en="Income", kind="income", parent_code=None, sort_order=2000),
    TaxonomyCategory(id="12f308d1-3783-4526-8d21-96cb3be78f4b", code="entrate.stipendio", name="Stipendio", name_en="Salary", kind="income", parent_code="entrate", sort_order=2001),
    TaxonomyCategory(id="d0416de4-4764-4fa7-b98c-ff48ff11843c", code="entrate.tredicesima", name="Tredicesima e quattordicesima", name_en="13th and 14th month pay", kind="income", parent_code="entrate", sort_order=2002),
    TaxonomyCategory(id="e6e15bea-54bf-4c74-a2ce-289cd4c71ab2", code="entrate.bonus_premi", name="Bonus e premi", name_en="Bonuses and awards", kind="income", parent_code="entrate", sort_order=2003),
    TaxonomyCategory(id="7ad73903-ad84-4116-8fc8-5b202c3ba66b", code="entrate.pensione", name="Pensione", name_en="Pension", kind="income", parent_code="entrate", sort_order=2004),
    TaxonomyCategory(id="5beed5d8-57f0-4411-9830-7ce5473a4421", code="entrate.freelance", name="Compensi freelance", name_en="Freelance income", kind="income", parent_code="entrate", sort_order=2005),
    TaxonomyCategory(id="4a451b87-b503-4528-831e-e9f03396eadd", code="entrate.affitti_attivi", name="Affitti attivi", name_en="Rental income", kind="income", parent_code="entrate", sort_order=2006),
    TaxonomyCategory(id="535d2726-4f94-4f86-9532-db6b6f095c23", code="entrate.dividendi", name="Dividendi", name_en="Dividends", kind="income", parent_code="entrate", sort_order=2007),
    TaxonomyCategory(id="3f5915b0-1285-4d39-8862-91cdf36f03c4", code="entrate.interessi_attivi", name="Interessi attivi", name_en="Interest earned", kind="income", parent_code="entrate", sort_order=2008),
    TaxonomyCategory(id="0b87d9f4-9a44-4a58-a820-527f79cede56", code="entrate.rimborsi_spese", name="Rimborsi spese", name_en="Expense reimbursements", kind="income", parent_code="entrate", sort_order=2009),
    TaxonomyCategory(id="59daeef0-aaaf-4408-b7c4-fce0ebdc9d80", code="entrate.rimborsi_fiscali", name="Rimborsi fiscali", name_en="Tax refunds", kind="income", parent_code="entrate", sort_order=2010),
    TaxonomyCategory(id="84e22ed0-3eee-4681-b637-e95c5183cd65", code="entrate.altro", name="Entrate - altro", name_en="Income - other", kind="income", parent_code="entrate", sort_order=2011),
    TaxonomyCategory(id="74b5800a-9095-4055-a445-06d8cae02ff1", code="trasferimenti", name="Trasferimenti", name_en="Transfers", kind="transfer", parent_code=None, sort_order=2100),
    TaxonomyCategory(id="6f03ff7a-eb13-4d49-a9dd-9c104862543f", code="trasferimenti.giroconto", name="Giroconto tra conti propri", name_en="Transfer between own accounts", kind="transfer", parent_code="trasferimenti", sort_order=2101),
    TaxonomyCategory(id="92cb92c9-5202-4692-a78e-6ccd709a8031", code="trasferimenti.prelievo_contanti", name="Prelievo contanti", name_en="Cash withdrawal", kind="transfer", parent_code="trasferimenti", sort_order=2102),
    TaxonomyCategory(id="f5ee1d0a-c53a-48db-91e2-8063defd9378", code="trasferimenti.versamento_contanti", name="Versamento contanti", name_en="Cash deposit", kind="transfer", parent_code="trasferimenti", sort_order=2103),
    TaxonomyCategory(id="c36c6403-cb4e-4f40-9a66-c16249e00eb8", code="trasferimenti.ricarica_carta", name="Ricarica carta", name_en="Card top-up", kind="transfer", parent_code="trasferimenti", sort_order=2104),
    TaxonomyCategory(id="772059d2-883d-4dc2-850d-74a9c61917f4", code="investimenti", name="Investimenti", name_en="Investments", kind="investment", parent_code=None, sort_order=2200),
    TaxonomyCategory(id="5315b817-43d0-4b3c-9945-5ee3f5392f83", code="investimenti.acquisto_titoli", name="Acquisto titoli", name_en="Securities purchase", kind="investment", parent_code="investimenti", sort_order=2201),
    TaxonomyCategory(id="7df9b258-9e8e-44b2-a0c1-4d35d5782bba", code="investimenti.vendita_titoli", name="Vendita titoli", name_en="Securities sale", kind="investment", parent_code="investimenti", sort_order=2202),
    TaxonomyCategory(id="a0826ff0-2c18-486f-9bfc-978e34664a09", code="investimenti.versamento_pac", name="Versamento PAC", name_en="Recurring investment plan deposit", kind="investment", parent_code="investimenti", sort_order=2203),
    TaxonomyCategory(id="221c2bad-1814-47b7-95a2-397333b874d7", code="investimenti.acquisto_cripto", name="Acquisto criptovalute", name_en="Crypto purchase", kind="investment", parent_code="investimenti", sort_order=2204),
    TaxonomyCategory(id="d7470985-dd5c-4008-a95f-95d3e07f6289", code="investimenti.vendita_cripto", name="Vendita criptovalute", name_en="Crypto sale", kind="investment", parent_code="investimenti", sort_order=2205),
    TaxonomyCategory(id="c1ec5aa7-85be-4f03-8d95-348f9c922ef5", code="investimenti.deposito_conto_titoli", name="Deposito su conto titoli", name_en="Deposit to brokerage account", kind="investment", parent_code="investimenti", sort_order=2206),
    TaxonomyCategory(id="7c53f340-b39c-41ec-8430-dc965a5ea2ed", code="investimenti.prelievo_conto_titoli", name="Prelievo da conto titoli", name_en="Withdrawal from brokerage account", kind="investment", parent_code="investimenti", sort_order=2207),
    TaxonomyCategory(id="187f5a5c-5408-4e8b-9d7f-f07144431dc4", code="altro", name="Altro", name_en="Other", kind="neutral", parent_code=None, sort_order=2300),
    TaxonomyCategory(id="e100683d-8788-4a14-b59c-78c306d4fb81", code="altro.da_classificare", name="Da classificare", name_en="To be classified", kind="neutral", parent_code="altro", sort_order=2301),
    TaxonomyCategory(id="a70a5b27-a56e-4010-af75-658f0e3d1c76", code="altro.bonifico_a_terzi", name="Bonifico a terzi (scopo non specificato)", name_en="Transfer to third party (unspecified purpose)", kind="neutral", parent_code="altro", sort_order=2302, hint="usa questa SOLO se nessun'altra categoria descrive lo scopo del bonifico", hint_en="use this ONLY if no other category describes the purpose of the transfer"),
    TaxonomyCategory(id="d41606f2-785d-4a3c-ae70-3c5a1b4c87fc", code="altro.bonifico_ricevuto", name="Bonifico ricevuto (origine non specificata)", name_en="Transfer received (unspecified origin)", kind="neutral", parent_code="altro", sort_order=2303, hint="usa questa SOLO se nessun'altra categoria descrive l'origine del bonifico", hint_en="use this ONLY if no other category describes the origin of the transfer"),
    TaxonomyCategory(id="3a6e4aba-c644-47f9-90a3-7b9d89a44837", code="altro.contanti", name="Contanti non tracciati", name_en="Untracked cash", kind="neutral", parent_code="altro", sort_order=2304),
]

TAXONOMY_BY_CODE: dict[str, TaxonomyCategory] = {c.code: c for c in TAXONOMY}
