-- =========================================================================
-- PROJECT : ETL - Huella de Carbono de Hogares Colombianos (ODS 12)
-- FILE    : create_dw.sql
-- DESC    : DDL para crear el Data Warehouse dimensional (Star Schema).
--           Compatible con MySQL, PostgreSQL y SQLite.
--           Las surrogate keys se generan desde Python.
-- =========================================================================

-- -----------------------------------------------------------------
-- Eliminar tablas existentes (orden inverso por dependencias FK)
-- -----------------------------------------------------------------
DROP TABLE IF EXISTS fact_huella_carbono;
DROP TABLE IF EXISTS dim_tarifas;
DROP TABLE IF EXISTS dim_combustibles;
DROP TABLE IF EXISTS dim_ubicacion;
DROP TABLE IF EXISTS dim_hogar;


-- =================================================================
-- DIMENSIONES
-- =================================================================

-- -----------------------------------------------------------------
-- dim_hogar: Un registro por hogar encuestado en la ECV.
-- Grano: combinación única de DIRECTORIO + SECUENCIA_P.
-- -----------------------------------------------------------------
CREATE TABLE dim_hogar (
    sk_hogar          INTEGER PRIMARY KEY,
    directorio        INTEGER NOT NULL,
    secuencia_p       INTEGER NOT NULL,
    num_personas      INTEGER DEFAULT 1,
    tiene_vehiculo    VARCHAR(10) DEFAULT 'No'
);


-- -----------------------------------------------------------------
-- dim_ubicacion: Ubicación geográfica + estrato del hogar.
-- Grano: combinación única de (codigo_departamento, estrato).
-- -----------------------------------------------------------------
CREATE TABLE dim_ubicacion (
    sk_ubicacion          INTEGER PRIMARY KEY,
    codigo_departamento   INTEGER,
    nombre_departamento   VARCHAR(100),
    estrato               INTEGER
);


-- -----------------------------------------------------------------
-- dim_combustibles: Tipo de combustible para cocción con su factor
-- de emisión oficial (IPCC / IDEAM), expresado en kg CO₂ / TJ.
-- -----------------------------------------------------------------
CREATE TABLE dim_combustibles (
    sk_combustible        INTEGER PRIMARY KEY,
    tipo_combustible      VARCHAR(100),
    factor_emision_kg_tj  REAL
);


-- -----------------------------------------------------------------
-- dim_tarifas: Costo estimado de energía eléctrica por estrato
-- socioeconómico, basado en tarifas CREG vigentes.
-- -----------------------------------------------------------------
CREATE TABLE dim_tarifas (
    sk_tarifa            INTEGER PRIMARY KEY,
    estrato_aplica       INTEGER,
    costo_promedio_kwh   REAL
);


-- =================================================================
-- TABLA DE HECHOS
-- =================================================================

-- -----------------------------------------------------------------
-- fact_huella_carbono: Medición anual estimada de la huella de
-- carbono residencial de un hogar colombiano.
-- Grano: un registro por hogar (DIRECTORIO + SECUENCIA_P).
-- -----------------------------------------------------------------
CREATE TABLE fact_huella_carbono (
    sk_fact                    INTEGER PRIMARY KEY,
    fk_hogar                   INTEGER NOT NULL,
    fk_ubicacion               INTEGER NOT NULL,
    fk_combustible_cocina      INTEGER,
    fk_tarifa_energia          INTEGER,
    kwh_consumidos_estimados   REAL,
    emisiones_energia_kg       REAL,
    emisiones_coccion_kg       REAL,
    huella_total_anual_kg      REAL,

    FOREIGN KEY (fk_hogar)              REFERENCES dim_hogar (sk_hogar),
    FOREIGN KEY (fk_ubicacion)          REFERENCES dim_ubicacion (sk_ubicacion),
    FOREIGN KEY (fk_combustible_cocina) REFERENCES dim_combustibles (sk_combustible),
    FOREIGN KEY (fk_tarifa_energia)     REFERENCES dim_tarifas (sk_tarifa)
);
