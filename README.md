# Logsync

Frågeskärm för programledare, med logg mot kamerans tidskod. Operatören styr från sin dator, programledaren ser frågorna på en egen skärm, och det operatören antecknar under inspelningen får kamerans tidskod så att det kan användas som underlag för grovklipp.

Appen är en enda fil, `index.html`. Öppna den publicerade versionen:

**https://philipatspoon.github.io/logsync/**

eller ladda ner `index.html` och öppna filen direkt i Chrome eller Edge. Båda sätten fungerar utan nät när appen väl har öppnats en gång (den publicerade versionen sparas av webbläsaren).

All data ligger i din webbläsare: manus, logg, inställningar, branding och typsnitt. Inget av det finns i den här koden eller skickas någonstans.

## Inspelningsdag

1. Koppla in programledarens skärm som **utökad skärm** (inte speglad).
2. Öppna appen. Klicka **Öppna värdskärm**, dra fönstret till den andra skärmen och klicka i det för helskärm.
3. Styr med tangentbordet eller en presentationsklicker.

| Tangent | Funktion |
|---|---|
| → / Space / PageDown | Nästa steg: fråga → följdfrågan blir stor → nästa fråga |
| ← / PageUp | Bakåt |
| ↑ / ↓ | Hoppa ett helt kort |
| F | Visa eller dölj följdfrågan (i ett moment: visa alla alternativ) |
| I | Visa eller dölj bakgrunden för programledaren |
| B | Standby (svart skärm) |
| 1–9 | Skicka snabbmeddelande till programledaren |
| Esc | Rensa meddelandet |
| − / + | Mindre eller större text på aktuellt kort (sparas per kort) |
| R | REC start/stopp (loggen) |
| Shift + 1–9 | Loggknapp: Bra svar, Bra tagning, Omtag … |
| C | Skriv kommentar (tidskoden sätts när du börjar skriva) |
| T | Starta eller pausa inspelningstimern |

## Manus

Under **Redigera** finns episoder, sektioner och kort. Allt sparas automatiskt.

**Importera från Google Docs:** markera allt i manuset, kopiera och klistra in. Importen känner igen:

- rubriker som börjar med `BLOCK`, `MOMENT`, `OUTRO` (sektioner)
- `Core questions` / `Guest questions` (frågetyp)
- punktlistor och numrerade listor (ett kort per rad)
- `Follow-up:` (följdfråga) och `Background:` (din egen anteckning)
- `↻` (återkommande fråga)
- repliker i outrot på formen `Namn: replik`

## Logg med kamerans tidskod

1. Starta inspelningen på kameran och tryck **REC** (R) i appen.
2. Synkfönstret öppnas. Appen läser tidskoden från kamerans skärm och synkar när sex avläsningar stämmer med varandra (2–5 sekunder). Tre sätt att läsa av:
   - **Med mobil (QR):** skanna QR-koden en gång, ställ mobilen mot kamerans skärm och dra en ruta runt tidskoden. Sedan läser mobilen av själv vid varje REC.
   - **Med kamera:** datorns webbkamera riktad mot kamerans skärm.
   - **Manuellt** eller **klockslag**, om kameran går på Time of Day.
3. Varje kort du stegar till loggas automatiskt. Lägg till taggar (Shift + 1–9) och kommentarer (C).
4. **Exportera logg → Kopiera för Claude / ChatGPT** ger ett färdigt underlag: instruktion i steg, manus, tid på skärm för varje fråga, dina taggar och kommentarer, och samma logg som JSON. Har du transkriberat med Logsync-appen flätas transkriptet in på rätt tidskod. Annars bifogar du ett eget transkript.

Varje klipp sparar sin egen synk, så det fungerar med både Free Run och Rec Run. Precisionen är inom en till två rutor. Mät kamerans fördröjning en gång under *Precision* i synkfönstret.

Mobilen och datorn pratar via den publika tjänsten [ntfy.sh](https://ntfy.sh) i en slumpad kanal. Det enda som skickas är en synkkod på sju tecken. Tjänsten tillåter 250 meddelanden per dygn och nätverk, och en synk kostar fyra, så det räcker till ungefär 60 synkar per dag. Går det inte att nå tjänsten visar mobilen koden, och du skriver in den på datorn.

Textigenkänningen (Tesseract) hämtas från nätet första gången och sparas sedan av webbläsaren. Gör en provsynk innan inspelningsdagen.

## Branding

Appen har ingen egen branding. Under ⚙︎ → *Branding* skriver du en webbadress och trycker **Hämta från webbplats**. Logsync hämtar sidans logotyp, färger och typsnitt, och du väljer vad som ska användas:

- logotypen visas i värdskärmens hörn och i standby
- en av färgerna kan användas för meddelanden till programledaren
- typsnittet används för all text på värdskärmen (typsnitt har ofta licensvillkor – använd det bara om ni har rätt till det)

Hämtningen görs av Logsync-appen (se nedan), eftersom en webbsida inte får läsa andra webbplatser. Utan appen kan du lägga in en logotypfil (SVG eller PNG) och typsnittsfiler (.woff2, .ttf eller .otf) för hand på samma ställe.

## Logsync-appen (Mac)

En liten menyradsapp som gör det webbläsaren inte kan:

- **transkriberar kamerafiler** lokalt med kamerans tidskod, en ljudkanal per person, och läser in transkriptet i loggen (*Exportera logg → Transkript*)
- **hämtar branding** från en webbplats

Installera genom att köra det här i Terminal:

```bash
curl -fsSL https://philipatspoon.github.io/logsync/install.sh | bash
```

Appen byggs på datorn och läggs i Program-mappen i din hemmapp. Det fungerar även på datorer där IT bara tillåter appar från App Store och kända utvecklare. Alternativt: ladda ner [Logsync-app.zip](https://philipatspoon.github.io/logsync/Logsync-app.zip) och följ `LÄS MIG.txt`. Appen startas från Logsync i webbläsaren och stängs av därifrån eller från menyraden. Inget körs i bakgrunden när den är avstängd.

Allt appen laddar ner – Whisper-modellen, Python och paketen, totalt cirka 3 GB – ligger i en enda mapp, `~/Library/Application Support/Logsync`. *Avinstallera Logsync* i LS-menyn tar bort appen och hela mappen.

Appen lyssnar bara på den egna datorn och svarar bara de adresser som står i `ALLOWED_ORIGINS` överst i `helper/Logsync.app/Contents/Resources/logsync_helper.py`. Kör du Logsync från en annan adress lägger du till den där.

## Backup och flytt

**Redigera → Exportera backup** sparar manus, loggar, inställningar, branding och typsnitt i en fil. **Läs in backup** återställer dem, också i en annan webbläsare eller på en annan dator. Exportera en backup efter varje inspelningsdag.

Datan hör till adressen appen öppnas från. Byter du mellan den lokala filen och den publicerade adressen flyttar du datan med en backup.

## Utveckling

`index.html` är hela appen. `sw.js` gör att den publicerade versionen startar utan nät. `helper/` innehåller Logsync-appen; kör `python3 helper/build-zip.py` efter ändringar där så att `Logsync-app.zip` följer med.

```bash
node tests/run.js
```

kör testerna (kräver Playwright med Chromium, och python3 för testerna av hjälptjänsten). De använder lokala kopior av relätjänsten och av en webbplats, och går inte ut på nätet. De öppnar appen som lokal fil och kontrollerar navigering, värdskärm, redigering, import, tidskodsmatte, logg, export och backup.

Relätjänsten kan bytas mot en egen ntfy-server genom att sätta `localStorage.setItem('vh.relay', 'https://…')` i webbläsarens konsol på både datorn och mobilen.
