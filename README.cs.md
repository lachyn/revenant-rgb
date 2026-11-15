# revenant

**Čeština** · [English](https://github.com/lachyn/revenant-rgb/blob/main/README.md)

Neoficiální multiplatformní ovladač pro herní klávesnici **CZC.Gaming Revenant**
(čip SONiX, USB `0C45:8006`). Nahrazuje originální software CZC, který existuje jen pro Windows
a umí méně – tohle běží na **Windows, Linuxu i macOS**.

- **Podsvícení** – 19 hardwarových efektů (barva/duha, jas, rychlost, směr) a vlastní barva pro každou ze 104 kláves
- **Funkce kláves** – přeřazení na jinou klávesu, kombinaci, multimediální funkci, tlačítko myši, makro nebo zakázání
- **Makra** – psaní textu, kombinace, pauzy, kliknutí myší; přehrát jednou / N× / zapnout-vypnout
- **Herní mód** – blokování Alt+Tab, Alt+F4 a klávesy Windows
- **Profily** – pojmenovaná kompletní nastavení, přepínání jedním příkazem, automatické přepínání podle spuštěné hry
- **TUI** (textové rozhraní s myší), **webové rozhraní** v prohlížeči i **příkazová řádka** – vše nad stejným aktuálním nastavením
- **Česky i anglicky** – jazyk se vybere podle systému, přepnout jde kdykoliv
- **Ukázkové profily** – monokai, nord, ocean, synthwave, sunset, rozložení pro FPS hry a další, nainstalují se při prvním spuštění

Všechno se ukládá přímo do klávesnice, takže nastavení funguje i bez běžícího programu a na jiném počítači.

> **Klávesnice musí být připojená USB kabelem** a přepínač režimu na její spodní straně musí být v poloze **Off**
> (drátový režim). Přes 2,4GHz přijímač ani Bluetooth se nastavovat nedá – nejde to ani originálním softwarem CZC.
> Jednou nastavené chování pak funguje ve všech režimech.

### Proč to vzniklo

Ke klávesnici se dodává jen originální program CZC – uzavřená aplikace **jen pro Windows**, která navíc chce
práva správce. Žádná verze pro Linux ani macOS, žádné API, SDK ani dokumentace protokolu, žádná příkazová řádka,
nic, co by šlo skriptovat nebo do čeho by šlo přidat funkci. Profil se přepíná jen klikáním v jejím okně.

Komunikace s klávesnicí se proto **odposlechla**: originální program se spustil pod nástrojem
[Frida](https://frida.re), který zaznamenal každý paket, jež program posílá do klávesnice. Program se přitom
ovládal automaticky (klikání a snímky obrazovky), takže ke každému kliknutí byla známá data, která odešla.
Z toho se poskládal celý protokol – podsvícení, funkce kláves, makra i herní mód – a tento ovladač ho
reprodukuje bajt po bajtu. Nic se nedekompilovalo ani nekopírovalo z kódu CZC; sledovala se jen data mezi
programem a klávesnicí, za účelem interoperability. Podrobnosti v sekcích [Protokol](#protokol)
a [Jak byl protokol zjištěn](#jak-byl-protokol-zjištěn).

---

## Obsah
- [Požadavky](#požadavky)
- [Instalace](#instalace)
- [Rychlý start](#rychlý-start)
- [TUI](#tui)
- [Webové rozhraní](#webové-rozhraní)
- [Příkazová řádka](#příkazová-řádka)
- [Jazyk](#jazyk)
- [Profily](#profily)
- [Automatické přepínání profilů](#automatické-přepínání-profilů)
- [Použití jako knihovna](#použití-jako-knihovna)
- [Řešení problémů](#řešení-problémů)
- [Co je ověřené](#co-je-ověřené)
- [Protokol](#protokol)
- [Jak byl protokol zjištěn](#jak-byl-protokol-zjištěn)
- [Struktura projektu](#struktura-projektu)

---

## Požadavky

- Python **3.9+**
- klávesnice připojená **USB kabelem** – pravý přepínač na spodní straně v poloze **Off**.
  Přes 2,4 GHz ani Bluetooth se klávesnice konfigurovat nedá (stejně jako originálním softwarem).
- knihovny `hidapi`, `textual` (TUI) a `psutil` (automatické přepínání profilů) – nainstalují se samy, viz níže

## Instalace

Nejjednodušší je přes [uv](https://docs.astral.sh/uv/) (v případě potřeby stáhne i Python):

```
uv tool install revenant-rgb      # pak funguje příkaz `revenant` odkudkoliv
revenant                          # textové rozhraní
revenant web                      # webové rozhraní
uv tool upgrade revenant-rgb      # aktualizace
```

nebo `uvx revenant-rgb` pro spuštění bez instalace, případně `pip install revenant-rgb`.
Pak se řiď poznámkami k systému níže (Linux: jednou `revenant setup`).

### Ze zdrojových kódů

Program je `revenant.py` (příkazová řádka, TUI i server webového rozhraní) plus složka `revenant_web/` se stránkou. Stačí Python, nic se ručně instalovat nemusí:

```
git clone https://github.com/lachyn/revenant-rgb.git revenant
cd revenant
python revenant.py            # Windows (nebo: py revenant.py)
python3 revenant.py           # Linux / macOS (nebo: ./revenant.py)
```

Při prvním spuštění si program sám vytvoří vlastní prostředí a nainstaluje do něj knihovny
(`hidapi`, `textual`, `psutil`) – trvá to pár sekund a jen poprvé. Prostředí leží v:

| Systém | Umístění |
|---|---|
| Linux | `~/.cache/revenant/venv` |
| macOS | `~/Library/Caches/revenant/venv` |
| Windows | `%LOCALAPPDATA%\revenant\venv` |

Smazáním složky se vše odinstaluje. Kdo má radši vlastní správu balíčků:

- **uv**: `uv run revenant.py …` – závislosti jsou zapsané přímo v hlavičce souboru (PEP 723)
- **pip**: `pip install -r requirements.txt` a automatickou instalaci vypnout `REVENANT_NO_BOOTSTRAP=1`

### Bez klonování: přes `uv`

S [uv](https://docs.astral.sh/uv/) se nemusí klonovat ani instalovat Python (uv si ho případně stáhne sám):

```
# jednorázové spuštění (stáhne se do cache uv, příště se spouští rovnou)
uvx --from git+https://github.com/lachyn/revenant-rgb revenant-rgb

# trvalá instalace - pak funguje příkaz `revenant` odkudkoliv
uv tool install git+https://github.com/lachyn/revenant-rgb
revenant static red
revenant                     # TUI

uv tool upgrade revenant-rgb      # aktualizace na nejnovější vydání
uv tool uninstall revenant-rgb    # odinstalace
```

Konkrétní verzi jde zvolit přidáním `@<tag>` za adresu repozitáře, např. `…/revenant-rgb@v0.1.0`.
Nainstalovanou verzi ukáže `revenant --version`.

Debian/Ubuntu: pokud automatická instalace selže, chybí balíček `python3-venv` (`sudo apt install python3-venv`).

### Windows
Nic dalšího není potřeba, funguje to i bez práv správce. Pokud běží originální software CZC, zavři ho
(oba programy by si mohly přepisovat nastavení).

### Linux
Aby šlo klávesnici ovládat bez `sudo`, je potřeba jednou nainstalovat udev pravidlo. Udělá to:
```
python3 revenant.py setup
```
Zeptá se na heslo správce (v terminálu přes `sudo`, jinak grafickým oknem přes `pkexec`), nainstaluje
`/etc/udev/rules.d/70-czc-revenant.rules` a ověří, že klávesnice jde otevřít. Pravidlo dá přístup jen přihlášenému
uživateli a jen k zařízení `0C45:8006`. Když pravidlo chybí, TUI i webové rozhraní to poznají a nastavení samy
nabídnou (v TUI dialog nebo klávesa `F2`, ve webu tlačítko *Nastavit přístup* – heslo se zadává v systémovém okně
přes `pkexec`, webová stránka ho nevidí). Ručně to samé:
```
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0c45", ATTRS{idProduct}=="8006", MODE="0660", TAG+="uaccess"' \
  | sudo tee /etc/udev/rules.d/70-czc-revenant.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
Na Linuxu se klávesnice ovládá přes `/dev/hidraw*`, takže během ovládání normálně píše dál.

### macOS
Instalace není potřeba. Při prvním použití může systém chtít povolit **Sledování vstupu** (Input Monitoring)
pro Terminál nebo aplikaci, ze které revenant spouštíš: *Nastavení systému → Soukromí a zabezpečení → Sledování vstupu*.
`python3 revenant.py setup --open` to nastavení otevře a ověří přístup ke klávesnici.

### Volitelně: příkaz `revenant` odkudkoliv
Nejjednodušší je `uv tool install` (viz výše). Bez uv:

PowerShell (`notepad $PROFILE`):
```powershell
function revenant { python C:\cesta\k\revenant\revenant.py @args }
```
bash / zsh (`~/.bashrc`, `~/.zshrc`):
```bash
alias revenant='python3 /cesta/k/revenant/revenant.py'
```
Na Linuxu/macOS stačí i odkaz: `ln -s "$PWD/revenant.py" ~/.local/bin/revenant`.

## Rychlý start

```
python revenant.py static red                      # celá klávesnice červeně
python revenant.py keys wasd=red --base 101010     # WASD červeně, zbytek tlumeně
python revenant.py remap caps=disable              # vypnout Caps Lock
python revenant.py status                          # co je nastavené
python revenant.py                                 # bez příkazu = grafické ovládání v terminálu (TUI)
```

---

## TUI

```
python revenant.py          # nebo: python revenant.py tui
```

Ovládá se myší i klávesnicí. Každá změna jde hned do klávesnice; profil se změní, až když ho uložíš (`Ctrl+S`
nebo *Uložit* na záložce Profily). Dokud jsou změny neuložené, ukazuje titulek `• neuloženo`.

| Záložka | Co umí |
|---|---|
| **Barvy kláves** | klikací klávesnice vybarvená podle aktuálního nastavení. Klikni na klávesy (nebo na skupinu `all`, `letters`, `numbers`, `fkeys`, `wasd`, `arrows`, `numpad`, `nav`, `mods`) a pak na barvu v paletě nebo zadej `#RRGGBB`. Kapátko převezme barvu z klávesy, jas 0–16. |
| **Efekty** | výběr z 19 efektů, barva nebo duha, jas, rychlost, směr → *Spustit efekt* |
| **Funkce kláves** | klávesa + typ funkce (výchozí, zakázáno, jiná klávesa, kombinace, multimédia, myš, makro) + parametr → *Přiřadit*. Tabulka ukazuje všechna přeřazení; kliknutím na řádek ho načteš k úpravě. |
| **Makra** | seznam maker a editor kroků (jeden krok na řádek, nápověda pod editorem) |
| **Herní mód** | vypínač + co blokovat (Alt+Tab, Alt+F4, Win) |
| **Profily** | seznam profilů s popisem, *Uložit*, *Zahodit změny*, *Uložit jako nový*, *Načíst vybraný*, *Nový prázdný*, *Smazat* |

| Zkratka | Akce |
|---|---|
| `F5` | nahrát aktuální nastavení znovu do klávesnice |
| `Ctrl+S` | uložit aktuální nastavení do aktivního profilu |
| `Ctrl+R` | načíst aktuální nastavení znovu ze souboru (po změně z příkazové řádky) |
| `Ctrl+A` / `Esc` | vybrat všechny klávesy / zrušit výběr |
| `F2` | nastavit přístup ke klávesnici (Linux: udev pravidlo, macOS: Sledování vstupu) |
| `Ctrl+L` | vybrat jazyk (podle systému / English / Čeština) |
| `Ctrl+Q` | konec |

TUI potřebuje terminál s 24bitovými barvami: Windows Terminal, většina terminálů na Linuxu a macOS
(iTerm2, Terminal.app, GNOME Terminal, Konsole, kitty…). Staré okno `cmd.exe` (conhost) barvy nezobrazí.

## Webové rozhraní

```
python revenant.py web                 # otevře prohlížeč na http://127.0.0.1:8462/
python revenant.py web --port 9000     # jiný port
python revenant.py web --no-browser    # jen spustit server (adresa se vypíše)
```

Vlevo jsou **profily**: aktivní profil se stavem (uloženo / neuložené změny) a tlačítky *Uložit* / *Zahodit změny*,
seznam (kliknutím profil načteš), *Uložit jako nový* a *Nový prázdný*. Vpravo jsou **úpravy** aktuálního nastavení:
*Podsvícení* (vlastní barvy nebo hardwarový efekt), *Funkce kláves* (klávesu vybereš kliknutím na klávesnici),
*Makra* a *Herní mód*. Funguje ve světlém i tmavém režimu i na úzké obrazovce. Konec: `Ctrl+C` v terminálu.

- Výchozí port **8462** – na běžném Windows, macOS i Linuxu volný (nekoliduje s AirPlay na 5000/7000 ani s vývojovými
  servery na 8000/8080). Když je obsazený nebo ho Windows rezervují (Hyper-V/WSL), vezme se automaticky jiný volný port.
- Server poslouchá **jen na 127.0.0.1** – z jiných počítačů není dostupný a firewall Windows ani macOS se neptá.
  Požadavky z cizích webových stránek odmítá (kontrola hlavičky `Host` a vlastní hlavičky `X-Revenant`).
- Stav klávesnice ukazuje vpravo nahoře (připojena / nenalezena / bez přístupu) a každé 4 s ho ověřuje – jen
  zjišťuje, jestli je připojená, nic do ní nezapisuje. Odpojení a připojení kabelu pozná sám.
- Když je klávesnice připojená, ale chybí přístup, ukáže lištu s tlačítkem *Nastavit přístup*.
- Změny jdou hned do klávesnice; při neuložených změnách ukazuje horní lišta `• neuloženo` a tlačítka *Uložit*
  (do aktivního profilu) a *Zahodit změny*. *Zhasnout vše* se ptá na potvrzení.

Frontend je ve složce `revenant_web/` – čisté HTML, CSS a JavaScript bez sestavování. `app.js` má typy v JSDoc
a dá se zkontrolovat TypeScriptem: `npx -p typescript tsc -p revenant_web`.

---

## Příkazová řádka

```
python revenant.py [-v] [-p PROFIL] <příkaz> …
```

Bez příkazu se spustí TUI.

Každý příkaz, který něco mění, změní **aktuální nastavení** a pošle ho do klávesnice; do profilu ho uložíš příkazem
`profile save` (viz [Profily](#profily)).

| Globální volba | Význam |
|---|---|
| `-p PROFIL` | upravit uložený profil místo aktuálního nastavení – klávesnice se nemění |
| `-v` | podrobný výpis (otevřené zařízení, kontrolní součty) |

### Přehled a nápověda
| Příkaz | Co dělá |
|---|---|
| `status` | shrnutí aktivního profilu (s `-p` jiného) |
| `--help`, `<příkaz> --help` | nápověda |
| `funcs` | zápis funkcí kláves a kroků maker |
| `keylist` | názvy všech kláves a skupin |
| `list` | názvy efektů |
| `apply` | znovu poslat aktuální nastavení do klávesnice |
| `setup` | jednorázové nastavení systému (Linux: udev pravidlo) a test přístupu ke klávesnici |
| `web` | webové rozhraní, viz výše |
| `lang [cs\|en\|auto]` | ukázat nebo nastavit jazyk |

### Podsvícení
```
python revenant.py static COLOR [-b JAS]
python revenant.py effect EFEKT [-c BARVA] [-b JAS] [-s RYCHLOST] [-d SMĚR]
python revenant.py keys KLÁVESA=BARVA … [--base BARVA] [-b JAS] [--clear]
python revenant.py off
```

- **Barva**: `RRGGBB` (`ff8800`, `#ff8800`) nebo název – `red green blue white yellow cyan magenta orange purple pink off`,
  česky `cervena zelena modra bila zluta fialova oranzova ruzova`.
- **Jas** a **rychlost**: 0–16.
- **Směr**: `right` / `left` / `up` / `down` (česky `doprava doleva nahoru dolu`).
- `effect` bez `-c` jede duhově.
- `keys` přidává k aktuálním barvám, `--clear` nejdřív všechno zhasne, `--base` je barva kláves, které nemají vlastní.
  Místo klávesy lze napsat skupinu: `all letters numbers fkeys wasd arrows numpad nav mods`.

Efekty: `static press-on press-off sparkle rain colors breathing spectrum center-wave vertical-wave
horizontal-wave rotating explosion start ripple snake pulse disco lines`

```
python revenant.py static red
python revenant.py effect breathing -c blue -s 6
python revenant.py effect horizontal-wave -d left -s 16
python revenant.py keys --clear letters=0000ff wasd=red arrows=green fkeys=yellow esc=white numpad=purple --base 101010
```

### Funkce kláves
```
python revenant.py remap KLÁVESA=FUNKCE …     # nastavit
python revenant.py remap KLÁVESA=default      # vrátit jednu klávesu
python revenant.py remap                      # vypsat
python revenant.py remap --clear              # všechno na výchozí
```

| Funkce | Význam |
|---|---|
| `default` | výchozí funkce klávesy |
| `disable` | klávesa nedělá nic |
| `key:esc` (nebo jen `esc`) | chová se jako jiná klávesa (`a`–`z`, `0`–`9`, `f1`–`f24`, `enter`, `space`, `lctrl`, `win`, `num5`… viz `keylist`) |
| `combo:ctrl+shift+esc` | kombinace až 3 kláves |
| `media:NÁZEV` | `volup voldown mute play next prev stop mail calc mycomputer browser` |
| `mouse:NÁZEV` | `left right middle back forward wheelup wheeldown` |
| `macro:JMÉNO` | spustí makro jednou |
| `macro:JMÉNO:repeat:N` | spustí makro N× (1–255) |
| `macro:JMÉNO:toggle` | stisk spustí opakování, další stisk zastaví |

```
python revenant.py remap caps=disable f12=media:volup f11=media:voldown
python revenant.py remap pause=combo:ctrl+shift+esc menu=mouse:middle
```

### Makra
```
python revenant.py macro set JMÉNO KROK KROK …
python revenant.py macro list | show JMÉNO | delete JMÉNO
```

| Krok | Význam |
|---|---|
| `a`, `enter`, `f5`, `esc` … | stisk a puštění klávesy |
| `text:Ahoj svete!` | napíše text (velká písmena a `!@#$%^&*()_+{}|:"<>?~` přes Shift) |
| `combo:ctrl+c` | kombinace kláves |
| `down:shift` / `up:shift` | jen stisk / jen puštění |
| `100ms` (nebo `delay:100`) | pauza |
| `mouse:left` | kliknutí myší; `mdown:left` / `mup:left` jen stisk / puštění |

Mezi kroky se automaticky vkládá pauza 10 ms. Makro přiřadíš klávese přes `remap`:

```
python revenant.py macro set pozdrav "text:Ahoj svete!" enter
python revenant.py macro set kopiruj combo:ctrl+c 50ms combo:alt+tab 100ms combo:ctrl+v
python revenant.py remap f1=macro:pozdrav f2=macro:kopiruj
```

Makro přiřazené klávese nejde smazat – nejdřív klávese změň funkci. Klávesnice pojme až 100 maker.

> Text se píše jako stisky kláves podle **anglického (US) rozložení**. Při českém rozložení vyjde
> např. `y`↔`z` prohozené a číslice jako `+ěščřžýáí`. Pro diakritiku makra nejsou vhodná.

### Herní mód
```
python revenant.py gamemode on [--alt-tab] [--alt-f4] [--win]
python revenant.py gamemode off
```

### Profily
```
python revenant.py profile list                 # * = aktivní
python revenant.py profile show [NÁZEV]
python revenant.py profile use NÁZEV            # načíst do aktuálního nastavení a poslat do klávesnice
python revenant.py profile save [NÁZEV]         # uložit aktuální nastavení (do aktivního profilu, nebo jako NÁZEV)
python revenant.py profile discard              # zahodit neuložené změny, zpět na uložený aktivní profil
python revenant.py profile new NÁZEV            # prázdný profil
python revenant.py profile copy ZDROJ NOVÝ
python revenant.py profile delete NÁZEV         # aktivní smazat nejde
python revenant.py profile path                 # kde jsou soubory
python revenant.py profile presets              # doplnit chybějící ukázkové profily
```

## Jazyk

Program umí **česky a anglicky**. Výchozí je jazyk systému (český a slovenský systém dostane češtinu, ostatní
angličtinu). Nastavit napevno:

```
python revenant.py lang cs        # cs | en | auto – uloží se, platí pro příkazovou řádku, TUI i web
python revenant.py --lang en …    # jen pro toto spuštění
```

Dál jde použít `REVENANT_LANG=cs`, v TUI `Ctrl+L` a ve webu nabídku jazyka vpravo nahoře.

**Překlady** jsou v `revenant_i18n/<jazyk>.json` ve tvaru `{"anglický text": "překlad"}` – zdrojové texty v kódu jsou
anglicky (`tr("…")` v Pythonu, `t("…")` ve webu, `data-i18n` v HTML). Po změně textu spusť
`python tools/i18n_check.py`: vypíše chybějící a nepoužité překlady a nesouhlasící `{zástupné hodnoty}`
(`--add` chybějící doplní s označením `TODO`). Nový jazyk = nový `xx.json` a položka v `LANGUAGES` v `revenant.py`.

---

## Profily

Profil je kompletní nastavení klávesnice uložené pod jménem: podsvícení, funkce kláves, makra a herní mód.

- **Aktuální nastavení** je to, co je právě v klávesnici. Upravuje ho TUI, webové rozhraní i příkazová řádka a každá
  změna se hned pošle do klávesnice – takže vidíš, co děláš.
- **Aktivní profil** je ten, ze kterého aktuální nastavení vzniklo. Mění se **jen když uložíš**: `Ctrl+S` v TUI,
  *Uložit* ve webu, `revenant profile save`. *Uložit jako nový* / `profile save NÁZEV` ho uloží pod novým jménem.
  Do té doby web i TUI ukazují `• neuloženo` a *Zahodit změny* / `profile discard` vrátí uložený profil – zkoušením
  tedy profil nezkazíš.
- Kliknutí na profil (web), *Načíst vybraný* (TUI) nebo `profile use NÁZEV` načte profil do aktuálního nastavení (neuložené změny se zahodí).
- První spuštění nainstaluje ukázkové profily níže a začne profilem `default`.

Umístění: `~/.config/revenant/` (Windows: `C:\Users\<jméno>\.config\revenant\`), jinde přes proměnnou `REVENANT_HOME`.

### Ukázkové profily
Při prvním spuštění se nakopírují do složky profilů (`python revenant.py profile presets` později doplní chybějící,
tvoje profily nepřepíše):

| Profil | Co to je |
|---|---|
| `default` | klidná statická tyrkysová |
| `monokai` | paleta Monokai v tlumených tónech – písmena, čísla, F-klávesy, modifikátory a numerická klávesnice každé svou barvou |
| `monokai-vivid` | totéž v plném jasu |
| `nord` | paleta Nord – sněhová písmena, ledově modré modifikátory, F-klávesy, šipky a numerika v barvách polární záře |
| `ocean` | od hluboké modré k tyrkysové, zleva doprava |
| `synthwave` | růžová → fialová → tyrkysová, shora dolů |
| `sunset` | oranžová a jantarová s modrými akcenty |
| `fps` | tmavá klávesnice se zvýrazněným WASD, akčními klávesami, čísly zbraní a modifikátory; herní mód blokuje klávesu Windows |
| `cs16` | Counter-Strike 1.6 – klávesy obarvené podle výchozích bindů (pohyb, nákup, granáty, rádio…) |
| `rainbow-wave` | hardwarová duhová vlna |
| `breathing` | hardwarové dýchání ve fialové |

Animované běží přímo v klávesnici, takže za běhu nic nestojí a nic nezapisují.

```
~/.config/revenant/
├── active                 # název aktivního profilu
├── current.json           # aktuální nastavení (to, co je v klávesnici)
├── auto.json              # pravidla automatického přepínání
└── profiles/
    ├── default.json
    └── hry.json
```

Profil je čitelný JSON, dá se upravovat i ručně (pak `python revenant.py profile use NÁZEV`):

```json
{
  "lighting": {
    "mode": "keys",
    "effect": "static", "color": "00aaff", "rainbow": false,
    "brightness": 16, "speed": 10, "direction": "right",
    "keys": { "w": "ff0000", "a": "ff0000", "s": "ff0000", "d": "ff0000" },
    "base": "101010", "key_brightness": 16
  },
  "remap": {
    "caps": "disable",
    "f1": "macro:pozdrav",
    "f12": "media:volup"
  },
  "macros": {
    "pozdrav": ["text:Ahoj svete!", "enter"]
  },
  "gamemode": { "enabled": true, "alt_tab": false, "alt_f4": false, "win": true }
}
```

- `lighting.mode`: `"effect"` použije `effect/color/rainbow/brightness/speed/direction`,
  `"keys"` použije barvy kláves `keys` + `base` + `key_brightness`. Obě sady se pamatují, takže přepnutí neztratí nastavení.
- `remap` a `macros` používají stejné zápisy jako příkazová řádka.

Profily se mezi počítači nesynchronizují – pro použití jinde zkopíruj složku `profiles/`.

## Automatické přepínání profilů

```
python revenant.py auto [--interval 2]
```

Při prvním spuštění vytvoří vzorový `~/.config/revenant/auto.json`:

```json
{
  "default": "prace",
  "rules": [
    { "process": "cs2.exe",   "profile": "hry" },
    { "process": "notepad.exe", "profile": "psani" }
  ]
}
```

Každé 2 s zkontroluje běžící procesy: první pravidlo, jehož program běží, určuje profil, jinak se použije `default`.
Přepnutí načte profil do aktuálního nastavení, takže neuložené změny se zahodí.
Soubor se čte pokaždé znovu, takže ho jde měnit za běhu. Na Linuxu/macOS jsou názvy procesů bez `.exe`.
Odpojení klávesnice program nezastaví – po připojení pokračuje.

Spuštění po přihlášení: Windows – zástupce `pythonw revenant.py auto` ve složce `shell:startup`;
Linux – systemd user service; macOS – LaunchAgent.

## Použití jako knihovna

```python
import revenant as rv

kb = rv.Revenant()
kb.set_effect("breathing", (0, 0, 255), rainbow=0, speed=8)
kb.set_keys({"wasd": (255, 0, 0), "esc": (255, 255, 255)}, base=(16, 16, 16))

kb.write_macros([rv.compile_macro(["text:Ahoj!", "enter"])])                  # makro č. 0
kb.write_keymap({rv.KEYS["f1"]: rv.encode_action("macro:x", {"x": 0}),
                 rv.KEYS["caps"]: rv.encode_action("disable")})
kb.set_gamemode(True, win=True)

prof = rv.load_profile("hry")
rv.apply_profile(kb, prof)
```

`rv.Revenant()` vyhodí `rv.RevenantNotFound`, když klávesnice není připojená, a `rv.RevenantAccessError`, když je
připojená, ale nejde otevřít (obě jsou podtřídy `rv.RevenantError`).

---

## Řešení problémů

| Problém | Řešení |
|---|---|
| *Klávesnice nenalezena* | připoj USB kabelem, pravý přepínač vespod na **Off** (přes 2,4 GHz / Bluetooth to nejde) |
| *Nepodařilo se otevřít ovládací rozhraní* | Linux: `revenant setup`. macOS: povol Sledování vstupu. Windows: zavři originální software CZC. |
| *kontrolní součet nesedí* | data dorazila poškozená – zopakuj příkaz; pomáhá jiný USB port / bez hubu |
| TUI je černobílé | terminál bez 24bitových barev – použij Windows Terminal; zkontroluj, že nemáš nastavené `NO_COLOR` |
| Makro píše jiné znaky | makra píšou podle US rozložení (viz poznámka u maker) |
| Klávesnice se chová divně | tovární nastavení: podrž **Fn+Esc** 3 s, pak `python revenant.py apply` |

Užitečné zkratky přímo na klávesnici (podle manuálu CZC): Fn+Scroll módy podsvícení (ovládá i boční hranu),
Fn+Pause barva, Fn+↑/↓ jas, Fn+←/→ rychlost, Fn+PrtSc vlastní podsvícení, Fn+Win zámek klávesy Windows,
Fn+A / Fn+S režim Windows / Mac, Fn+Esc (3 s) tovární nastavení.

### Opotřebení paměti klávesnice

**Každý zápis do klávesnice se ukládá trvale** – i bez závěrečného příkazu `04 f0` nastavení přežije odpojení
kabelu. Klávesnice tedy při každé změně barvy, efektu, funkce kláves nebo profilu přepisuje svou flash paměť,
která snese jen omezený počet přepisů (u podobných čipů typicky desítky tisíc).

- Běžné používání (změna barvy, přepnutí profilu, úprava v TUI) je v pořádku – jde o jednotky zápisů.
- **Ovladač není vhodný na animace, hry ani rychle se měnící efekty** řízené z počítače (např. vizualizace hudby,
  had na klávesnici) – při ~6 snímcích za sekundu by šlo o tisíce zápisů za pár minut.
- Animace použij vestavěné – efekty běží přímo v klávesnici a nic nezapisují (`effect snake`, `effect ripple`…).
- `auto` zapisuje jen při změně profilu, ne při každé kontrole.

**Boční světelnou hranu z počítače ovládat nejde** – nereaguje na žádná data, která posílá ovladač ani originální
software; přepíná ji jen Fn+Scroll přímo na klávesnici.

## Co je ověřené

Ověřeno na skutečné klávesnici:
- statická barva, jas, efekt dýchání, horizontální vlna oběma směry
- barvy jednotlivých kláves – mapa všech 104 kláves
- makro s textem, multimédia (hlasitost), zakázání klávesy, herní mód (blokování Win)

Odpovídá datům zachyceným z originálního softwaru, ale na klávesnici zvlášť nezkoušené:
ostatní efekty, směr nahoru/dolů, funkce myši, `wheeldown`, makro v režimu `toggle`, pořadí kláves v `combo`.
Tabulky funkcí kláves a maker generované ovladačem jsou bajt po bajtu shodné s originálním softwarem.

Vyvíjeno na Windows a Linuxu: na Linuxu je ověřený přístup přes `/dev/hidraw*`, `revenant setup` i odeslání celého
profilu do klávesnice (každý zápis klávesnice potvrdila kontrolním součtem). Na macOS se skutečnou klávesnicí zatím
nikdo nezkoušel (používá multiplatformní `hidapi`). Automatické testy (protokol, profily, příkazová řádka, webové API,
TUI, překlady) běží na Linuxu, Windows i macOS.

---

## Protokol

Veškerá komunikace probíhá přes 64bajtové HID **feature reporty** (report ID 0) na **rozhraní 0** (klávesnicové).
Každý zápis má stejný průběh:

```
04 ab                      začátek relace          → potvrzení
<64 B náhodných dat>
04 02                      dotaz                    → potvrzení
04 <op> 00 00 00 00 00 [n] začátek zápisu n paketů → potvrzení
<n × 64 B dat>
04 02                      dotaz → odpověď 04 02 00 01 [součet lo] [součet hi] = 16bit součet všech bajtů dat
04 f0                      uložit (jen u podsvícení)
```

Po každém příkazu `04 xx` se čte feature report; klávesnice potvrdí bajtem 4 = `01`.

Ověřeno: data se uloží trvale i bez `04 f0` (nastavení přežije odpojení) – viz [opotřebení paměti](#opotřebení-paměti-klávesnice).

| op | Obsah | Paketů |
|---|---|---|
| `13` | **podsvícení** – 20 záznamů efektů (5 paketů), 3 rezervní, barvy kláves 144 × `80 R G B` (9), aktivní efekt (1) | 18 |
| `11` | **funkce kláves** – 160 × 4 B, index = LED index klávesy, posledních 2 B `aa 55` | 10 |
| `15` | **makra** – 100 × u32 LE offset, pak bloky `[počet u16][6 B 00][události u32 …]`, posledních 2 B `aa 55` | ⌈délka/64⌉ + 1 |
| `17` | **herní mód** – `0a [zapnuto] [Alt+Tab] [Alt+F4] [Win] … aa 55` | 1 |

**Index klávesy** = řádek × 18 + sloupec v matici 8 × 18 (rozložení v `revenant.py`, `KEYS`).

**Záznam efektu** (16 B):
```
[id] [R] [G] [B] 00 00 00 00 [duha 0/1] [jas 0-16] [rychlost 0-16] [směr 0-3] 00 00 aa 55
```
id: `01` statické … `13` řádkování, `80` vlastní barvy kláves. Směr: 0 doprava, 1 doleva, 2 nahoru, 3 dolů.

**Funkce klávesy** (4 B):

| Bajty | Funkce |
|---|---|
| `00 00 00 00` | výchozí |
| `01 01 [maska]` | tlačítko myši (1 levé, 2 pravé, 4 prostřední, 8 zpět, 16 vpřed) |
| `01 03 [01/ff]` | kolečko nahoru / dolů |
| `02 00 [kód]` | klávesa (HID usage) |
| `03 [lo] [hi]` | multimédia (HID consumer usage, např. `ea 00` = hlasitost −) |
| `05 03` | zakázáno |
| `06 [makro] [režim] [počet]` | makro; režim 0 jednou, 1 N×, 2 přepínání |
| `07 [k1] [k2] [k3]` | kombinace kláves |

**Událost makra** (u32 LE) = `typ << 24 | kód << 16 | hodnota`:
typ `30` klávesa, `10` myš (kód = maska tlačítka), `50` pauza (hodnota = ms, 24 bitů); `| 80` = stisk, bez něj puštění.

## Jak byl protokol zjištěn

1. Originální software CZC (V1.00.238n) komunikuje přes `SonixHidDll.dll` → `HidD_SetFeature` / `HidD_GetFeature`.
2. [`research/sniff.py`](https://github.com/lachyn/revenant-rgb/blob/main/research/sniff.py) se pomocí [Frida](https://frida.re) připojí k běžícímu programu
   CZC a zapisuje každý feature report (program běží jako správce, takže i sniffer musí).
3. Program CZC se ovládal automaticky ([`research/`](https://github.com/lachyn/revenant-rgb/tree/main/research) – snímky obrazovky a klikání) a ke každé
   akci se zaznamenal čas; změny v datech se pak spárovaly s akcemi.
4. Kontrolní součet v odpovědi na `04 02` potvrdil, že klávesnice data přijala.
5. Hypotézy (mapa kláves, směry, efekty) se ověřily na klávesnici.

Zachycené vzorky jsou v `research/` (`capture_*.bin`, `capture_static_b4.txt`) a ovladač je umí bajt po bajtu reprodukovat.

## Vývoj

```
uv run --group dev pytest          # testy (klávesnice není potřeba – použije se náhradní)
python tools/i18n_check.py         # jsou překlady kompletní?
npx -p typescript tsc -p revenant_web   # kontrola typů webového rozhraní
```

Testy pokrývají kódování protokolu proti záznamům v `research/` (tabulky funkcí kláves a maker bajt po bajtu,
záznamy podsvícení a kontrolní součet), profily včetně ukázkových, příkazovou řádku, webové API včetně
bezpečnostních kontrol, TUI (bez okna) a překlady. Do skutečné klávesnice nikdy nezapisují.

## Struktura projektu

```
revenant.py          ovladač: protokol, profily, příkazová řádka, TUI a server webového rozhraní
                     (jde importovat jako knihovna; závislosti si při spuštění doinstaluje sám)
LICENSE              MIT
README.md            dokumentace anglicky (README.cs.md česky)
revenant_web/        webové rozhraní (index.html, style.css, app.js s typy JSDoc, tsconfig.json pro kontrolu)
revenant_i18n/       překlady (cs.json); zdrojové texty jsou anglicky
revenant_profiles/   ukázkové profily, které se nainstalují při prvním spuštění
pyproject.toml       balíček revenant-rgb pro uvx / uv tool install (příkazy revenant a revenant-rgb)
requirements.txt     hidapi, textual, psutil – jen pro ruční instalaci
research/            zkoumání protokolu: záznamy, sniffer a pomůcky k němu
  sniff.py           Frida odposlech originálního softwaru → hidlog.txt
  capture_*          vzorky tabulek podsvícení, funkcí kláves a maker (používají je testy)
  listen.py          poslech vstupních reportů klávesnice
  clicker.ps1, act.ps1, shot.ps1   automatické ovládání GUI programu CZC (Windows)
tests/               testy (pytest, klávesnice není potřeba)
tools/               vývojové nástroje
  i18n_check.py      kontrola, že každý text má překlad
```

---

Licence: [MIT](https://github.com/lachyn/revenant-rgb/blob/main/LICENSE).

*Neoficiální projekt, není spojený s CZC.cz s.r.o. Používáš na vlastní riziko – v nejhorším případě
pomůže tovární reset Fn+Esc.*
