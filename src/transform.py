"""
==========================================================================
Módulo de Transformación (T) — ETL Huella de Carbono
==========================================================================
Aplica las reglas de limpieza definidas en el notebook de data profiling:

  1. Deduplicación por DIRECTORIO + SECUENCIA_P
  2. Imputación de nulos en P5018 con la mediana por estrato (P5010)
  3. Truncamiento de outliers al percentil 99
  4. Tratamiento de ceros (imputar si estrato ≠ 1)

Luego calcula las métricas de huella de carbono y construye las tablas
del modelo estrella (dimensiones + tabla de hechos).
==========================================================================
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# =========================================================================
# CONSTANTES
# =========================================================================

# ── Factor de emisión eléctrico (XM, Colombia) ──────────────────────────
FACTOR_ELECTRICO_DEFAULT = 0.097  # kg CO₂e / kWh

# ── Precios promedio de referencia para cocción (COP) ────────────────────
PRECIO_GAS_NATURAL_M3 = 1_800   # COP / m³ (red pública)
PRECIO_GLP_KG = 3_200           # COP / kg  (cilindro / pipeta)

# ── Valores calóricos netos (Net Calorific Value) ────────────────────────
NCV_GAS_NATURAL_MJ_M3 = 37.2    # MJ / m³
NCV_GLP_MJ_KG = 47.3            # MJ / kg
NCV_LENA_MJ_KG = 15.6           # MJ / kg

# ── Conversión de unidades ───────────────────────────────────────────────
MJ_POR_TJ = 1_000_000           # 1 TJ = 10⁶ MJ

# ── Consumo estimado de leña para hogares sin dato de gasto ──────────────
CONSUMO_LENA_KG_MES = 150       # ~5 kg/día (IDEAM, promedio rural)

# ── Mapeo ECV P5030 → id_combustible de dim_combustibles.csv ─────────────
#    P5030: 1=Electricidad, 2=Gas natural, 3=GLP, 4=Leña,
#           5=Carbón mineral, 6=Petróleo/kerosén, 9=No cocinan
MAPA_P5030_A_COMBUSTIBLE = {
    2: 3,   # Gas natural (ECV=2) → id_combustible=3
    3: 2,   # GLP/Propano (ECV=3) → id_combustible=2
    4: 1,   # Leña        (ECV=4) → id_combustible=1
}

# ── Códigos DANE de departamentos de Colombia ────────────────────────────
DEPARTAMENTOS_COLOMBIA = {
    5: "Antioquia", 8: "Atlántico", 11: "Bogotá, D.C.",
    13: "Bolívar", 15: "Boyacá", 17: "Caldas", 18: "Caquetá",
    19: "Cauca", 20: "Cesar", 23: "Córdoba", 25: "Cundinamarca",
    27: "Chocó", 41: "Huila", 44: "La Guajira", 47: "Magdalena",
    50: "Meta", 52: "Nariño", 54: "Norte de Santander",
    63: "Quindío", 66: "Risaralda", 68: "Santander", 70: "Sucre",
    73: "Tolima", 76: "Valle del Cauca", 81: "Arauca",
    85: "Casanare", 86: "Putumayo", 88: "San Andrés y Providencia",
    91: "Amazonas", 94: "Guainía", 95: "Guaviare",
    97: "Vaupés", 99: "Vichada",
}

# ── Columnas candidatas para encontrar el código de departamento ─────────
COLS_DEPARTAMENTO = ["DEPARTAMENTO", "DPTO", "P1_DEPARTAMENTO", "DEPTO"]

# ── Columnas candidatas para vehículo particular ─────────────────────────
COLS_VEHICULO = ["P5210S10A1", "P1091S1", "P5250S9A1"]


# =========================================================================
# FUNCIONES AUXILIARES
# =========================================================================

def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte los nombres de columnas a MAYÚSCULAS y elimina espacios."""
    df.columns = df.columns.str.strip().str.upper()
    return df


def _buscar_columna(df: pd.DataFrame, candidatas: list[str]) -> str | None:
    """Retorna el primer nombre de columna encontrado en el DataFrame."""
    for col in candidatas:
        if col in df.columns:
            return col
    return None


# =========================================================================
# FUNCIONES DE LIMPIEZA (Data Cleansing)
# =========================================================================

def _deduplicar(df: pd.DataFrame) -> pd.DataFrame:
    """Paso 1: Elimina duplicados por DIRECTORIO + SECUENCIA_P."""
    antes = len(df)
    df = df.drop_duplicates(subset=["DIRECTORIO", "SECUENCIA_P"], keep="first")
    eliminados = antes - len(df)
    if eliminados > 0:
        logger.info(f"  Deduplicación: {eliminados:,} registros eliminados")
    return df.reset_index(drop=True)


def _imputar_pago_energia(df: pd.DataFrame) -> pd.DataFrame:
    """
    Paso 2: Imputa nulos en P5018 (pago energía) con la mediana
    del estrato socioeconómico (P5010).
    """
    nulos_antes = df["P5018"].isna().sum()
    if nulos_antes == 0:
        return df

    medianas = df.groupby("P5010")["P5018"].transform("median")
    df["P5018"] = df["P5018"].fillna(medianas)

    # Si aún quedan nulos (estratos sin datos), usar mediana global
    mediana_global = df["P5018"].median()
    df["P5018"] = df["P5018"].fillna(mediana_global)

    logger.info(
        f"  Imputación: {nulos_antes:,} nulos en P5018 imputados "
        f"(mediana por estrato)"
    )
    return df


def _tratar_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Paso 3: Trunca (cap) valores de P5018 al percentil 99."""
    p99 = df["P5018"].quantile(0.99)
    outliers = (df["P5018"] > p99).sum()
    df["P5018"] = df["P5018"].clip(upper=p99)
    if outliers > 0:
        logger.info(
            f"  Outliers: {outliers:,} valores truncados al P99 "
            f"(${p99:,.0f} COP)"
        )
    return df


def _tratar_ceros(df: pd.DataFrame) -> pd.DataFrame:
    """
    Paso 4: Ceros en P5018 para estrato ≠ 1 se imputan con la
    mediana del estrato. Estrato 1 con $0 se considera válido
    (subsidio puede cubrir el 100 %).
    """
    mask_cero_invalido = (df["P5018"] == 0) & (df["P5010"] != 1)
    n_ceros = mask_cero_invalido.sum()
    if n_ceros > 0:
        medianas = df.groupby("P5010")["P5018"].transform("median")
        df.loc[mask_cero_invalido, "P5018"] = medianas[mask_cero_invalido]
        logger.info(
            f"  Ceros inválidos: {n_ceros:,} registros "
            f"(estrato ≠ 1) imputados con mediana"
        )
    return df


# =========================================================================
# CONSTRUCCIÓN DE DIMENSIONES
# =========================================================================

def _construir_dim_hogar(
    df_servicios: pd.DataFrame,
    df_personas: pd.DataFrame | None,
    df_condiciones: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Construye dim_hogar con:
      - sk_hogar, directorio, secuencia_p, num_personas, tiene_vehiculo
    """
    dim = df_servicios[["DIRECTORIO", "SECUENCIA_P"]].copy()

    # ── num_personas ────────────────────────────────────────────
    if df_personas is not None:
        conteo = (
            df_personas
            .groupby(["DIRECTORIO", "SECUENCIA_P"])
            .size()
            .reset_index(name="NUM_PERSONAS")
        )
        dim = dim.merge(conteo, on=["DIRECTORIO", "SECUENCIA_P"], how="left")
        dim["NUM_PERSONAS"] = dim["NUM_PERSONAS"].fillna(1).astype(int)
    else:
        dim["NUM_PERSONAS"] = 1
        logger.warning(
            "  Sin archivo Características: num_personas = 1 por defecto"
        )

    # ── tiene_vehiculo ──────────────────────────────────────────
    if df_condiciones is not None:
        col_vehiculo = _buscar_columna(df_condiciones, COLS_VEHICULO)
        if col_vehiculo:
            vehiculo = (
                df_condiciones[["DIRECTORIO", "SECUENCIA_P", col_vehiculo]]
                .drop_duplicates(subset=["DIRECTORIO", "SECUENCIA_P"])
                .copy()
            )
            vehiculo["TIENE_VEHICULO"] = vehiculo[col_vehiculo].map(
                {1: "Sí", 2: "No"}
            ).fillna("No")
            dim = dim.merge(
                vehiculo[["DIRECTORIO", "SECUENCIA_P", "TIENE_VEHICULO"]],
                on=["DIRECTORIO", "SECUENCIA_P"],
                how="left",
            )
            dim["TIENE_VEHICULO"] = dim["TIENE_VEHICULO"].fillna("No")
        else:
            dim["TIENE_VEHICULO"] = "No"
            logger.warning(
                "  Columna de vehículo no encontrada: "
                "tiene_vehiculo = 'No' por defecto"
            )
    else:
        dim["TIENE_VEHICULO"] = "No"
        logger.warning(
            "  Sin archivo Condiciones: tiene_vehiculo = 'No' por defecto"
        )

    # ── Surrogate key ───────────────────────────────────────────
    dim.insert(0, "SK_HOGAR", range(1, len(dim) + 1))

    dim = dim.rename(columns={
        "SK_HOGAR": "sk_hogar",
        "DIRECTORIO": "directorio",
        "SECUENCIA_P": "secuencia_p",
        "NUM_PERSONAS": "num_personas",
        "TIENE_VEHICULO": "tiene_vehiculo",
    })
    return dim


def _construir_dim_ubicacion(
    df_servicios: pd.DataFrame,
    df_vivienda: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Construye dim_ubicacion con:
      - sk_ubicacion, codigo_departamento, nombre_departamento, estrato
    Grano: combinación única de (departamento, estrato).
    """
    # Obtener estrato desde servicios
    base = df_servicios[["DIRECTORIO", "SECUENCIA_P", "P5010"]].copy()

    # Obtener código de departamento
    if df_vivienda is not None:
        col_depto = _buscar_columna(df_vivienda, COLS_DEPARTAMENTO)
        if col_depto:
            depto = (
                df_vivienda[["DIRECTORIO", "SECUENCIA_P", col_depto]]
                .drop_duplicates(subset=["DIRECTORIO", "SECUENCIA_P"])
            )
            base = base.merge(
                depto, on=["DIRECTORIO", "SECUENCIA_P"], how="left"
            )
            base.rename(columns={col_depto: "COD_DEPTO"}, inplace=True)
        else:
            base["COD_DEPTO"] = 0
            logger.warning(
                "  Columna de departamento no encontrada en Datos vivienda"
            )
    else:
        base["COD_DEPTO"] = 0
        logger.warning(
            "  Sin archivo Datos vivienda: departamento desconocido"
        )

    base["COD_DEPTO"] = pd.to_numeric(base["COD_DEPTO"], errors="coerce").fillna(0).astype(int)
    base["P5010"] = pd.to_numeric(base["P5010"], errors="coerce").fillna(1).astype(int)

    # Crear combinaciones únicas (departamento, estrato)
    ubicaciones = (
        base[["COD_DEPTO", "P5010"]]
        .drop_duplicates()
        .sort_values(["COD_DEPTO", "P5010"])
        .reset_index(drop=True)
    )
    ubicaciones.insert(0, "sk_ubicacion", range(1, len(ubicaciones) + 1))
    ubicaciones["nombre_departamento"] = ubicaciones["COD_DEPTO"].map(
        DEPARTAMENTOS_COLOMBIA
    ).fillna("Desconocido")

    ubicaciones = ubicaciones.rename(columns={
        "COD_DEPTO": "codigo_departamento",
        "P5010": "estrato",
    })

    # Guardar el mapeo para asignar FK a cada hogar
    ubicaciones._mapa_hogares = base[
        ["DIRECTORIO", "SECUENCIA_P", "COD_DEPTO", "P5010"]
    ].copy()

    return ubicaciones


def _construir_dim_combustibles(ref_combustibles: pd.DataFrame) -> pd.DataFrame:
    """Construye dim_combustibles desde el CSV de referencia."""
    dim = ref_combustibles[["id_combustible", "tipo_combustible",
                             "factor_emision_co2"]].copy()
    dim = dim.rename(columns={
        "id_combustible": "sk_combustible",
        "factor_emision_co2": "factor_emision_kg_tj",
    })
    return dim


def _construir_dim_tarifas(ref_tarifas: pd.DataFrame) -> pd.DataFrame:
    """Construye dim_tarifas desde el CSV de referencia."""
    dim = ref_tarifas.copy()

    # Columna "Estrato" → extraer número: "Estrato 1" → 1
    col_estrato = dim.columns[0]
    dim["estrato_aplica"] = (
        dim[col_estrato].astype(str).str.extract(r"(\d+)").astype(int)
    )

    # Columna de costo → manejar separador de miles colombiano ("1.150" → 1150)
    col_costo = [c for c in dim.columns if "Costo" in c or "costo" in c][0]
    dim["costo_promedio_kwh"] = (
        dim[col_costo]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    dim.insert(0, "sk_tarifa", range(1, len(dim) + 1))
    return dim[["sk_tarifa", "estrato_aplica", "costo_promedio_kwh"]]


# =========================================================================
# CÁLCULO DE EMISIONES
# =========================================================================

def _calcular_emisiones(
    df: pd.DataFrame,
    tarifa_lookup: dict[int, float],
    factor_electrico: float,
    factor_combustibles: dict[int, float],
) -> pd.DataFrame:
    """
    Calcula las métricas de huella de carbono para cada hogar:
      - kwh_consumidos_estimados (mensual)
      - emisiones_energia_kg     (anual)
      - emisiones_coccion_kg     (anual)
      - huella_total_anual_kg    (anual)
    """
    # ── 1. kWh estimados mensuales ──────────────────────────────
    df["TARIFA_KWH"] = df["P5010"].map(tarifa_lookup)
    # Fallback: si un estrato no tiene tarifa, usar la más baja
    tarifa_default = min(tarifa_lookup.values()) if tarifa_lookup else 460
    df["TARIFA_KWH"] = df["TARIFA_KWH"].fillna(tarifa_default)

    df["kwh_consumidos_estimados"] = (
        df["P5018"].astype(float) / df["TARIFA_KWH"]
    ).round(2)
    # Evitar kWh negativos o absurdos
    df["kwh_consumidos_estimados"] = df["kwh_consumidos_estimados"].clip(lower=0)

    # ── 2. Emisiones de energía eléctrica (anuales) ─────────────
    df["emisiones_energia_kg"] = (
        df["kwh_consumidos_estimados"] * 12 * factor_electrico
    ).round(4)

    # ── 3. Emisiones por cocción (anuales) ──────────────────────
    # Asegurar que P5030 exista
    if "P5030" not in df.columns:
        df["emisiones_coccion_kg"] = 0.0
        logger.warning("  Columna P5030 no encontrada: emisiones_coccion = 0")
    else:
        df["ID_COMBUSTIBLE"] = df["P5030"].map(MAPA_P5030_A_COMBUSTIBLE)

        # Obtener gasto mensual según tipo de combustible
        gasto_gas = df.get("P5046S1A1", pd.Series(0, index=df.index))
        gasto_glp = df.get("P5067", pd.Series(0, index=df.index))

        gasto_gas = pd.to_numeric(gasto_gas, errors="coerce").fillna(0)
        gasto_glp = pd.to_numeric(gasto_glp, errors="coerce").fillna(0)

        # Calcular consumo físico mensual y emisiones mensuales
        emisiones_mensuales = pd.Series(0.0, index=df.index)

        # Gas Natural (P5030=2 → id_combustible=3)
        mask_gas = df["ID_COMBUSTIBLE"] == 3
        if mask_gas.any():
            factor_gas = factor_combustibles.get(3, 56100)
            m3_mes = gasto_gas[mask_gas] / PRECIO_GAS_NATURAL_M3
            tj_mes = m3_mes * NCV_GAS_NATURAL_MJ_M3 / MJ_POR_TJ
            emisiones_mensuales[mask_gas] = tj_mes * factor_gas

        # GLP / Propano (P5030=3 → id_combustible=2)
        mask_glp = df["ID_COMBUSTIBLE"] == 2
        if mask_glp.any():
            factor_glp = factor_combustibles.get(2, 63100)
            kg_mes = gasto_glp[mask_glp] / PRECIO_GLP_KG
            tj_mes = kg_mes * NCV_GLP_MJ_KG / MJ_POR_TJ
            emisiones_mensuales[mask_glp] = tj_mes * factor_glp

        # Leña / Biomasa (P5030=4 → id_combustible=1)
        mask_lena = df["ID_COMBUSTIBLE"] == 1
        if mask_lena.any():
            factor_lena = factor_combustibles.get(1, 112000)
            tj_mes = CONSUMO_LENA_KG_MES * NCV_LENA_MJ_KG / MJ_POR_TJ
            emisiones_mensuales[mask_lena] = tj_mes * factor_lena

        df["emisiones_coccion_kg"] = (emisiones_mensuales * 12).round(4)

    # ── 4. Huella total anual ───────────────────────────────────
    df["huella_total_anual_kg"] = (
        df["emisiones_energia_kg"] + df["emisiones_coccion_kg"]
    ).round(4)

    return df


# =========================================================================
# FUNCIÓN PRINCIPAL DE TRANSFORMACIÓN
# =========================================================================

def transformar(
    ecv_data: dict[str, pd.DataFrame],
    ref_data: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """
    Ejecuta la transformación completa:
      1. Limpieza y preparación de datos ECV
      2. Cálculo de huella de carbono
      3. Construcción de las tablas del modelo estrella

    Parameters
    ----------
    ecv_data : dict
        DataFrames crudos de la ECV (extract.extraer_datos_ecv()).
    ref_data : dict
        DataFrames de referencia (extract.extraer_dimensiones_referencia()).

    Returns
    -------
    dict[str, pd.DataFrame]
        Tablas listas para cargar: 'dim_hogar', 'dim_ubicacion',
        'dim_combustibles', 'dim_tarifas', 'fact_huella_carbono'.
    """
    logger.info("=" * 60)
    logger.info("TRANSFORMACIÓN — Limpieza y cálculo de emisiones")
    logger.info("=" * 60)

    # ── Obtener DataFrames ──────────────────────────────────────
    df_servicios = ecv_data.get("servicios")
    if df_servicios is None:
        raise ValueError(
            "El archivo de Servicios del hogar es obligatorio para el ETL."
        )

    df_servicios = _normalizar_columnas(df_servicios.copy())
    df_vivienda = ecv_data.get("datos_vivienda")
    df_personas = ecv_data.get("caracteristicas")
    df_condiciones = ecv_data.get("condiciones")

    if df_vivienda is not None:
        df_vivienda = _normalizar_columnas(df_vivienda.copy())
    if df_personas is not None:
        df_personas = _normalizar_columnas(df_personas.copy())
    if df_condiciones is not None:
        df_condiciones = _normalizar_columnas(df_condiciones.copy())

    # ── Verificar columnas mínimas ──────────────────────────────
    for col in ["DIRECTORIO", "SECUENCIA_P", "P5010", "P5018"]:
        if col not in df_servicios.columns:
            raise KeyError(
                f"Columna obligatoria '{col}' no encontrada en Servicios. "
                f"Columnas disponibles: {list(df_servicios.columns[:20])}"
            )

    # Convertir columnas numéricas
    df_servicios["P5018"] = pd.to_numeric(
        df_servicios["P5018"], errors="coerce"
    )
    df_servicios["P5010"] = pd.to_numeric(
        df_servicios["P5010"], errors="coerce"
    ).fillna(1).astype(int)

    # ── Aplicar reglas de limpieza ──────────────────────────────
    logger.info("  Aplicando reglas de limpieza (Data Cleansing)...")
    df_servicios = _deduplicar(df_servicios)
    df_servicios = _imputar_pago_energia(df_servicios)
    df_servicios = _tratar_outliers(df_servicios)
    df_servicios = _tratar_ceros(df_servicios)

    logger.info(f"  Registros limpios: {len(df_servicios):,}")

    # ── Construir dimensiones ───────────────────────────────────
    logger.info("-" * 60)
    logger.info("  Construyendo dimensiones del modelo estrella...")

    dim_hogar = _construir_dim_hogar(df_servicios, df_personas, df_condiciones)
    dim_ubicacion = _construir_dim_ubicacion(df_servicios, df_vivienda)
    dim_combustibles = _construir_dim_combustibles(ref_data["combustibles"])
    dim_tarifas = _construir_dim_tarifas(ref_data["tarifas"])

    logger.info(f"    dim_hogar:        {len(dim_hogar):,} registros")
    logger.info(f"    dim_ubicacion:    {len(dim_ubicacion):,} registros")
    logger.info(f"    dim_combustibles: {len(dim_combustibles):,} registros")
    logger.info(f"    dim_tarifas:      {len(dim_tarifas):,} registros")

    # ── Preparar lookups para cálculos ──────────────────────────
    tarifa_lookup = dict(zip(
        dim_tarifas["estrato_aplica"], dim_tarifas["costo_promedio_kwh"]
    ))

    factor_electrico = FACTOR_ELECTRICO_DEFAULT
    if "factor_electrico" in ref_data:
        fe = ref_data["factor_electrico"]
        col_factor = [c for c in fe.columns if "factor" in c.lower()]
        if col_factor:
            factor_electrico = float(fe[col_factor[0]].iloc[0])
    logger.info(f"    Factor eléctrico: {factor_electrico} kg CO₂/kWh")

    factor_combustibles = dict(zip(
        dim_combustibles["sk_combustible"],
        dim_combustibles["factor_emision_kg_tj"],
    ))

    # ── Calcular emisiones ──────────────────────────────────────
    logger.info("-" * 60)
    logger.info("  Calculando huella de carbono por hogar...")
    df_servicios = _calcular_emisiones(
        df_servicios, tarifa_lookup, factor_electrico, factor_combustibles
    )

    # ── Construir tabla de hechos ───────────────────────────────
    logger.info("  Construyendo tabla de hechos (fact_huella_carbono)...")

    # Mapear FK del hogar
    hogar_map = dict(zip(
        zip(dim_hogar["directorio"], dim_hogar["secuencia_p"]),
        dim_hogar["sk_hogar"],
    ))
    df_servicios["fk_hogar"] = list(zip(
        df_servicios["DIRECTORIO"], df_servicios["SECUENCIA_P"]
    ))
    df_servicios["fk_hogar"] = df_servicios["fk_hogar"].map(hogar_map)

    # Mapear FK de ubicación
    mapa_ubi = dim_ubicacion._mapa_hogares if hasattr(
        dim_ubicacion, "_mapa_hogares"
    ) else None

    if mapa_ubi is not None:
        # Crear lookup (cod_depto, estrato) → sk_ubicacion
        ubi_lookup = dict(zip(
            zip(dim_ubicacion["codigo_departamento"], dim_ubicacion["estrato"]),
            dim_ubicacion["sk_ubicacion"],
        ))
        # Asignar código de departamento a servicios
        merge_ubi = mapa_ubi.rename(columns={
            "COD_DEPTO": "depto_temp", "P5010": "estrato_temp"
        })
        df_servicios = df_servicios.merge(
            merge_ubi[["DIRECTORIO", "SECUENCIA_P", "depto_temp", "estrato_temp"]],
            on=["DIRECTORIO", "SECUENCIA_P"],
            how="left",
        )
        df_servicios["fk_ubicacion"] = list(zip(
            df_servicios["depto_temp"], df_servicios["estrato_temp"]
        ))
        df_servicios["fk_ubicacion"] = df_servicios["fk_ubicacion"].map(
            ubi_lookup
        )
    else:
        df_servicios["fk_ubicacion"] = 1

    # Mapear FK de combustible
    df_servicios["fk_combustible_cocina"] = df_servicios.get(
        "ID_COMBUSTIBLE", pd.Series(dtype="float64")
    )

    # Mapear FK de tarifa
    tarifa_sk = dict(zip(
        dim_tarifas["estrato_aplica"], dim_tarifas["sk_tarifa"]
    ))
    df_servicios["fk_tarifa_energia"] = df_servicios["P5010"].map(tarifa_sk)

    # Ensamblar fact table
    fact = df_servicios[[
        "fk_hogar",
        "fk_ubicacion",
        "fk_combustible_cocina",
        "fk_tarifa_energia",
        "kwh_consumidos_estimados",
        "emisiones_energia_kg",
        "emisiones_coccion_kg",
        "huella_total_anual_kg",
    ]].copy()
    fact.insert(0, "sk_fact", range(1, len(fact) + 1))

    # Convertir FKs a entero nullable
    for fk_col in ["fk_hogar", "fk_ubicacion", "fk_combustible_cocina",
                    "fk_tarifa_energia"]:
        fact[fk_col] = pd.to_numeric(fact[fk_col], errors="coerce")
        fact[fk_col] = fact[fk_col].astype("Int64")  # nullable int

    logger.info(f"    fact_huella_carbono: {len(fact):,} registros")

    # ── Resumen de métricas calculadas ──────────────────────────
    logger.info("-" * 60)
    logger.info("  Resumen de métricas:")
    logger.info(
        f"    kWh mensual promedio:        "
        f"{fact['kwh_consumidos_estimados'].mean():.1f} kWh"
    )
    logger.info(
        f"    Emisiones eléctricas (anual): "
        f"{fact['emisiones_energia_kg'].mean():.1f} kg CO₂"
    )
    logger.info(
        f"    Emisiones cocción (anual):    "
        f"{fact['emisiones_coccion_kg'].mean():.1f} kg CO₂"
    )
    logger.info(
        f"    Huella total (anual):         "
        f"{fact['huella_total_anual_kg'].mean():.1f} kg CO₂"
    )

    return {
        "dim_hogar": dim_hogar,
        "dim_ubicacion": dim_ubicacion[
            ["sk_ubicacion", "codigo_departamento",
             "nombre_departamento", "estrato"]
        ],
        "dim_combustibles": dim_combustibles,
        "dim_tarifas": dim_tarifas,
        "fact_huella_carbono": fact,
    }
