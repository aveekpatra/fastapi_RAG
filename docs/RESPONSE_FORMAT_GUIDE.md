# Response Format Guide

## 🎯 New Response Structure

The improved system now provides structured, citation-rich responses that are easy to verify and understand.

## 📋 Response Format

### 1. Shrnutí relevance (Relevance Summary)
**Purpose:** Immediately tells user if cases answer their question

**Format:**
```
**Shrnutí relevance:**
[1-2 sentences about whether cases are relevant]
```

**Examples:**

**When cases ARE relevant:**
```
**Shrnutí relevance:**
3 z 5 rozhodnutí se přímo týkají výpovědi zaměstnance a poskytují 
odpověď na vaši otázku.
```

**When cases are NOT relevant:**
```
**Shrnutí relevance:**
⚠️ Poskytnutá rozhodnutí se nezabývají povinností rozsvícení světel. 
Rozhodnutí řeší jiné oblasti práva (daňové spory, smlouvy).
```

**When cases are PARTIALLY relevant:**
```
**Shrnutí relevance:**
2 rozhodnutí obsahují relevantní informace o náhradě škody, zbývající 
3 se týkají jiných právních otázek.
```

---

### 2. Analýza rozhodnutí (Case Analysis)
**Purpose:** Explains what each case actually contains

**Format:**
```
**Analýza rozhodnutí:**

📋 **[Spisová značka]** - [Soud], [Datum]
- **Co řešilo:** [Brief description of the case]
- **Klíčové závěry:** [Key conclusions from the court]
- **Právní předpisy:** [Laws mentioned in the case]
- **Relevance pro vaši otázku:** [How it relates to the question]
```

**Example:**
```
**Analýza rozhodnutí:**

📋 **31 C 39/2022-55** - Obvodní soud pro Prahu 1, 2023-09-20
- **Co řešilo:** Spor o zaplacení 200 000 Kč v souvislosti s daňovými 
  otázkami a nemajetkovou újmou
- **Klíčové závěry:** Soud rozhodl o povinnosti zaplatit částku na 
  základě § 2 z. č. 111/1994 Sb. (daň z přidané hodnoty)
- **Právní předpisy:** § 2 z. č. 111/1994 Sb., § 21 z. č. 111/1994 Sb., 
  § 34e z. č. 111/1994 Sb.
- **Relevance pro vaši otázku:** Toto rozhodnutí se netýká dopravních 
  předpisů ani povinnosti svícení

📋 **4 C 301/2019-305** - Obvodní soud pro Prahu 5, 2023-02-08
- **Co řešilo:** Spor o zaplacení 95 315,31 Kč za daň silniční a odtah 
  vozidla
- **Klíčové závěry:** Soud rozhodl o povinnosti uhradit daň silniční 
  podle nař. vl. č. 351/2013 Sb.
- **Právní předpisy:** nař. vl. č. 351/2013 Sb., § 1970 z. č. 89/2012 Sb.
- **Relevance pro vaši otázku:** Rozhodnutí se týká daně silniční, ne 
  pravidel provozu vozidel
```

---

### 3. Odpověď na otázku (Answer)
**Purpose:** Provides the actual answer with inline citations

**Format:**
```
**Odpověď na otázku:**
[Answer text with inline citations [^1], [^2], [^3]]
```

**Example with relevant cases:**
```
**Odpověď na otázku:**
Podle rozhodnutí Nejvyššího soudu [^1] je výpověď zaměstnance možná 
pouze za podmínek stanovených v § 52 zákoníku práce. Soud v tomto 
případě zdůraznil, že zaměstnavatel musí dodržet výpovědní dobu [^1] 
a poskytnout písemné odůvodnění [^2].

V případě porušení těchto podmínek je výpověď neplatná, jak potvrdil 
i Městský soud v Praze [^3], který rozhodl, že zaměstnanec má nárok 
na náhradu mzdy za dobu, kdy nemohl konat práci.
```

**Example with irrelevant cases:**
```
**Odpověď na otázku:**
⚠️ Poskytnutá rozhodnutí neobsahují informace o povinnosti rozsvícení 
světel motorových vozidel. Pro odpověď na tuto otázku by bylo potřeba 
nalézt rozhodnutí týkající se:
- Zákona č. 361/2000 Sb., o provozu na pozemních komunikacích
- Přestupků proti bezpečnosti a plynulosti provozu
- Konkrétních případů porušení povinnosti svícení

**Doporučení:**
Pro získání odpovědi na vaši otázku vyhledejte rozhodnutí obsahující 
klíčová slova: "povinnost svícení", "denní svícení", "zákon 361/2000"
```

---

### 4. Citované případy (Citations)
**Purpose:** Lists all cited cases for easy reference

**Format:**
```
**Citované případy:**
[^1]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]
[^2]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]
[^3]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]
```

**Example:**
```
**Citované případy:**
[^1]: 21 Cdo 1234/2023, Nejvyšší soud, 2023-05-15, 
      ECLI:ECLI:CZ:NS:2023:21.Cdo.1234.2023.1
[^2]: 14 Co 567/2023, Městský soud v Praze, 2023-03-20, 
      ECLI:ECLI:CZ:MSPH:2023:14.Co.567.2023.1
[^3]: 19 C 890/2022, Obvodní soud pro Prahu 9, 2023-01-10, 
      ECLI:ECLI:CZ:OSPH09:2023:19.C.890.2022.1
```

---

## 🎨 Visual Elements

### Emojis Used

| Emoji | Meaning | Usage |
|-------|---------|-------|
| 📋 | Case identifier | Before case number |
| ⚠️ | Warning/Notice | When cases aren't relevant |
| ⚖️ | Legal references | Before laws mentioned |
| 🏷️ | Keywords | Before case keywords |
| 🔗 | Source link | Before URLs |
| ✅ | Positive/Confirmed | When cases are relevant |

### Section Markers

```
**Bold text:** Section headers
[^1], [^2]: Inline citations
═══════: Visual separators (in case formatting)
```

---

## 📊 Complete Example

### Question: "Jaké jsou podmínky pro výpověď zaměstnance?"

### Response:

```
**Shrnutí relevance:**
3 z 5 rozhodnutí se přímo týkají výpovědi zaměstnance a poskytují 
odpověď na vaši otázku. Zbývající 2 rozhodnutí se týkají jiných 
pracovněprávních otázek.

**Analýza rozhodnutí:**

📋 **21 Cdo 1234/2023** - Nejvyšší soud, 2023-05-15
- **Co řešilo:** Spor o platnost výpovědi zaměstnance ze strany 
  zaměstnavatele pro porušení pracovní kázně
- **Klíčové závěry:** Soud rozhodl, že výpověď musí být písemná, 
  doručená a obsahovat konkrétní důvody podle § 52 zákoníku práce
- **Právní předpisy:** § 52 z. č. 262/2006 Sb., § 55 z. č. 262/2006 Sb.
- **Relevance pro vaši otázku:** Přímo odpovídá na otázku podmínek 
  výpovědi

📋 **14 Co 567/2023** - Městský soud v Praze, 2023-03-20
- **Co řešilo:** Odvolání zaměstnance proti výpovědi pro nadbytečnost
- **Klíčové závěry:** Zaměstnavatel musí prokázat nadbytečnost a nabídnout 
  jiné vhodné místo podle § 52 písm. c) zákoníku práce
- **Právní předpisy:** § 52 písm. c) z. č. 262/2006 Sb.
- **Relevance pro vaši otázku:** Upřesňuje podmínky pro výpověď z 
  organizačních důvodů

📋 **19 C 890/2022** - Obvodní soud pro Prahu 9, 2023-01-10
- **Co řešilo:** Náhrada mzdy po neplatné výpovědi
- **Klíčové závěry:** Při neplatné výpovědi má zaměstnanec nárok na 
  náhradu mzdy za dobu, kdy nemohl konat práci
- **Právní předpisy:** § 69 z. č. 262/2006 Sb.
- **Relevance pro vaši otázku:** Ukazuje důsledky porušení podmínek 
  výpovědi

📋 **5 C 123/2022** - Obvodní soud pro Prahu 1, 2022-11-15
- **Co řešilo:** Spor o náhradu škody způsobené zaměstnancem
- **Klíčové závěry:** Zaměstnanec odpovídá za škodu podle § 250 
  zákoníku práce
- **Právní předpisy:** § 250 z. č. 262/2006 Sb.
- **Relevance pro vaši otázku:** Netýká se výpovědi, ale odpovědnosti 
  za škodu

📋 **8 C 456/2022** - Obvodní soud pro Prahu 2, 2022-09-20
- **Co řešilo:** Spor o dovolenou
- **Klíčové závěry:** Zaměstnanec má nárok na dovolenou podle § 213 
  zákoníku práce
- **Právní předpisy:** § 213 z. č. 262/2006 Sb.
- **Relevance pro vaši otázku:** Netýká se výpovědi

**Odpověď na otázku:**
Podle rozhodnutí Nejvyššího soudu [^1] musí výpověď zaměstnance splňovat 
následující podmínky:

1. **Písemná forma:** Výpověď musí být dána v písemné formě a řádně 
   doručena zaměstnanci [^1]

2. **Zákonný důvod:** Výpověď lze dát pouze z důvodů uvedených v § 52 
   zákoníku práce [^1], například:
   - Porušení pracovní kázně zvlášť hrubým způsobem
   - Organizační důvody (nadbytečnost) [^2]
   - Zdravotní nezpůsobilost

3. **Konkrétní odůvodnění:** Výpověď musí obsahovat konkrétní důvody, 
   pro které je dávána [^1]

4. **Výpovědní doba:** Musí být dodržena výpovědní doba, která činí 
   nejméně 2 měsíce [^1]

5. **Nabídka jiného místa:** Při výpovědi z organizačních důvodů musí 
   zaměstnavatel nabídnout zaměstnanci jiné vhodné volné pracovní místo, 
   pokud takové má [^2]

Pokud nejsou tyto podmínky splněny, je výpověď neplatná a zaměstnanec 
má nárok na náhradu mzdy za dobu, kdy nemohl konat práci [^3].

**Citované případy:**
[^1]: 21 Cdo 1234/2023, Nejvyšší soud, 2023-05-15, 
      ECLI:ECLI:CZ:NS:2023:21.Cdo.1234.2023.1
[^2]: 14 Co 567/2023, Městský soud v Praze, 2023-03-20, 
      ECLI:ECLI:CZ:MSPH:2023:14.Co.567.2023.1
[^3]: 19 C 890/2022, Obvodní soud pro Prahu 9, 2023-01-10, 
      ECLI:ECLI:CZ:OSPH09:2023:19.C.890.2022.1
```

---

## 🎯 Key Features

### 1. Inline Citations
Every claim has a citation: `[^1]`, `[^2]`, `[^3]`

**Benefits:**
- ✅ Easy to verify claims
- ✅ Builds trust
- ✅ Shows which case supports which point
- ✅ Prevents hallucinations

### 2. Structured Format
Clear sections with headers

**Benefits:**
- ✅ Easy to scan
- ✅ Card-friendly layout
- ✅ Logical flow
- ✅ Professional appearance

### 3. Relevance Assessment
Upfront statement about case relevance

**Benefits:**
- ✅ Saves user time
- ✅ Sets expectations
- ✅ Honest about limitations
- ✅ Guides next steps

### 4. Detailed Case Analysis
Explains what each case contains

**Benefits:**
- ✅ User understands context
- ✅ Can judge relevance themselves
- ✅ Learns about related topics
- ✅ Discovers useful cases

---

## 🔧 Frontend Integration

### Parsing the Response

```typescript
interface ParsedResponse {
  relevanceSummary: string;
  caseAnalyses: CaseAnalysis[];
  answer: string;
  citations: Citation[];
}

interface CaseAnalysis {
  caseNumber: string;
  court: string;
  date: string;
  whatItSolved: string;
  keyConclusions: string;
  legalReferences: string[];
  relevance: string;
}

interface Citation {
  number: number;
  caseNumber: string;
  court: string;
  date: string;
  ecli: string;
}
```

### Rendering as Cards

```tsx
<div className="response">
  {/* Relevance Summary Card */}
  <Card className="relevance-summary">
    <CardHeader>
      <CardTitle>Shrnutí relevance</CardTitle>
    </CardHeader>
    <CardContent>
      {relevanceSummary}
    </CardContent>
  </Card>

  {/* Case Analysis Cards */}
  {caseAnalyses.map((analysis, i) => (
    <Card key={i} className="case-analysis">
      <CardHeader>
        <CardTitle>
          📋 {analysis.caseNumber}
        </CardTitle>
        <CardDescription>
          {analysis.court}, {analysis.date}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="analysis-section">
          <strong>Co řešilo:</strong>
          <p>{analysis.whatItSolved}</p>
        </div>
        <div className="analysis-section">
          <strong>Klíčové závěry:</strong>
          <p>{analysis.keyConclusions}</p>
        </div>
        <div className="analysis-section">
          <strong>Právní předpisy:</strong>
          <ul>
            {analysis.legalReferences.map((ref, j) => (
              <li key={j}>{ref}</li>
            ))}
          </ul>
        </div>
        <div className="analysis-section">
          <strong>Relevance:</strong>
          <p>{analysis.relevance}</p>
        </div>
      </CardContent>
    </Card>
  ))}

  {/* Answer Card */}
  <Card className="answer">
    <CardHeader>
      <CardTitle>Odpověď na otázku</CardTitle>
    </CardHeader>
    <CardContent>
      <CitationAwareMarkdown content={answer} />
    </CardContent>
  </Card>

  {/* Citations Card */}
  <Card className="citations">
    <CardHeader>
      <CardTitle>Citované případy</CardTitle>
    </CardHeader>
    <CardContent>
      <ol>
        {citations.map((citation, i) => (
          <li key={i}>
            <strong>{citation.caseNumber}</strong>, {citation.court}, 
            {citation.date}, ECLI: {citation.ecli}
          </li>
        ))}
      </ol>
    </CardContent>
  </Card>
</div>
```

---

## ✅ Quality Checklist

Use this checklist to verify response quality:

- [ ] **Relevance summary present** - First section assesses relevance
- [ ] **Each case analyzed** - All cases have structured analysis
- [ ] **Inline citations used** - Every claim has [^X]
- [ ] **Citations list at end** - All [^X] references listed
- [ ] **No hallucinations** - All info from provided cases
- [ ] **Clear when irrelevant** - Honest about limitations
- [ ] **Structured format** - Uses headers and sections
- [ ] **Emojis for clarity** - Visual markers present

---

## 📚 Additional Resources

- **Anti-Hallucination Guide**: `ANTI_HALLUCINATION_IMPROVEMENTS.md`
- **Implementation Details**: `IMPROVED_RAG_PIPELINE.md`
- **Quick Reference**: `QUICK_REFERENCE.md`

---

## 🎉 Summary

The new response format provides:
- ✅ **Structured** - Clear sections with headers
- ✅ **Cited** - Inline citations for every claim
- ✅ **Honest** - Clear about relevance and limitations
- ✅ **Detailed** - Explains what cases actually contain
- ✅ **Card-friendly** - Easy to parse and display
- ✅ **Verifiable** - Every claim can be checked

This format dramatically reduces hallucinations and builds user trust! 🎯
