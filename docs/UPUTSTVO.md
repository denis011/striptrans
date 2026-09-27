# StripTrans — instalacija i uputstvo za korišćenje

Kako se aplikacija instalira i kako se u njoj radi, od uvoza stripa do izvoza albuma.

---

## Deo 1 — Instalacija

### 1.1 Šta je potrebno

| Komponenta | Namena | Napomena |
|---|---|---|
| Windows 10/11 | domaćin | |
| WSL2 sa Ubuntu distribucijom | tu radi kod i Docker komande | `wsl --install` u PowerShell-u kao administrator |
| Docker Desktop | kontejneri (api, worker, frontend) | Settings → Resources → WSL integration: uključiti za Ubuntu |
| llama-server (llama.cpp, Vulkan) za Windows | OCR na grafičkoj kartici | testirano sa b11189 i AMD RX 6800 (16 GB VRAM) |
| git, make, curl u WSL-u | preuzimanje i pokretanje | `sudo apt install git make curl` |
| OpenRouter nalog sa kreditom | AI prevod i glosar (bez ključa prevod ne radi) | ceo broj košta oko 0,05 $ (ključ može imati svoj limit, proveri ga na openrouter.ai → Keys) |
| Prostor na disku | | Docker slike ≈2,5 GB (+1,9 GB za E2E test), OCR model ≈6 GB, ONNX modeli 0,5 GB, oko 350 MB po obrađenom broju sa jednim izvozom |

### 1.2 llama-server na Windows-u (OCR)

OCR radi model Qwen2.5-VL 7B u **llama-serveru** (llama.cpp) na grafičkoj kartici Windows-a. Do v1.1 je to radila
Ollama; llama-server je iste tačnosti i ~1,9× brži (`docs/benchmarks/ocr-llamaserver.md`).

1. Sa https://github.com/ggml-org/llama.cpp/releases preuzmi Windows Vulkan izdanje
   (`llama-b…-bin-win-vulkan-x64.zip`; testirano sa b11189) i raspakuj ga u `C:\llm-bench\vulkan\`
   (tu treba da bude `llama-server.exe`).
2. Modeli (≈6 GB, u `C:\llm-bench\models\`, sa proverom SHA256), iz WSL-a u folderu projekta:
   ```bash
   make llm-models
   ```
3. Drugi folder se podešava u `.env`: `LLAMA_SERVER_DIR=D:\neki\folder` (u njemu `vulkan\` i `models\`).
4. Ako Windows Firewall pita za pristup za `llama-server.exe`, dozvoli ga za privatne mreže (Docker mu pristupa
   preko `host.docker.internal:8081`).

Server se ne pokreće ručno: `make up` (ili samo `make llm`) proveri da li radi, ugasi Ollamu ako je ostala upaljena
(dva modela ne staju u 16 GB VRAM-a) i pokrene llama-server sa izmerenim podešavanjima (bez flash attention,
slika bloka 1024–1280 tokena). Učitavanje traje ~30–50 s; log je u `C:\llm-bench\llama-server.log`.

**Ollama umesto llama-servera:** ako ti je lakše, OCR radi i preko Ollame (instalacija sa https://ollama.com, pa
u PowerShell-u `ollama pull qwen2.5vl:7b`). Tačnost je skoro ista, a OCR je ~2× sporiji (5 s po bloku). Nije potrebno
ništa podešavati: podrazumevano `OCR_SERVER=auto` u `.env` znači da `make up` pokrene llama-server ako je
instaliran, a inače Ollamu, i da aplikacija koristi onaj koji odgovara (ako se ugasi usred rada, prelazi na drugi bez
restarta). Izričit izbor: `OCR_SERVER=llama-server` ili `OCR_SERVER=ollama`. Status strana piše koji server radi.

**Onomatopeje i natpisi su najteži za OCR** (stilizovana slova): ni jači modeli ih ne čitaju bitno bolje. Zato
ih pregledaj u lekturi; blok na kome se model „zaglavio" (npr. „SSSSSS…") aplikacija skrati i označi za proveru,
a natpis bez ijednog slova (bar-kod, brojevi) ostavi prazan.
NVIDIA kartice: llama.cpp ima CUDA i Vulkan izdanja, a Ollama radi sa NVIDIA karticama; nije testirano.

**Prelazak sa Ollame:** posle prvog `make up` sa llama-serverom isključi automatsko pokretanje Ollame (ikonica u
traci → Settings, ili Task Manager → Startup apps → Ollama → Disable). Ollama i njeni modeli (≈12 GB) mogu da se
uklone (Settings → Apps → Ollama → Uninstall, pa folder `%USERPROFILE%\.ollama`).

### 1.3 Kod i podešavanja (u WSL-u)

```bash
git clone <putanja-do-repozitorijuma> ~/claude/striptrans
```

```bash
cd ~/claude/striptrans && cp .env.example .env
```

U `.env` upiši ključ sa https://openrouter.ai/keys:

```
OPENROUTER_API_KEY=sk-or-...
```

Ostale vrednosti mogu ostati podrazumevane (opisane su u `.env.example`). Ključ se ne sme
slati nikome i ne ide u git (`.env` je u `.gitignore`).

### 1.4 Modeli za detekciju i brisanje teksta

```bash
make models
```

Skripta preuzima ONNX modele čiste licence (detektor oblačića i teksta, LaMa za brisanje preko crteža; oba
Apache-2.0) u `models/` i proverava im SHA256. Ponovno pokretanje preskače ono što je već preuzeto.

**Neobavezno, za onomatopeje:**

```bash
make models-onomatopeje
```

preuzima comic-text-detector: on predlaže okvire za onomatopeje koje detektor oblačića ne vidi i pomaže da se
slova onomatopeje preko crteža obrišu cela. Njegov izvorni projekat je pod licencom GPL-3.0, pa ga preuzmi samo
ako ti ta licenca odgovara. Bez njega aplikacija radi normalno, samo okvire onomatopeja crtaš ručno (N), a brisanje
preko crteža se oslanja na poteze mastila (ponekad ostane deo slova — tada pomaže četkica).

### 1.5 Pokretanje

```bash
make up
```

`make up` prvo proveri llama-server na Windows-u i pokrene ga ako ne radi (1.2), pa izgradi i podigne kontejnere. Prvi put traje
nekoliko minuta. Posle toga:

- aplikacija: http://localhost:5173
- stanje sistema: http://localhost:5173/status (baza, worker i llama-server treba da budu zeleni)
- API dokumentacija: http://localhost:8000/docs

Zaustavljanje je `make down`. Podaci (baza, slike, fontovi, izvozi) ostaju u Docker volume-u `striptrans_data`.

### 1.6 Ažuriranje

```bash
git pull && make up
```

Migracije baze se izvršavaju same pri startu, a baza se pre toga kopira u `/data/backups/`.

Verzije Python paketa su zaključane u `backend/constraints.txt`, pa svaki build (stabilno i razvojno okruženje) dobija
iste verzije. Nadogradnja paketa: izmeni verziju u tom fajlu, pa `make up`, `make test` i `make lint` (prvo u razvojnom
okruženju).

### 1.7 Rezervna kopija podataka

Pre kopiranja zaustavi aplikaciju (`make down`), da baza bude u mirnom stanju.

```bash
docker run --rm -v striptrans_data:/data -v "$PWD":/backup alpine tar czf /backup/striptrans-data.tgz -C /data .
```

Vraćanje kopije (briše trenutne podatke u volume-u):

```bash
docker run --rm -v striptrans_data:/data -v "$PWD":/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/striptrans-data.tgz -C /data"
```

### 1.8 Provera instalacije (opciono)

```bash
make test
```

```bash
make test-e2e
```

`make test` pokreće testove backenda i frontenda. `make test-e2e` radi dok je aplikacija podignuta: napravi mali
probni strip, očisti ga i izveze u CBZ i PDF, pa ga obriše.

### 1.9 Kad nešto ne radi

| Simptom | Rešenje |
|---|---|
| Status: llama-server nedostupan | `make llm` (pokreće ga na Windows-u). Ako i dalje ne radi, pogledaj `C:\llm-bench\llama-server.log` i firewall (1.2). Poslovi OCR-a za to vreme čekaju u redu i nastavljaju sami. |
| OCR je spor (desetine sekundi po bloku) | u logu servera treba da piše da je model na Vulkan uređaju (grafička); proveri da Ollama ili drugi program ne drži VRAM. |
| Nema modela u listi za prevod | proveri `OPENROUTER_API_KEY` u `.env`, pa pokreni `docker compose up -d` (`restart` ne učitava novi `.env`) |
| Prevod javlja grešku 402 | na OpenRouter-u je potrošen kredit |
| Worker: crveno na statusnoj strani | `docker compose logs worker`, pa `docker compose up -d` |
| Port 5173 ili 8000 je zauzet | zatvori drugi program koji ga koristi ili promeni port u `docker-compose.yml` |
| Stari font posle zamene | osveži stranu (Ctrl+F5) |

---

### 1.10 Stabilno i razvojno okruženje

Aplikacija sa kojom se radi (lektura, izvoz) je **stabilna**: folder `~/claude/striptrans`, grana `main`,
adresa http://localhost:5173. Nove funkcionalnosti se prave u **razvojnom** okruženju, da nedovršen kod i probe
ne diraju prave projekte:

| | Stabilno (**PROD**) | Razvojno (**DEV**) |
|---|---|---|
| folder | `~/claude/striptrans` (`main`) | `~/claude/striptrans-dev` (grana `feature/…` ili `fix/…`) |
| adresa | http://localhost:5173 (API :8000) | http://localhost:5174 (API :8001) |
| podaci | prave baze i projekti | kopija (Docker volume `striptrans-dev_data`) |

- **DEV se prepoznaje po crvenom okviru** oko cele strane i natpisu „DEV — razvojna kopija, izmene se ne čuvaju“ na dnu,
  a naslov taba počinje sa „DEV —“. Lektura, čišćenje i izvoz rade se samo u PROD-u (bez okvira).
- Prvo pravljenje (jednom, iz stabilnog foldera): `make dev-setup`. Napravi `git worktree`, njegov `.env` (isti
  ključevi, uz `COMPOSE_FILE` sa `docker-compose.dev.yml`), podigne kontejnere i kopira podatke (~3 GB).
- U razvojnom folderu sve `make` komande (`up`, `test`, `lint`, `test-e2e`) rade nad razvojnim kontejnerima.
- Sveža kopija podataka: `make dev-data` u razvojnom folderu. Poslovi iz reda stabilnog okruženja se u kopiji
  otkazuju, da se OCR ne bi radio dvaput. llama-server je zajednički, pa istovremen OCR u oba okruženja ide sporije.
- Nova funkcionalnost: u razvojnom folderu `git switch -c feature/ime main`; posle provere i odobrenja se spaja u
  `main` (`git merge --no-ff`) i stabilno okruženje se samo osveži (kontejneri prate kod). Detalji su u
  `docs/PLAN.md`, odeljak „Grane, okruženja i izdanja".

## Deo 2 — Korišćenje

### 2.1 Tok rada ukratko

Strana projekta vodi kroz isti redosled, sa brojevima i stanjem svakog koraka (odeljak 2.3):

1. **Uvezi stranice**: novi projekat na početnoj strani (serijal, broj, naslovi, fajlovi originala i opciono
   srpskog izdanja kao reference), a kasnije stranice prevlačenjem na stranu projekta.
2. **Označi stranice koje se preskaču** (naslovna, impresum, reklame): dugme ⊘ na sličici.
3. **Pronađi blokove i pročitaj tekst (OCR)**.
4. **Prevedi**.
5. **Lektura**: Scenario (čitanje van aplikacije) i editor, stranicu po stranicu.
6. **Očisti originalni tekst**.
7. **Doteraj slaganje u editoru**: crven tekst ne staje, a panel kaže koji red i za koliko piksela.
8. **Izvezi album** u CBZ, PDF ili ZIP.

Koraci 3, 4 i 6 mogu i odjednom, dugmetom „Pripremi ceo album".

### 2.2 Projekti i uvoz

- Na početnoj strani su projekti sa sličicom naslovne i brojem stranica. Forma „Novi projekat" prima fajlove
  prevlačenjem ili izborom: CBZ/CBR, ZIP, RAR, 7z, PDF ili pojedinačne slike (JPG, PNG, WEBP, TIFF…). Ekstenzija
  nije bitna; `.cbr` koji je zapravo ZIP radi normalno.
- **Referentno izdanje** (npr. srpsko izdanje istog broja) je opciono. U editoru se prikazuje uporedo, a koristi se i
  za predloge glosara.
- Na strani projekta:
  - tabovi „Original" i „Referenca" sa sličicama;
  - stranice se dodaju prevlačenjem novih fajlova;
  - redosled se menja prevlačenjem sličica, a „Vrati izvorni redosled" poništava izmene;
  - ✕ na sličici briše stranicu;
  - **⊘ na sličici preskače stranicu**: takva stranica se ne obrađuje (bez OCR-a, prevoda i čišćenja), ali u album
    ulazi neizmenjena. Tako se označavaju naslovna, impresum i reklame. Preskočena sličica je siva i bleda, a
    dugme ostaje uključeno dok se ne klikne ponovo;
  - dugmad: „Izvoz albuma", „Glosar", „Scenario", „CSV", „Otvori pregled", „Obriši projekat".

### 2.3 Koraci obrade (strana projekta)

Strana projekta je spisak od osam numerisanih koraka. Uz svaki korak piše dokle se stiglo, a gotov korak ima
zelenu kvačicu umesto broja. Preskočene stranice se ne broje.

| Korak | Stanje koje se vidi | Dugmad |
|---|---|---|
| **1. Uvezi stranice** | broj stranica originala i reference | (fajlovi se prevlače u polje iznad sličica) |
| **2. Označi stranice koje se preskaču** | koje su preskočene | (dugme ⊘ na sličici) |
| **3. Pronađi blokove i pročitaj tekst (OCR)** | koliko stranica je obrađeno; ako je obrada bila prekinuta, piše i koliko je blokova ostalo nepročitano — „Obradi ceo projekat" ih dočita, ne dirajući ostale | OCR model, „Zameni postojeće blokove" (briše ručno ispravljene blokove — pažljivo), „Obradi ceo projekat" |
| **4. Prevedi** | koliko blokova je bez prevoda, u nacrtu, izmenjeno, odobreno | model prevoda, „Ponovo prevedi nacrte", „Prevedi ceo projekat" |
| **5. Lektura** | koliko stranica je lektorisano | Scenario, CSV, Glosar |
| **6. Očisti originalni tekst** | koliko stranica je očišćeno | „Očisti ceo projekat" |
| **7. Doteraj slaganje u editoru** | — | Otvori pregled, „Ponovo izmeri oblačiće" (aktivno kad je bar jedna strana očišćena) |
| **8. Izvezi album** | kada je bio poslednji izvoz; ako je album menjan posle toga, piše „album je menjan posle toga" i korak nije označen kao gotov | Izvoz albuma |

Iznad koraka je prečica **„Pripremi ceo album"**: koraci 3, 4 i 6 odjednom. Urađeno se preskače, pa se može
pokrenuti ponovo posle ispravki.

Posao radi u pozadini i nastavlja se i ako se kontejneri restartuju. Može se prekinuti dugmetom uz napredak.

### 2.4 Editor stranice

Otvara se klikom na sličicu. Gore su dve niske trake, u sredini je stranica, desno lista blokova, a na dnu sličice
(zelen okvir znači lektorisanu stranicu).

**Gornja traka:** StripTrans (početna), naziv projekta (nazad na projekat), ‹ strana › , prikaz (Cela, Širina,
1:1), oznake stranice kao prekidači (**OCR proveren**, **Lektorisana**, **Preskoči**), dugmad za sakrivanje sličica
i panela blokova i prekidač teme (kao sistem → svetla → tamna; izbor se pamti u browseru).

**Traka alata**, s leva nadesno:
- režim rada, uvek je uključen samo jedan: **Izbor**, **Blok** (novi blok, N), **Četkica** (B), **Tekst** (uređivanje
  složenog prevoda, T). Isti taster ili Esc vraća na Izbor;
- **Blokovi ▾**: Spoji, Dupliraj, Obriši, Automatski redosled;
- **Obradi** (detekcija i OCR stranice) i **OCR ▾** (OCR model, „Čitaj nov blok", Pročitaj izabrane);
- **Prevedi** (cela stranica) i **Prevod ▾** (model prevoda);
- **Očisti** (briše originalni tekst);
- desno **Prikaz ▾** (blokovi, prevod na slici, očišćeno, uporedo sa referencom, samo upozorenja), **Fontovi ▾**
  (font za govor i za onomatopeje, Dodaj font…) i **Sačuvaj ▾** (stranica kao JPG ili PNG);
- kad je uključena četkica, u istoj traci su njen režim i veličina.

Meni se zatvara klikom van njega ili tasterom Esc; radnja iz menija ga zatvara, a izbor (kvačica, model) ga
ostavlja otvorenim.

**Pregled:**
- točkić miša zumira, a prevlačenje pomera stranicu;
- u meniju Prikaz: „Uporedo sa referencom" prikazuje srpsko izdanje pored originala, „Prikaži blokove" okvire
  blokova (boja označava tip), „Očišćeno" stranicu bez originalnog teksta, a „Prevod na slici" složen prevod.

**Blokovi (OCR):**
- tipovi su Govor, Misao, Naracija, Onomatopeja, Ostalo (natpisi, table) i Naslov (naslov priče). Tip određuje
  čišćenje i slaganje, pa ga vredi ispraviti;
- režim **Blok** (N): prevuci pravougaonik preko teksta. Ako je uključeno „Čitaj nov blok" (meni OCR), tekst se
  odmah pročita;
- **slobodan tekst** (tekst koga nema u originalu, npr. napomena prevodioca ili dodatak na naslovnoj): isključi
  „Čitaj nov blok" u meniju OCR, nacrtaj blok (N) gde treba, polje za original ostavi prazno, a svoj tekst upiši
  u polje za prevod. Tip, font, boja, obrub i „Uklopi u okvir" rade kao kod svakog bloka. Blok bez originalnog
  teksta se pri čišćenju nikad ne briše, pa crtež ispod njega ostaje netaknut;
- **AI prepravka natpisa** (naslov, natpis, onomatopeja; izabran blok sa originalnim tekstom i prevodom): u panelu
  **„Prepravi AI-jem"** i izbor „kvalitetno (~0,07 $)" ili „jeftino (~0,03 $)". Model za slike crta prevod istim
  slovima na isečku originala (za ~5–10 s); predlog se vidi uz original. **Proveri slova** — model ume da pogreši
  (npr. „TUMP" umesto „TUP"): „Pokušaj ponovo" daje novu varijantu (svaka se plaća), „Prihvati" je stavlja kao
  zakrpu (okvir bloka i nova slova koja iz njega izlaze), iznad složenog prevoda (Ctrl+Z je vraća). Svi plaćeni
  predlozi bloka ostaju u panelu kao sličice: klik bira predlog, a „Prihvati" ga primenjuje **bez novog plaćanja**
  (npr. posle Ctrl+Z); „Nov predlog" je jedini koji se plaća. Isečak ide na
  OpenRouter (Google). Zbir troška piše na strani projekta, u koraku 7. Merenje: `docs/benchmarks/ai-natpisi.md`;
- **Zakrpa slikom** (režim „Zakrpe", taster P) je rezerva za ono što automatika ne pokrije — tabla sa teksturom,
  logotip, naslov preko crteža. „Izvezi isečak" daje PNG izabranog bloka (ili cele stranice) u punoj rezoluciji;
  doteraš ga u GIMP-u ili Photoshop-u i vratiš dugmetom „Dodaj zakrpu…". Zakrpa se pomera, uvećava i rotira
  mišem, ima providnost i prekidač „Iznad teksta", a briše se tasterom Delete. Ulazi u izvoz isto kao u editoru;
- **Poništi** i **Ponovi** (strelice u traci alata, Ctrl+Z i Ctrl+Shift+Z) vraćaju poslednjih 30 izmena na
  stranici: tekst, prevod, okvire, tip bloka, stil, slova naslova, brisanje i spajanje blokova, obradu i prevod
  stranice, kao i poteze četkicom. Istorija se pamti na serveru, pa ostaje i posle osvežavanja stranice, a svaka
  stranica ima svoju;
- klik bira blok, a Shift ili Ctrl + klik bira više blokova. Okvir se pomera i menja ručkama;
- meni Blokovi (Spoji, Dupliraj, Obriši, Automatski redosled) radi nad izabranim blokovima. U listi se redosled
  menja strelicama ↑/↓;
- R ponovo čita izabrane blokove izabranim OCR modelom;
- **Obradi** radi detekciju i OCR samo za ovu stranicu;
- prekidač **OCR proveren** u gornjoj traci označava da je tekst originala proveren.

**Prevod i lektura:**
- **Prevedi** prevodi celu stranicu modelom izabranim u meniju Prevod. U listi, uz svaki blok: „Prevedi" (ponovo), „Kraće"
  (skraćena verzija) i odobravanje;
- ispod prevoda se vide upozorenja: nepoznata reč (klik je dodaje u rečnik serijala), izraz iz glosara koji nije
  upotrebljen, predugačak prevod i **„nije srpski: …"** za hrvatsku ili ijekavsku reč (UVIJEK, OVDJE, TOČNO), koju
  pravopisni rečnik inače prihvata. TISUĆU, TKO, NETKO i NITKO aplikacija sama zamenjuje sa HILJADU, KO, NEKO i NIKO
  u novim prevodima;
- „Samo upozorenja" (meni Prikaz) prikazuje samo blokove sa upozorenjima;
- **Ctrl+Enter** odobrava prevod bloka i prelazi na sledeći neodobren blok;
- **Ctrl+Shift+Enter** odobrava sve prevode na stranici, označava stranicu kao lektorisanu i prelazi na sledeću;
- Enter u polju prevoda je ručni prelom reda u oblačiću: tu obavezno počinje nov red, a deo koji je duži od
  oblačića se dalje prelama sam (dovoljan je jedan Enter, npr. pre reda uz obod šešira). Kad je Enter na kraju
  svakog reda, raspored ostaje tačno kako je upisan; red koji ne staje je crven, a panel kaže koji je.

**Čišćenje:**
- **Očisti** briše originalni tekst. Govor, misao i naracija se prekrivaju bojom oblačića. Onomatopeje i
  natpisi (Ostalo) se brišu preko crteža samo ako imaju prevod različit od originala;
- režim **Četkica** (B) ispravlja masku čišćenja. Prevlači se preko mesta, uz izbor režima i veličine:
  - *obriši tekst (belo)*: ostatak slova se prekriva bojom okoline;
  - *obriši preko crteža*: LaMa dopunjuje crtež;
  - *vrati original*: vraća piksele originala (kad je čišćenje obrisalo deo crteža);
- zum ostaje isti posle poteza četkicom;
- ako se blokovi menjaju posle čišćenja, „Pripremi ceo album" će tu stranicu ponovo očistiti.

**Slaganje teksta (lettering):**
- font za govor i font za onomatopeje su zajednički za ceo serijal i biraju se u meniju Fontovi. „Dodaj font…"
  prima TTF ili OTF koji ima slova Č, Ć, Ž, Š i Đ;
- tekst se slaže automatski: veličina slova kao u originalu, redovi po obliku oblačića, rastavljanje reči po srpskim
  pravilima. Crven tekst ne staje u oblačić: skrati prevod („Kraće"), smanji slova ili pomeri tekst;
- režim **Tekst** (T): tekst se prevlači, ugaone ručke menjaju veličinu, a ručka iznad okvira rotira;
- **izmena teksta na samoj slici**: dvoklik na složen tekst (režim Tekst) ili na okvir bloka (režim Izbor)
  otvara polje tačno tamo gde tekst i stoji, slovima i veličinom kojom će biti složen. **Ctrl+Enter** ili klik
  van polja snima, **Esc** odustaje, Enter je nov red. Snimanje je isto kao iz panela (prevod se piše velikim
  slovima, status prelazi u „izmenjeno"), pa se poništava sa Ctrl+Z;
- u panelu izabranog bloka:
  - A− / A+ menja veličinu slova, a dugmad za prored razmak između redova;
  - poravnanje: ⇤ levo, ↔ centar, ⇥ desno, ☰ obostrano (poslednji red ostaje centriran); levo i desno
    poravnanje daje svim redovima istu ivicu;
  - ispravljanje rotacije i font samo za taj blok;
  - **Uklopi u okvir** (uredničke strane, impresum, pisma čitalaca): tekst se prelama po širini okvira bloka i
    puni ga, a slova se biraju slobodno — najveća sa kojima ceo tekst staje, i sitnija od granice od 3/4 koja važi
    za oblačiće. A−/A+ ih smanjuje ili povećava, ≡−/≡+ menja prored, ☰ daje obostrano poravnanje; prazan red u
    prevodu deli pasuse. Veličinu teksta tada određuje okvir bloka, pa se tekst doteruje pomeranjem ivica okvira;
  - **Boja** i **Obrub** (za naslovnu i kolor strane): „A" je automatska boja (crno, a belo na tamnoj
    podlozi), zatim bela, crna, žuta i crvena, i polje za bilo koju boju. Obrub dobija i govor kad mu se izabere
    boja; **Debljina obruba** − / + menja debljinu, a 0 % ga uklanja (i sa onomatopeje);
  - „Automatski" vraća sve na automatsko slaganje, uključujući boju;
- **naglasak** (kao u srpskim izdanjima: podebljano i ukošeno):
  - ceo oblačić (vika, psovka): prekidač **„Naglašeno"** u panelu izabranog bloka;
  - jedna reč ili deo rečenice: označi ga u polju prevoda (ili samo stavi kursor u reč) i klikni **B** uz polje, ili
    pritisni **Ctrl+B** (radi i u izmeni na samoj slici). U prevodu se to vidi kao `*REČ*`; isto dugme ga skida.
    Interpunkcija na kraju ostaje obična („*ORLA*!"). Naglašena reč se rastavlja kao i obična;
  - **automatski iz originala (v1.1):** posle OCR-a aplikacija sama prepoznaje povik (ceo oblačić podebljan i
    ukošen) i uključuje „Naglašeno"; pojedine podebljane reči označi zvezdicama već u italijanskom tekstu
    (`*FERMO!...* LASCIA…`), a prevod ih prenosi na srpske reči. Ako prevod nema iste oznake (npr. došao je iz
    memorije), lektura javlja **„naglasak nije prenet"** — dodaj ga sa Ctrl+B. Naracija se ne naglašava. Cele
    oblačiće prepoznaje ~95 %, a pojedine reči oko polovine, pa ih pri lekturi vredi pogledati. Za broj koji je
    pročitan pre v1.1: `docker compose exec api python -m tools.emphasis_suggest --project N` (spisak), pa isto sa
    `--apply` (dira samo blokove bez lekture; Poništi u editoru ga vraća);
- **naracija ukošena** (kao u srpskim izdanjima): meni **Fontovi** → „Naracija ukošena"; važi za ceo serijal i izvoz;
- tekst na tamnoj podlozi (npr. potpisi na crnoj traci) slaže se belim slovima. Podloga se meri pri čišćenju, pa
  posle promene tipa bloka treba ponovo kliknuti „Očisti stranicu".

**Naslov od slova originala:**
- blok preko naslova priče postavi na tip **Naslov**. Tekst bloka mora biti tačan tekst originala (npr.
  LA VALLE!), jer se slova uparuju sa njim; aplikacija odmah iseče slova i javi ako se broj ne poklapa;
- prevod (npr. DOLINA!) se slaže od slika slova originala. Slova kojih nema u originalu (npr. D, O, N) prave se
  automatski i u traci slova u panelu imaju isprekidan narandžast okvir, a slova sastavljena od delova zelen;
- **šuplja slova** (bela sa konturom, npr. naslov priče preko crteža) se nalaze po beloj unutrašnjosti, i
  napravljena slova dobijaju istu konturu i belu ispunu;
- **kos naslov ili traka** (npr. „TESTO & DISEGNI" na kosoj traci): okvir bloka nacrtaj oko cele trake. Aplikacija
  sama izmeri nagib i kurziv, iseče slova uspravna i složi prevod pod istim uglom i u istom kurzivu;
- u panelu izabranog bloka: klik na slovo u traci, pa „Drugi primerak" (npr. drugo A iz originala) i strelice za
  pomeraj slova; „Popuni širinu" (reč zauzima širinu originala), A−/A+, razmak slova, „Automatski" i „Iseci slova
  ponovo" (posle izmene teksta ili okvira);
- **Font slova** (za slovo kojeg nema u originalu, npr. K, R, Ž): aplikacija ga sama pravi od fonta koji najviše
  liči na original („napravljena slova: …"); u padajućem spisku uz izabrano slovo može se izabrati drugi font —
  ugrađeni (Archivo Black, Roboto Serif, Anton), tvoji fontovi za naslove i tvoj rukopis za dijalog i onomatopeje
  (npr. tvoj font napravljen od rukopisa, za natpise u rukopisu). Slovo tada prelazi na primerak od tog fonta; slovo sastavljeno od
  delova ostaje sačuvano („Drugi primerak"). Za naslov isečen pre v1.1 spisak se pojavi posle „Iseci slova ponovo";
- **Novo slovo od delova…** otvara prozor za slovo kojeg nema u originalu (npr. K), kao u Photoshopu:
  1. levo izaberi slovo originala (npr. R), pa mišem izreži deo: „Pravougaonik" ili „Slobodno" (linija oko
     dela), zatim „Dodaj deo"; „Celo slovo" dodaje celo slovo;
  2. desno delove prevlači, ugaonim ručkama menjaj veličinu, ručkom iznad rotiraj, a „Ogledalo" ih okreće;
     isprekidane linije su osnovna linija i visina slova, a bledo slovo u pozadini je automatski napravljeno slovo;
  3. „Sačuvaj slovo": novo slovo odmah zamenjuje napravljeno (zelen okvir u traci slova). Klik na njega u traci,
     pa „Uredi slovo", otvara isti prozor za izmene ili brisanje;
- slova koja se dodiruju (npr. serifom) aplikacija sama razdvaja; font za napravljena slova bira sama (piše u
  panelu), kao i nagib i šuplja slova. Ako si dodao svoj font za naslove (vrsta „naslov"), i on je kandidat;
- ↺ ↻ rotiraju izabrano slovo (naslov u luku);
- **Neprovidna**: unutrašnjost slova (papir) pokriva crtež iza slova. Za šuplja slova (bela sa crnom konturom,
  npr. onomatopeja preko crteža) uključeno je samo; isključi ga ako crtež treba da se vidi kroz slova. Tip Naslov
  radi i za onomatopeje: od slova originala CLICK složi se KLIK;
- **Očisti** briše originalni naslov sa trake.

**Ostalo:**
- prekidač **Preskoči** znači da se stranica ne obrađuje i ulazi u album neizmenjena (ili se izostavlja, po izboru pri
  izvozu);
- meni **Sačuvaj** (JPG/PNG) preuzima stranicu u punoj rezoluciji, tačno kao u izvozu.

### 2.5 Prečice u editoru

| Taster | Radnja |
|---|---|
| ← / → , PageUp / PageDown | prethodna / sledeća stranica |
| Home / End | prva / poslednja stranica |
| N | režim Blok (novi blok) |
| R | ponovo pročitaj izabrane blokove |
| B | režim Četkica |
| T | režim Tekst (uređivanje složenog prevoda) |
| Delete / Backspace | obriši izabrane blokove |
| P | režim Zakrpe (slika preko stranice) |
| Ctrl+Z | poništi poslednju izmenu na stranici |
| Ctrl+Shift+Z (ili Ctrl+Y) | ponovi poništenu izmenu |
| dvoklik na tekst ili blok | izmena prevoda na samoj slici |
| Ctrl+Enter | snimi tekst (u polju na slici) ili odobri prevod bloka i pređi na sledeći |
| Ctrl+Shift+Enter | odobri celu stranicu i pređi na sledeću |
| Ctrl+B | naglasi (ili vrati u običnu) označenu reč ili reč pod kursorom, u polju prevoda i na slici |
| Esc | zatvori meni → izlaz iz polja za tekst → režim Izbor i poništen izbor → nazad na projekat |
| Shift / Ctrl + klik | izbor više blokova |

Prečice sa slovima ne rade dok je kursor u polju za tekst (tada Esc izlazi iz polja).

### 2.5b Scenario za lektora

Na strani projekta su dugmad **„Scenario"** i **„CSV"**.
- **Scenario** otvara tabelu u browseru: po stranici, za svaki oblačić original i prevod, vrsta bloka, status
  prevoda i napomena (predugačak prevod, OCR za proveru). Naslov strane je link na tu stranu u editoru, a strana
  je spremna i za štampu (Ctrl+P).
- **CSV** daje isto kao tabelu za Excel ili LibreOffice (tačka-zarez kao razdvajač).

Preskočene stranice i blokovi bez teksta se ne izvoze.

### 2.6 Glosar serijala

Otvara se dugmetom „Glosar" na strani projekta.
- Stavka ima italijanski izraz, srpski prevod, vrstu i napomenu. Prevodilac dobija samo stavke koje se javljaju na
  stranici, a lektura upozorava kad prevod ne koristi traženi izraz.
- „Predlozi iz objavljenog prevoda": izaberi italijanski projekat i projekat sa srpskim izdanjem istog broja. Oba
  moraju biti obrađena (pročitan tekst). Model upari blokove i predloži stavke, koje stižu u tab „Predlozi", gde se
  odobravaju ili odbacuju.
- Odobren prevod bloka ulazi u memoriju prevoda: isti italijanski tekst na drugom mestu dobija isti prevod bez
  poziva modela.

### 2.7 Izvoz albuma

Otvara se dugmetom „Izvoz albuma" na strani projekta.
1. **Spremnost** pokazuje stranice koje nisu očišćene, blokove bez prevoda i nelektorisane stranice, sa linkovima.
   To je upozorenje, izvoz je i dalje moguć.
2. **Podešavanja:**
   - format: CBZ (za čitače stripova), PDF ili ZIP sa slikama;
   - slike JPG (kvalitet 92) ili PNG;
   - preskočene stranice: uključi neizmenjene ili izostavi;
   - opseg stranica „od–do".
3. **Izvezi album:** browser crta stranicu po stranicu (vidi se napredak, može se prekinuti), pa server pakuje album.
   Na kraju se javljaju stranice na kojima tekst ne staje.
4. Gotovi albumi su u spisku ispod, sa dugmetom „Preuzmi" i brisanjem ✕.

Tab sa izvozom mora ostati otvoren dok crtanje traje; 100 stranica traje oko pola minuta. Napredak se vidi i van
tog taba: na strani **Status** (Poslovi: „Crtanje albuma: 34 / 96", pa „Pakovanje albuma") i na strani projekta u
koraku 8. Ako tab zatvoriš usred crtanja, piše „čeka otvoren tab za izvoz"; nedovršen izvoz se posle sat vremena
više ne prikazuje. Na strani za izvoz traka prati i pakovanje.

### 2.7b Praćenje poslova

Strana **Status** (gore u meniju) ima odeljak **Poslovi**: posao koji trenutno radi (projekat, traka, „Prekini") i
spisak poslova koji čekaju, redom kojim dolaze na red. Posle minut rada pojavljuje se procena: koliko je ostalo
tekućem poslu i otprilike do kraja reda (poslovi iste vrste se računaju kao jednako dugi). Vidi se svaki posao iz
reda — uvoz, obrada i OCR, prevod, čišćenje, priprema albuma, predlozi glosara, pakovanje izvoza — ali ne i čitanje
jednog bloka (R) ni crtanje strana pri izvozu, jer oni ne idu kroz red.

### 2.8 Saveti

- Pre pripreme albuma obeleži naslovnu, reklame i uvodnik kao preskočene. Tako se ne troši OCR i prevod.
- Onomatopeje koje detektor promaši nacrtaj ručno (N) i izaberi tip Onomatopeja.
- Natpise na tablama postavi na tip Ostalo, a naslov priče na tip Naslov. Ako su na tamnoj traci, ponovo očisti
  stranicu.
- Za teksturisane table (npr. SALOON) posle čišćenja upotrebi četkicu „obriši preko crteža".
- Ako tekst „ne staje" iako oblačić izgleda dovoljno veliki, oblik oblačića je verovatno promašeno izmeren.
  Na strani projekta, u koraku 7, klikni **„Ponovo izmeri oblačiće"** — oblik se osvežava iz očišćenih
  strana, bez ponovnog čišćenja, i vraća se sa „Poništi" u editoru. Za jedan oblačić je dovoljan i potez
  četkicom u njemu (oblik se tada meri ponovo).
- Stanje OpenRouter kredita proveri na https://openrouter.ai/credits.
- Fontovi koje napraviš od skenova tuđih izdanja služe samo za ličnu upotrebu.

---

## Dodatak — javna verzija (za autora)

Javna verzija je čista kopija `main`-a bez zaštićenog sadržaja, u folderu `~/claude/striptrans-public` sa svojom
istorijom:

```bash
make notice
```

osveži `public/NOTICE.md` (licence paketa; staje ako se pojavi GPL/AGPL paket), pa se commit-uje u privatnom repou.

```bash
make public-release
```

napravi ili osveži javnu kopiju i proveri je (ključevi, e-pošta, lične putanje, tekst stripa). Slanje na GitHub je
ručno, posle pregleda: `git -C ~/claude/striptrans-public push`.

