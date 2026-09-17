# ETL Project: Data Engineering for Sustainable Development in Colombia
**Course:** ETL (G01) - Universidad Autónoma de Occidente  
**Phase 1:** From Analytical Requirements to a Dimensional Data Warehouse  

---

## 1. Colombian Problem Definition & SDG
* **Selected SDG:** SDG 12 - Responsible Consumption and Production.
* **Relevant Target:** By 2030, achieve the sustainable management and efficient use of natural resources, promoting lifestyles in harmony with nature.
* **Context and Problem Statement:** In Colombia, the measurement of residential carbon footprint is often addressed fragmentarily or at a macroeconomic level, hindering the identification of key household emission hotspots (such as electric power consumption, cooking methods, and transportation). This project analyzes microdatos from Colombian households to quantify and characterize their direct environmental impact, scoping the study to the national and residential sector level.
* **Stakeholders / Users:** Ministry of Environment and Sustainable Development, National Planning Department (DNP), regional authorities, and academic entities dedicated to planning energy transition and sustainability policies.

## 2. Objective and Analytical Requirements (R1 - R5)
The analytical objective of this solution is to structure a dimensional Data Warehouse based on DANE's National Quality of Life Survey (ECV) and official factors, fulfilling the following business needs:

| ID | Analytical Requirement | Business Question | Supported Decision / Finding |
| :--- | :--- | :--- | :--- |
| **R1** | Electric Power Footprint | What is the average carbon footprint from electricity consumption by socioeconomic stratum (estrato)? | Supports targeted design of savings incentives and energy subsidies. |
| **R2** | Cooking Fuel Emissions | How do departmental emissions vary according to the type of fuel used for cooking (gas, propane, or firewood)? | Evaluates the effectiveness of firewood-to-gas substitution programs. |
| **R3** | Private Vehicle Impact | What is the percentage weight of private vehicles in total household emissions? | Guides urban sustainable mobility plans and clean technology transition. |
| **R4** | Geographic Prioritization | Which municipalities or departments have the highest per capita residential carbon footprint generation? | Allows prioritizing resource allocation for regional environmental campaigns. |
| **R5** | Efficiency by Household Size | Is there a direct relationship between the number of household members and per capita emission efficiency? | Underpins environmental education programs focused on responsible consumption. |

## 3. SDG Alignment
The project aligns directly with SDG 12 targets by providing visibility into household energy and material consumption. By linking ECV survey data with official emission factors (XM and IPCC/IDEAM), the solution transcends simple survey visualization and becomes an analytical tool for decision-making aimed at reducing material footprints in Colombia.

## 4. Data Source Selection and Evaluation
* **Primary Source:** DANE's National Quality of Life Survey (ECV) 2025 — catalog ID `DANE-DIMPE-ECV-2025`.
* **Source URL:** https://microdatos.dane.gov.co/index.php/catalog/905
* **Institution / Data Owner:** Departamento Administrativo Nacional de Estadística (DANE), Dirección de Metodología y Producción Estadística (DIMPE).
* **Files used** (4 of the survey's chapters):
  | File (DANE chapter) | Records | Variables | Key fields used |
  |---|---|---|---|
  | Servicios del hogar | 87,060 | 98 | `P5018` (electricity payment), `P5010` (estrato), `P8536` (cooking fuel), `P8540`/`P3163` (fuel payment) |
  | Datos de la vivienda | 86,848 | 46 | Department code |
  | Características y composición del hogar | 235,350 (person-level) | 78 | Household size |
  | Condiciones de vida del hogar y tenencia de bienes | 87,060 | 145 | `P1077S15` (private car ownership) |
* **Secondary Sources (Reference Dimensions):**
  * XM electricity emission factor ($0.097$ kg CO₂e/kWh).
  * Official IPCC / IDEAM factors for fuels (Firewood, Propane, Natural Gas).
  * Unit energy costs based on CREG tariffs per stratum.
* **Acquisition instructions:** download the relevant CSV files from the "Obtener Microdatos" tab at the source URL above (free registration required) and place them in `data/raw/` — these are git-ignored due to file size (see `.gitignore`); only the exact source URL is versioned here.

### Dataset Suitability Matrix

| Criterion | Assessment |
|---|---|
| Institution / Data Owner | DANE — Dirección de Metodología y Producción Estadística (DIMPE) |
| Source URL / Access Mechanism | https://microdatos.dane.gov.co/index.php/catalog/905 (free registration) |
| Format | CSV, SAV (SPSS), DTA (Stata) |
| Number of Records | 87,060 households surveyed (86,848 after deduplication) |
| Number of Attributes | 98 + 46 + 78 + 145 across the 4 files used |
| Geographic Coverage | National — Bogotá + 32 departments, urban and rural |
| Temporal Coverage | 2025 survey round |
| Relevant Numerical Measures | `P5018` (electricity payment), `P8540`/`P3163` (cooking fuel payment) |
| Relevant Categorical Attributes | `P5010` (estrato), `P8536` (cooking fuel type, 8 categories), department code, `P1077S15` (car ownership) |
| Potential Data-Quality Issues | ~23% nulls in `P5018`; 3 initially-assumed variables (`P5030`, `P5046S1A1`, `P5067`) turned out to be wrong per the official dictionary and were replaced (see Section 5) |
| Relationship with Analytical Requirements | Directly supports R1–R5 (see traceability table, Section 6) |
| Suitability for Dimensional Modeling | High — clear household grain, natural categorical dimensions |
| Unit of Observation in the Source | Household (hogar), identified by `DIRECTORIO` + `SECUENCIA_P` |

## 5. Data Profiling and Quality
Profiling was executed in `notebooks/data_profiling.ipynb` and cross-checked against DANE's official data dictionary (https://microdatos.dane.gov.co/index.php/catalog/905/data-dictionary).

**Findings:**
* Raw records (Servicios del hogar): 87,060
* Duplicate records removed (`DIRECTORIO` + `SECUENCIA_P`): 212 (0.24%)
* Missing values in `P5018` (electricity payment): 19,969 (22.9%) — imputed with the median payment within the same stratum (`P5010`)
* Outliers in `P5018`: 855 records above the 99th percentile ($420,000 COP), capped at that value
* Invalid zero values in `P5018` (stratum ≠ 1, where $0 is implausible): 123 records — imputed with the stratum median
* Final clean record count: 86,848

**Critical issue found and corrected:** the variables originally assumed for cooking-fuel type and expense (`P5030`, `P5046S1A1`, `P5067`) do **not** measure that at all according to the DANE dictionary — they correspond to sanitation type, waste-sorting habits, and aqueduct payment, respectively. They were replaced with the correct variables `P8536` (main cooking fuel, 8 categories) and `P8540`/`P3163` (cooking-fuel / piped-gas payment). Similarly, private-vehicle ownership was not present in the originally downloaded files at all; the correct variable, `P1077S15` ("Carro particular"), was found in a different chapter ("Condiciones de vida del hogar y tenencia de bienes", 145 variables) that had to be additionally downloaded.

## 6. Requirements-to-Data Traceability

| Requirement | Required Attributes | Transformation Needed | Expected KPI / Analysis |
|---|---|---|---|
| R1 | `P5018`, `P5010` | Null imputation, outlier capping, kWh estimation via stratum tariff, ×12 ×0.097 kg CO₂/kWh | Avg. annual electric footprint by stratum |
| R2 | `P8536`, `P8540`/`P3163`, department code | Map fuel type → emission factor (IPCC/IDEAM); convert cost → volume → TJ → kg CO₂ | Total/avg. cooking emissions by department & fuel |
| R3 | `P1077S15` | Map 1/2 → Sí/No; join as descriptive attribute in `dim_hogar` | Avg. total footprint, vehicle owners vs. non-owners |
| R4 | Department code, `huella_total_anual_kg` | Aggregate footprint by department ÷ household count | Per-capita footprint ranking by department |
| R5 | `num_personas`, `huella_total_anual_kg` | Aggregate footprint by household-size bucket ÷ `num_personas` | Per-capita footprint by household size |

## 7. Data Preparation Strategy
Based on the profiling findings above, the following cleaning rules were implemented in `src/transform.py`:
* **Deduplication** on `DIRECTORIO` + `SECUENCIA_P` (household grain).
* **Null imputation** in `P5018` using the median electricity payment within the same stratum.
* **Outlier treatment**: values above the 99th percentile of `P5018` are capped (winsorized), not removed, to preserve sample size.
* **Invalid-zero handling**: a $0 electricity payment is only accepted for stratum 1 (fully subsidized); for other strata it is treated as missing and imputed.
* **Column normalization**: all source column names are upper-cased and stripped of whitespace before processing.

## 8. Declared Grain and Dimensional Model (Star Schema)
* **Granularity Declaration:** *"A row in the Fact Table represents the estimated annual measurement of the carbon footprint for a specific Colombian household, uniquely identified by the survey control variables (DIRECTORIO and SECUENCIA_P)."*
* **Star Schema Diagram:**  
  ![Star Schema Diagram](docs/star_schema.png)

### Dimension and Measure Justification
| Table | Analytical Justification |
|---|---|
| `dim_hogar` | Carries the household identity plus descriptive attributes (`num_personas`, `tiene_vehiculo`) required by R3 and R5 — not just a technical key. |
| `dim_ubicacion` | Combination of department + stratum, the exact grouping needed by R1 (stratum) and R4 (department). |
| `dim_combustibles` | Emission factor per fuel type, required to compute R2. |
| `dim_tarifas` | Electricity cost per stratum, required to convert `P5018` (COP) into estimated kWh for R1. |
| `emisiones_energia_kg` (measure) | Directly answers R1. |
| `emisiones_coccion_kg` (measure) | Directly answers R2. |
| `huella_total_anual_kg` (measure) | The combined footprint used by R3, R4 and R5. |

### Requirements-to-Model Validation
| Requirement | Dimension(s) | Measure(s) | Expected Query/KPI | Supported? |
|---|---|---|---|---|
| R1 | dim_ubicacion (estrato) | emisiones_energia_kg, kwh_consumidos_estimados | AVG by estrato | Yes |
| R2 | dim_ubicacion (departamento), dim_combustibles | emisiones_coccion_kg | SUM/AVG by department & fuel | Yes |
| R3 | dim_hogar (tiene_vehiculo) | huella_total_anual_kg | AVG by vehicle ownership | Yes |
| R4 | dim_ubicacion (departamento), dim_hogar (num_personas) | huella_total_anual_kg | SUM ÷ SUM(num_personas) by department | Yes |
| R5 | dim_hogar (num_personas) | huella_total_anual_kg | AVG per capita by household size | Yes |

## 9. System Architecture (ETL Pipeline)
* **Architecture Flow Diagram:**
  ![System Architecture](docs/architecture.png)

## 10. ETL Pipeline and Data Warehouse
* **Technologies:** Python (Pandas, SQLAlchemy, PyMySQL), **MySQL 8.0**.
* **Pipeline phases** (`src/main.py` orchestrates all four in order):
  1. **Extract** (`src/extract.py`) — reads the raw ECV CSVs and the 3 reference-dimension CSVs from `data/raw/`, with automatic encoding/separator detection. No business transformations happen here.
  2. **Transform** (`src/transform.py`) — data cleansing (see Section 7) + dimensional transformation: surrogate-key generation, star-schema table construction, and the carbon-footprint calculation itself.
  3. **Validate** (`src/validate.py`) — 5 checks executed before any data reaches the database: row-count reconciliation with the source, critical-null checks, primary-key uniqueness, referential integrity (every foreign key exists in its dimension), and range/business-rule checks (no negative measures; `huella_total_anual_kg` = `emisiones_energia_kg` + `emisiones_coccion_kg`). Any failure raises an exception and stops the pipeline before it touches the database.
  4. **Load** (`src/load.py`) — executes `sql/create_dw.sql` (DROP + CREATE, i.e. a **full/complete load** strategy, not incremental), loads dimensions first and the fact table last, and also exports a CSV backup of every table to `data/processed/`.
* **Execution Instructions:**
  1. Clone the repository.
  2. Install dependencies: `pip install -r requirements.txt`.
  3. Create a local `.env` file (copy `.env.example`) with your MySQL credentials — this file is git-ignored and must never be committed.
  4. Create the target database in MySQL: `CREATE DATABASE huella_carbono_dw;`
  5. Place the ECV raw CSVs (Section 4) in `data/raw/`.
  6. Run the main pipeline: `python src/main.py`.

## 11. Limitations and Assumptions
* Cooking-fuel monthly cost is estimated using fixed reference prices (Natural gas: $1,800 COP/m³; LPG: $3,200 COP/kg), since the ECV records household *expenditure*, not physical consumption, and these prices are not region- or supplier-specific.
* Firewood consumption for households without a reported expense is assumed at a fixed 150 kg/month (IDEAM rural average), since firewood is frequently self-collected and unpriced.
* The Data Warehouse uses a **full (complete) load** strategy: every pipeline run drops and recreates all 5 tables. This guarantees a clean, reproducible state on every run, at the cost of not retaining historical snapshots between runs.
* R3 measures the *association* between vehicle ownership and a household's total footprint (energy + cooking); it does not yet estimate transport emissions directly, since the ECV does not capture private-vehicle fuel consumption.

## 12. Analytical Queries (SQL) and KPIs
The formal queries solving R1-R5 against the Data Warehouse are in [`sql/analytical_queries.sql`](sql/analytical_queries.sql).

| Requirement | Metric / KPI | DW Tables Used | Main Result |
|---|---|---|---|
| R1 | Avg. monthly kWh & annual CO₂ by stratum | fact_huella_carbono, dim_ubicacion | Consumption/emissions decrease from stratum 1-2 (highest, ~137-139 kWh/month) to stratum 6 (lowest, ~94 kWh/month) |
| R2 | Total/avg. cooking emissions by department & fuel | fact_huella_carbono, dim_ubicacion, dim_combustibles | Firewood emits ~3x more per household (3,145 kg/year) than LPG/natural gas; La Guajira leads in total firewood-related emissions (1,242 households) |
| R3 | Avg. total footprint by vehicle ownership | fact_huella_carbono, dim_hogar | Households WITHOUT a private car show a higher footprint (1,232 kg) than those with one (1,030 kg) — likely confounded by rurality and cooking-fuel type, not the vehicle itself (further analysis pending) |
| R4 | Per-capita footprint ranking by department | fact_huella_carbono, dim_ubicacion, dim_hogar | Vichada, Guainía, Amazonas and Vaupés (Orinoquía-Amazonía) lead in per-capita footprint (620-740 kg), consistent with lower natural-gas grid coverage |
| R5 | Per-capita footprint by household size | fact_huella_carbono, dim_hogar | Per-capita footprint drops from 1,000 kg (1-person households) to ~243 kg (8-person households) — clear household economies of scale |

> **Mandatory source:** all analytical queries were run directly against the MySQL Data Warehouse, not against the raw source files.

## 13. Business Intelligence (BI) and Analytical Findings
* **Visualization:** Interactive dashboard connected to the Data Warehouse.  
  *(PENDING — dashboard.png not yet attached to docs/)*
* **Key Findings:**
  1. **Cooking fuel type is the single biggest driver of household emissions, not electricity.** Households cooking with firewood emit roughly 3x more annually (~3,145 kg CO₂) than those using LPG or piped natural gas. This directly answers R2 and suggests firewood-to-gas substitution programs (already piloted by the Colombian government in rural areas) would have a larger emissions-reduction impact than electricity-efficiency campaigns.
  2. **The four departments with the highest per-capita residential footprint (Vichada, Guainía, Amazonas, Vaupés) are exactly the departments with the least natural-gas grid coverage**, per R4. This is relevant for Colombia because it points to energy-infrastructure investment, not household behavior change, as the most effective lever for reducing emissions in these regions — supporting resource-allocation decisions for the Ministry of Environment and DNP.
  3. **Per-capita footprint falls sharply as household size grows** (from 1,000 kg for single-person households to ~243 kg for 8-person households), per R5. This supports environmental-education and housing-policy arguments in favor of shared/denser housing as an emissions-reduction lever, since larger households achieve clear economies of scale in energy and cooking-fuel use.

## 14. Team Members and Responsibilities
| Name | Role |
|---|---|
| Nikol Hurtado | Persona 1 — Data Engineering & Architecture |
| David Aponte  | Persona 2 — Exploratory Analysis & Data Quality |
| Diana Panesso | Persona 3 — Dimensional Modeling & Business Rules |
| Sebastian Celorio| Persona 4 — Business Intelligence & Analytics |