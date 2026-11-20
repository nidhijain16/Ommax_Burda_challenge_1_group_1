# FACTS Topic Opportunity Scout — Complete System Architecture & Flowchart

**TUM × OMMAX AI Hackathon · Hubert Burda Media / FACTS**

---

## 1. End-to-End System Flowchart (Mermaid Diagram)

```mermaid
flowchart TD
    subgraph Data_Layer ["1. DATA INGESTION & DOSSIER BUILDER"]
        A["10 CSV Data Tables\n(00_taxonomy to 09_spaces)"] --> B["data_loader.py\n(Loads & indexes by ID & topic_key)"]
        B --> C["Topic Dossier Aggregator\n(Signals, Indicators, Competitors, Learnings)"]
        C --> D["Publisher Deduplicator\n(08_sources.csv: counts distinct publishers)"]
    end

    subgraph Scoring_Layer ["2. DETERMINISTIC SCORING ENGINE (scorer.py)"]
        D --> E["5-Dimension Math Engine (0.0 to 5.0)"]
        E --> F1["A. Consumer Relevance (CR: 15%)\nBase 2.0 + YMYL (1.5) + Need signals"]
        E --> F2["B. Timing & Why Now (TD: 15%)\nGEG/Subsidies + Events + Indicators"]
        E --> F3["C. Competitive White Space (WS: 20%)\nDirectory/Award vs Well-served"]
        E --> F4["D. Portfolio Fit (PF: 10%)\nAdjacent expansion vs Cannibalisation"]
        E --> F5["E. Commercial Potential (CP: 15%)\nPopulation size + Master list route"]
        E --> F6["Risk & Precedent Audit (Risk: 25%)\nBGH rulings + Vulnerability penalties"]
        
        F1 & F2 & F3 & F4 & F5 & F6 --> G["Overall Composite Score\nWeighted Sum: 0.0 to 5.0"]
    end

    subgraph Decision_Gate ["3. STRICT WATERFALL STATUS GATEKEEPER"]
        G --> H{"Is Topic Vulnerable or\nHas BGH Court Ruling L...?"}
        H -- Yes --> I["DO NOT PURSUE 🔴\n(e.g. Funeral Services, Debt)"]
        H -- No --> J{"Is Market Well-Served or\nDirect FOCUS Duplicate?"}
        J -- Yes --> K["DEPRIORITISE ⚪\n(Crowded/Entrenched Markets)"]
        J -- No --> L{"Passes All 9 Strict Gates?\n(WS>=3.5, TD>=2.5, CP>=3.0, Risk>=2.2)"}
        L -- Yes --> M["VALIDATE NEXT 🟢\n(e.g. Heat Pumps, Vet Clinics)"]
        L -- No --> N["MONITOR 🟡\n(e.g. DiGA Apps, Stairlifts)"]
    end

    subgraph Generation_Layer ["4. OPPORTUNITY CARD SYNTHESIZER (generator.py)"]
        I & K & M & N --> O["Pydantic Schema Gatekeeper\n(Regex validation: ^[A-Z]{1,3}\\d{3,4}$)"]
        O --> P["14-Field Opportunity Card\n(Facts strictly separated from Hypotheses)"]
    end

    subgraph Interface_Layer ["5. EXECUTIVE COCKPIT & AI ANALYST (app.py)"]
        P --> Q["Interactive Streamlit Cockpit"]
        Q --> R1["Persistent 32-Topic Dropdown\n(Direct browse any topic)"]
        Q --> R2["Jury Wildcard Matcher\n(Type 'vet', 'driving', 'pv')"]
        Q --> R3["Grounded Raw Evidence Tabs\n(Signals, Indicators, Competitors)"]
        Q --> R4["Tesseracted Labs AI Gateway\n(DeepSeek-V4.1-Flash Q&A & Memos)"]
    end

    subgraph Deliverables ["6. OFFICIAL DELIVERABLES EXPORT"]
        P --> S1["cards.json\n(Machine-readable deliverable)"]
        P --> S2["cards.md\n(Executive Markdown report)"]
        P --> S3["cards.html\n(Standalone browser viewer)"]
        P --> S4["LOGIC.md\n(1-page scoring methodology)"]
    end
```

---

## 2. Text Architecture Map (Quick Overview)

```
[CSV Datasets (10 Files)]
       │
       ├──► 00_topic_taxonomy.csv (Master 32 Topics, YMYL Status)
       ├──► 01_portfolio.csv      (Current FOCUS Lists & Cannibalisation)
       ├──► 02_learnings.csv      (German Court Precedents & BGH Rulings)
       ├──► 03_signals.csv        (Why-Now Market Signals & Drivers)
       ├──► 04_competitors.csv    (Competitor Rankings & Provider-Pays Proof)
       ├──► 05_market_indicators.csv (Numeric Time-Series Data Points)
       ├──► 06_entity_populations.csv (Entity Sizing & Register Availability)
       ├──► 07_regulatory_events.csv (Dated Laws & Deadlines)
       ├──► 08_sources.csv        (296 Unique Publishers Deduplicated)
       └──► 09_opportunity_spaces.csv (Curated Specific Topics & Hypotheses)
       │
       ▼
[Deterministic Scoring Engine: src/scorer.py]
       ├── Dimension A: Consumer Relevance (15%)
       ├── Dimension B: Timing & Why Now (15%)
       ├── Dimension C: Competitive White Space (20%)
       ├── Dimension D: Portfolio Fit & Brand Alignment (10%)
       ├── Dimension E: Commercial Potential & Entity Pool (15%)
       └── Dimension F: Risk, Precedent & Vulnerability Audit (25%)
       │
       ▼
[Waterfall Status Classifier]
       ├── DO NOT PURSUE   (Red Light: Precedents / Vulnerable Consumers)
       ├── DEPRIORITISE    (Grey Light: Well-Served / Direct Duplicates)
       ├── VALIDATE NEXT   (Green Light: High White Space & Clean Feasibility)
       └── MONITOR         (Yellow Light: Emerging / Waiting for Scale)
       │
       ▼
[Pydantic Guardrail Gatekeeper: src/models.py]
       └── Regex check: Every fact MUST cite a valid ID (^[A-Z]{1,3}\d{3,4}$)
       │
       ▼
[Executive Streamlit Cockpit: app.py]
       ├── 32-Topic Dropdown + Live Jury Matcher
       ├── 14-Field Interactive Opportunity Card Viewer
       ├── Tesseracted Labs Shared AI Gateway (DeepSeek-V4.1-Flash)
       └── Built-In Deliverables Reader (cards.md, cards.json, LOGIC.md, cards.html)
```

---

## 3. The 3-to-5 Curated Deliverable Portfolio

The official deliverables (`cards.md`, `cards.json`, `cards.html`) showcase a balanced portfolio of **5 distinct strategic decisions**:

1. **`heat_pumps`** $\rightarrow$ **VALIDATE NEXT (Score: 3.66)**  
   *TOP Heat-pump installers for owner-occupied homes* (SHK craft businesses, GEG heating law, massive B2B seal licensing potential).
2. **`veterinary`** $\rightarrow$ **VALIDATE NEXT (Score: 3.79)**  
   *TOP Veterinary practices and emergency vet services* (Booming pet health, rising GOT fee schedule, zero court bans).
3. **`home_adaptation`** $\rightarrow$ **MONITOR (Score: 3.73)**  
   *TOP Age-appropriate home adaptation providers* (High demographic need, but fragmented Handwerksrolle master list).
4. **`digital_health`** $\rightarrow$ **MONITOR (Score: 3.51)**  
   *TOP Digital health applications (DiGA) orientation* (High consumer need, but current universe is only 58 approved apps).
5. **`end_of_life`** $\rightarrow$ **DO NOT PURSUE (Score: 3.06)**  
   *TOP Funeral service providers (Bestatter)* (Killed to protect Burda from public backlash and court bans `L015`).
