"""
==========================================================================
Módulo de Validación (V) — ETL Huella de Carbono
==========================================================================
Verifica la calidad e integridad del modelo estrella ANTES de cargarlo
a la base de datos:

  1. Conteos de filas (reconciliación con la fuente)
  2. Nulos críticos en llaves y medidas
  3. Unicidad de las llaves subrogadas (PK) de cada dimensión
  4. Integridad referencial (cada FK del hecho existe en su dimensión)
  5. Rangos y reglas de negocio (valores negativos, absurdos, etc.)

Si se detecta un problema CRÍTICO, se lanza ValidationError y el
pipeline se detiene antes de cargar datos corruptos a la base de datos.
==========================================================================
"""

import logging

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Error crítico de validación que detiene el pipeline."""
    pass


# =========================================================================
# 1. CONTEOS Y RECONCILIACIÓN CON LA FUENTE
# =========================================================================

def validar_conteos(tablas: dict, filas_fuente_originales: int) -> None:
    """
    Compara el número de filas del hecho contra la fuente original,
    permitiendo la pérdida esperada por deduplicación.
    """
    n_fact = len(tablas["fact_huella_carbono"])
    n_hogar = len(tablas["dim_hogar"])

    if n_fact != n_hogar:
        raise ValidationError(
            f"El conteo de fact_huella_carbono ({n_fact:,}) no coincide "
            f"con dim_hogar ({n_hogar:,}). El grano se rompió en algún paso."
        )

    if n_fact > filas_fuente_originales:
        raise ValidationError(
            f"fact_huella_carbono tiene MÁS filas ({n_fact:,}) que la "
            f"fuente original ({filas_fuente_originales:,}). Algo duplicó datos."
        )

    perdida_pct = 100 * (filas_fuente_originales - n_fact) / filas_fuente_originales
    logger.info(
        f"  Conteos OK: {n_fact:,} hogares en el DW vs. "
        f"{filas_fuente_originales:,} en la fuente "
        f"({perdida_pct:.1f}% removido en deduplicación)"
    )


# =========================================================================
# 2. NULOS CRÍTICOS
# =========================================================================

def validar_nulos_criticos(tablas: dict) -> None:
    """Verifica que las llaves y medidas críticas no tengan nulos."""
    fact = tablas["fact_huella_carbono"]

    columnas_criticas = [
        "sk_fact", "fk_hogar", "fk_ubicacion",
        "huella_total_anual_kg",
    ]
    for col in columnas_criticas:
        nulos = fact[col].isna().sum()
        if nulos > 0:
            raise ValidationError(
                f"'{col}' en fact_huella_carbono tiene {nulos:,} valores "
                "nulos. Esta columna es obligatoria."
            )

    logger.info(
        "  Nulos críticos OK: sk_fact, fk_hogar, fk_ubicacion, "
        "huella_total_anual_kg sin nulos"
    )


# =========================================================================
# 3. UNICIDAD DE LLAVES PRIMARIAS
# =========================================================================

def validar_unicidad(tablas: dict) -> None:
    """Verifica que cada surrogate key (PK) de dimensión sea única."""
    llaves_pk = {
        "dim_hogar": "sk_hogar",
        "dim_ubicacion": "sk_ubicacion",
        "dim_combustibles": "sk_combustible",
        "dim_tarifas": "sk_tarifa",
        "fact_huella_carbono": "sk_fact",
    }

    for tabla, pk in llaves_pk.items():
        df = tablas[tabla]
        duplicados = df[pk].duplicated().sum()
        if duplicados > 0:
            raise ValidationError(
                f"La llave primaria '{pk}' en '{tabla}' tiene "
                f"{duplicados:,} valores duplicados."
            )

    logger.info("  Unicidad OK: todas las llaves primarias (sk_*) son únicas")


# =========================================================================
# 4. INTEGRIDAD REFERENCIAL
# =========================================================================

def validar_integridad_referencial(tablas: dict) -> None:
    """
    Verifica que cada FK en fact_huella_carbono exista en su
    tabla de dimensión correspondiente (simula el constraint FK de SQL).
    """
    fact = tablas["fact_huella_carbono"]

    relaciones = [
        ("fk_hogar", "dim_hogar", "sk_hogar"),
        ("fk_ubicacion", "dim_ubicacion", "sk_ubicacion"),
        ("fk_combustible_cocina", "dim_combustibles", "sk_combustible"),
        ("fk_tarifa_energia", "dim_tarifas", "sk_tarifa"),
    ]

    for fk_col, dim_tabla, pk_col in relaciones:
        pks_validas = set(tablas[dim_tabla][pk_col])
        fks = fact[fk_col].dropna()
        huerfanos = ~fks.isin(pks_validas)
        n_huerfanos = huerfanos.sum()

        if n_huerfanos > 0:
            raise ValidationError(
                f"'{fk_col}' tiene {n_huerfanos:,} registros huérfanos "
                f"(no existen en '{dim_tabla}.{pk_col}')."
            )

    logger.info(
        "  Integridad referencial OK: todas las FK del hecho "
        "existen en su dimensión"
    )


# =========================================================================
# 5. RANGOS Y REGLAS DE NEGOCIO
# =========================================================================

def validar_rangos(tablas: dict) -> None:
    """Verifica que las medidas no tengan valores negativos o absurdos."""
    fact = tablas["fact_huella_carbono"]

    medidas_no_negativas = [
        "kwh_consumidos_estimados",
        "emisiones_energia_kg",
        "emisiones_coccion_kg",
        "huella_total_anual_kg",
    ]

    for col in medidas_no_negativas:
        negativos = (fact[col] < 0).sum()
        if negativos > 0:
            raise ValidationError(
                f"'{col}' tiene {negativos:,} valores negativos, lo cual "
                "no tiene sentido físico para una medida de consumo/emisión."
            )

    # Regla de negocio: la huella total debe ser la suma de sus componentes
    diferencia = (
        fact["huella_total_anual_kg"]
        - (fact["emisiones_energia_kg"] + fact["emisiones_coccion_kg"])
    ).abs()
    inconsistentes = (diferencia > 0.01).sum()
    if inconsistentes > 0:
        raise ValidationError(
            f"{inconsistentes:,} registros donde huella_total_anual_kg no "
            "es la suma de emisiones_energia_kg + emisiones_coccion_kg."
        )

    logger.info(
        "  Rangos OK: sin valores negativos; huella_total = energía + "
        "cocción en todos los registros"
    )


# =========================================================================
# ORQUESTADOR
# =========================================================================

def validar(tablas: dict, filas_fuente_originales: int) -> None:
    """
    Ejecuta todas las validaciones en orden. Si alguna falla,
    lanza ValidationError y detiene el pipeline antes de la carga.
    """
    logger.info("=" * 60)
    logger.info("VALIDACIÓN — Integridad del modelo estrella")
    logger.info("=" * 60)

    validar_conteos(tablas, filas_fuente_originales)
    validar_nulos_criticos(tablas)
    validar_unicidad(tablas)
    validar_integridad_referencial(tablas)
    validar_rangos(tablas)

    logger.info("  ✅ Todas las validaciones pasaron correctamente")