"""
==========================================================================
Módulo de Extracción (E) — ETL Huella de Carbono
==========================================================================
Lee los microdatos de la Encuesta de Calidad de Vida (ECV) del DANE y las
tablas de referencia (combustibles, factor eléctrico, tarifas) almacenados
como CSV en data/raw/.

Archivos ECV esperados (descargados de https://microdatos.dane.gov.co/):
    ├── Servicios*.csv        ← Servicios del hogar
    ├── Datos*.csv            ← Datos de la vivienda
    ├── Características*.csv  ← Características generales (personas)
    └── Condiciones*.csv      ← Condiciones de vida (bienes del hogar)

Archivos de referencia (incluidos en el repositorio):
    ├── dim_combustibles.csv
    ├── dim_factor_electrico.csv
    └── dim_tarifas.csv
==========================================================================
"""

import os
import glob
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Rutas base ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")


# ── Utilidades internas ─────────────────────────────────────────────────
def _buscar_csv(patron: str) -> str | None:
    """Busca un CSV en data/raw/ que coincida con un patrón glob."""
    resultados = glob.glob(os.path.join(RAW_DIR, patron))
    if resultados:
        logger.info(f"  Archivo encontrado: {os.path.basename(resultados[0])}")
        return resultados[0]
    return None


def _leer_csv_auto(ruta: str) -> pd.DataFrame:
    """
    Lee un CSV detectando automáticamente el separador (`,` o `;`)
    y la codificación (`utf-8` o `latin-1`).
    """
    for encoding in ("utf-8", "latin-1"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(
                    ruta, sep=sep, encoding=encoding, low_memory=False
                )
                # Si solo quedó 1 columna, el separador probablemente fue incorrecto
                if df.shape[1] > 1:
                    return df
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue

    # Último intento: dejar que Pandas infiera
    return pd.read_csv(ruta, encoding="latin-1", sep=None, engine="python",
                       low_memory=False)


# ── Funciones públicas ──────────────────────────────────────────────────
def extraer_datos_ecv() -> dict[str, pd.DataFrame]:
    """
    Extrae los microdatos de la ECV desde data/raw/.

    Returns
    -------
    dict[str, pd.DataFrame]
        Claves posibles: 'servicios', 'datos_vivienda',
        'caracteristicas', 'condiciones'.
    """
    logger.info("=" * 60)
    logger.info("EXTRACCIÓN — Microdatos ECV (DANE)")
    logger.info("=" * 60)

    patrones = {
        "servicios":       "Servicios*.csv",
        "datos_vivienda":  "Datos*.csv",
        "caracteristicas": "Caracter*sticas*.csv",   # cubre con/sin tilde
        "condiciones":     "Condiciones*.csv",
    }

    resultado: dict[str, pd.DataFrame] = {}

    for nombre, patron in patrones.items():
        ruta = _buscar_csv(patron)
        if ruta:
            df = _leer_csv_auto(ruta)
            logger.info(
                f"  [{nombre}] {df.shape[0]:,} filas × {df.shape[1]} columnas"
            )
            resultado[nombre] = df
        else:
            logger.warning(
                f"  [{nombre}] No se encontró archivo con patrón '{patron}'"
            )

    if not resultado:
        raise FileNotFoundError(
            f"No se encontraron microdatos de la ECV en:\n  {RAW_DIR}\n"
            "Descarga los archivos CSV de https://microdatos.dane.gov.co/ "
            "y colócalos en data/raw/"
        )

    return resultado


def extraer_dimensiones_referencia() -> dict[str, pd.DataFrame]:
    """
    Extrae las tablas de referencia (dimensiones estáticas) desde data/raw/.

    Returns
    -------
    dict[str, pd.DataFrame]
        Claves: 'combustibles', 'factor_electrico', 'tarifas'.
    """
    logger.info("-" * 60)
    logger.info("EXTRACCIÓN — Dimensiones de referencia")
    logger.info("-" * 60)

    archivos = {
        "combustibles":     "dim_combustibles.csv",
        "factor_electrico": "dim_factor_electrico.csv",
        "tarifas":          "dim_tarifas.csv",
    }

    resultado: dict[str, pd.DataFrame] = {}

    for nombre, archivo in archivos.items():
        ruta = os.path.join(RAW_DIR, archivo)
        if os.path.exists(ruta):
            df = _leer_csv_auto(ruta)
            logger.info(f"  [{nombre}] {df.shape[0]} registros cargados")
            resultado[nombre] = df
        else:
            logger.warning(f"  [{nombre}] Archivo '{archivo}' no encontrado")

    return resultado
