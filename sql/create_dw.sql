-- =========================================
-- CREAR BASE DE DATOS
-- =========================================

CREATE DATABASE IF NOT EXISTS huella_carbono;

USE huella_carbono;


-- =========================================
-- DIMENSIÓN: UBICACIÓN
-- =========================================

CREATE TABLE dim_ubicacion (
    sk_ubicacion INT AUTO_INCREMENT PRIMARY KEY,
    codigo_departamento VARCHAR(10) NOT NULL,
    nombre_departamento VARCHAR(100) NOT NULL,
    estrato INT
);


-- =========================================
-- DIMENSIÓN: HOGAR
-- =========================================

CREATE TABLE dim_hogar (
    sk_hogar INT AUTO_INCREMENT PRIMARY KEY,
    directorio VARCHAR(100),
    secuencia_p VARCHAR(50),
    num_personas INT,
    tiene_vehiculo BOOLEAN
);


-- =========================================
-- DIMENSIÓN: COMBUSTIBLES
-- =========================================

CREATE TABLE dim_combustibles (
    sk_combustible INT AUTO_INCREMENT PRIMARY KEY,
    tipo_combustible VARCHAR(100) NOT NULL,
    factor_emision_kg_tj DECIMAL(12,6) NOT NULL
);


-- =========================================
-- DIMENSIÓN: TARIFAS
-- =========================================

CREATE TABLE dim_tarifas (
    sk_tarifa INT AUTO_INCREMENT PRIMARY KEY,
    estrato_aplica INT NOT NULL,
    costo_promedio_kwh DECIMAL(12,4) NOT NULL
);


-- =========================================
-- TABLA DE HECHOS
-- =========================================

CREATE TABLE fact_huella_carbono (
    id_huella INT AUTO_INCREMENT PRIMARY KEY,

    fk_ubicacion INT NOT NULL,
    fk_hogar INT NOT NULL,
    fk_combustible_cocina INT,
    fk_tarifa_energia INT,

    kwh_consumidos_estimados DECIMAL(14,4),
    emisiones_energia_kg DECIMAL(14,4),
    emisiones_coccion_kg DECIMAL(14,4),
    huella_total_anual_kg DECIMAL(14,4),

    -- Foreign Keys
    CONSTRAINT fk_fact_ubicacion
        FOREIGN KEY (fk_ubicacion)
        REFERENCES dim_ubicacion(sk_ubicacion),

    CONSTRAINT fk_fact_hogar
        FOREIGN KEY (fk_hogar)
        REFERENCES dim_hogar(sk_hogar),

    CONSTRAINT fk_fact_combustible
        FOREIGN KEY (fk_combustible_cocina)
        REFERENCES dim_combustibles(sk_combustible),

    CONSTRAINT fk_fact_tarifa
        FOREIGN KEY (fk_tarifa_energia)
        REFERENCES dim_tarifas(sk_tarifa)
);