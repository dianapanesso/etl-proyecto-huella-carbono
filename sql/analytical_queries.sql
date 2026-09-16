-- =========================================================================
-- PROJECT: ETL - Carbon Footprint of Colombian Households (SDG 12)
-- FILE: analytical_queries.sql
-- DESCRIPTION: SQL queries addressing analytical requirements R1 to R5 
--              using the dimensional Data Warehouse (Star Schema).
-- =========================================================================

-- -------------------------------------------------------------------------
-- R1: Electric Power Footprint
-- Business Question: What is the average carbon footprint from electricity 
-- consumption by socioeconomic stratum (estrato)?
-- -------------------------------------------------------------------------
SELECT 
    d.estrato,
    COUNT(f.fk_hogar) AS total_households,
    ROUND(AVG(f.kwh_consumidos_estimados), 2) AS avg_monthly_kwh,
    ROUND(AVG(f.emisiones_energia_kg), 2) AS avg_annual_co2_kg
FROM 
    fact_huella_carbono f
JOIN 
    dim_ubicacion d ON f.fk_ubicacion = d.sk_ubicacion
GROUP BY 
    d.estrato
ORDER BY 
    d.estrato ASC;


-- -------------------------------------------------------------------------
-- R2: Cooking Fuel Emissions
-- Business Question: How do departmental emissions vary according to the type 
-- of fuel used for cooking (gas, propane, or firewood)?
-- -------------------------------------------------------------------------
SELECT 
    u.nombre_departamento,
    c.tipo_combustible,
    COUNT(f.fk_hogar) AS total_households,
    ROUND(SUM(f.emisiones_coccion_kg), 2) AS total_emissions_co2_kg,
    ROUND(AVG(f.emisiones_coccion_kg), 2) AS avg_emissions_per_household_kg
FROM 
    fact_huella_carbono f
JOIN 
    dim_ubicacion u ON f.fk_ubicacion = u.sk_ubicacion
JOIN 
    dim_combustibles c ON f.fk_combustible_cocina = c.sk_combustible
GROUP BY 
    u.nombre_departamento, 
    c.tipo_combustible
ORDER BY 
    total_emissions_co2_kg DESC;


-- -------------------------------------------------------------------------
-- R3: Private Vehicle Impact
-- Business Question: What is the percentage weight of private vehicles in 
-- total household emissions?
-- -------------------------------------------------------------------------
SELECT 
    h.tiene_vehiculo,
    COUNT(f.fk_hogar) AS total_households,
    ROUND(AVG(f.huella_total_anual_kg), 2) AS avg_total_carbon_footprint_kg
FROM 
    fact_huella_carbono f
JOIN 
    dim_hogar h ON f.fk_hogar = h.sk_hogar
GROUP BY 
    h.tiene_vehiculo;


-- -------------------------------------------------------------------------
-- R4: Geographic Prioritization
-- Business Question: Which municipalities or departments have the highest 
-- per capita residential carbon footprint generation?
-- -------------------------------------------------------------------------
SELECT 
    u.nombre_departamento,
    ROUND(SUM(f.huella_total_anual_kg) / SUM(h.num_personas), 2) AS per_capita_co2_kg,
    ROUND(SUM(f.huella_total_anual_kg), 2) AS cumulative_departmental_co2_kg
FROM 
    fact_huella_carbono f
JOIN 
    dim_ubicacion u ON f.fk_ubicacion = u.sk_ubicacion
JOIN 
    dim_hogar h ON f.fk_hogar = h.sk_hogar
GROUP BY 
    u.nombre_departamento
ORDER BY 
    per_capita_co2_kg DESC;


-- -------------------------------------------------------------------------
-- R5: Efficiency by Household Size
-- Business Question: Is there a direct relationship between the number of 
-- household members and per capita emission efficiency?
-- -------------------------------------------------------------------------
SELECT 
    h.num_personas AS household_size,
    COUNT(f.fk_hogar) AS total_households,
    ROUND(AVG(f.huella_total_anual_kg), 2) AS avg_total_footprint_kg,
    ROUND(AVG(f.huella_total_anual_kg / h.num_personas), 2) AS avg_per_capita_footprint_kg
FROM 
    fact_huella_carbono f
JOIN 
    dim_hogar h ON f.fk_hogar = h.sk_hogar
GROUP BY 
    h.num_personas
ORDER BY 
    h.num_personas ASC;