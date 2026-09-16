"""
==========================================================================
Módulo de Carga (L) — ETL Huella de Carbono
==========================================================================
Carga las tablas del modelo estrella en la base de datos destino usando
SQLAlchemy.  Soporta MySQL, PostgreSQL y SQLite.

Configuración (archivo .env en la raíz del proyecto):
  DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/huella_carbono_dw

  ó variables individuales:
    DB_ENGINE=mysql       (mysql | postgresql | sqlite)
    DB_HOST=localhost
    DB_PORT=3306
    DB_USER=root
    DB_PASSWORD=
    DB_NAME=huella_carbono_dw

Si no existe .env, se usa SQLite por defecto en data/huella_carbono_dw.db.
==========================================================================
"""

import os
import pandas as pd
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Orden de carga: dimensiones primero, hechos al final ─────────────────
ORDEN_TABLAS = [
    "dim_hogar",
    "dim_ubicacion",
    "dim_combustibles",
    "dim_tarifas",
    "fact_huella_carbono",
]


# =========================================================================
# CONEXIÓN A BASE DE DATOS
# =========================================================================

def crear_engine():
    """
    Crea un engine de SQLAlchemy a partir de la configuración del entorno.

    Prioridad:
      1. DATABASE_URL (string completo de conexión)
      2. Variables individuales DB_ENGINE, DB_HOST, etc.
      3. SQLite local en data/huella_carbono_dw.db
    """
    url = os.getenv("DATABASE_URL")

    if url:
        logger.info(f"  Conexión: {_ocultar_password(url)}")
        return create_engine(url, echo=False)

    motor = os.getenv("DB_ENGINE", "sqlite").lower()
    nombre_db = os.getenv("DB_NAME", "huella_carbono_dw")

    if motor == "sqlite":
        ruta_db = os.path.join(BASE_DIR, "data", f"{nombre_db}.db")
        url = f"sqlite:///{ruta_db}"
        logger.info(f"  Conexión SQLite: {ruta_db}")
        return create_engine(url, echo=False)

    host = os.getenv("DB_HOST", "localhost")
    puerto = os.getenv("DB_PORT", "3306" if motor == "mysql" else "5432")
    usuario = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")

    if motor == "mysql":
        driver = "mysql+pymysql"
    elif motor in ("postgresql", "postgres"):
        driver = "postgresql+psycopg2"
    else:
        raise ValueError(
            f"Motor de BD no soportado: '{motor}'. "
            "Use 'mysql', 'postgresql' o 'sqlite'."
        )

    url = f"{driver}://{usuario}:{password}@{host}:{puerto}/{nombre_db}"
    logger.info(f"  Conexión: {_ocultar_password(url)}")
    return create_engine(url, echo=False)


def _ocultar_password(url: str) -> str:
    """Enmascara la contraseña en la URL de conexión para el log."""
    import re
    return re.sub(r"(?<=:)[^:@]+(?=@)", "***", url)


# =========================================================================
# EJECUCIÓN DEL DDL
# =========================================================================

def ejecutar_ddl(engine) -> None:
    """
    Lee y ejecuta sql/create_dw.sql para crear (o recrear) las tablas
    del Data Warehouse.
    """
    ruta_ddl = os.path.join(BASE_DIR, "sql", "create_dw.sql")

    if not os.path.exists(ruta_ddl):
        raise FileNotFoundError(f"Archivo DDL no encontrado: {ruta_ddl}")

    with open(ruta_ddl, "r", encoding="utf-8") as f:
        ddl_script = f.read()

    # Separar sentencias por ';' y ejecutar una a una
    sentencias = [s.strip() for s in ddl_script.split(";") if s.strip()]

    with engine.begin() as conn:
        for sentencia in sentencias:
            # Ignorar comentarios sueltos
            lineas = [
                l for l in sentencia.split("\n")
                if l.strip() and not l.strip().startswith("--")
            ]
            if lineas:
                conn.execute(text(sentencia))

    logger.info("  DDL ejecutado: tablas del DW creadas correctamente")


# =========================================================================
# CARGA DE DATOS
# =========================================================================

def cargar_dimensiones_y_hechos(
    engine,
    tablas: dict[str, pd.DataFrame],
) -> None:
    """
    Carga las tablas del modelo estrella en la base de datos.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        Engine de conexión a la BD.
    tablas : dict[str, pd.DataFrame]
        Diccionario con las tablas a cargar (resultado de transform.transformar()).
    """
    for nombre in ORDEN_TABLAS:
        if nombre not in tablas:
            logger.warning(f"  Tabla '{nombre}' no encontrada, se omite")
            continue

        df = tablas[nombre]
        try:
            df.to_sql(
                name=nombre,
                con=engine,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
            logger.info(f"  ✓ {nombre}: {len(df):,} registros cargados")
        except Exception as e:
            logger.error(f"  ✗ Error cargando '{nombre}': {e}")
            raise


# =========================================================================
# EXPORTAR CSVs PROCESADOS (respaldo)
# =========================================================================

def exportar_csvs(tablas: dict[str, pd.DataFrame]) -> None:
    """
    Exporta las tablas transformadas como CSV en data/processed/
    como respaldo y para validación.
    """
    processed_dir = os.path.join(BASE_DIR, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)

    for nombre, df in tablas.items():
        ruta = os.path.join(processed_dir, f"{nombre}.csv")
        df.to_csv(ruta, index=False, encoding="utf-8")
        logger.info(f"  📄 {nombre}.csv exportado ({len(df):,} filas)")


# =========================================================================
# FUNCIÓN PRINCIPAL DE CARGA
# =========================================================================

def cargar(tablas: dict[str, pd.DataFrame]) -> None:
    """
    Orquesta la fase de carga completa:
      1. Crear engine de conexión
      2. Ejecutar DDL (crear/recrear tablas)
      3. Insertar datos en dimensiones y tabla de hechos
      4. Exportar respaldo en CSV
    """
    logger.info("=" * 60)
    logger.info("CARGA — Base de datos y archivos CSV")
    logger.info("=" * 60)

    # ── Siempre exportar CSVs (no requiere BD) ──────────────────
    logger.info("  Exportando CSVs procesados a data/processed/...")
    exportar_csvs(tablas)

    # ── Intentar carga a base de datos ──────────────────────────
    try:
        logger.info("-" * 60)
        logger.info("  Conectando a la base de datos...")
        engine = crear_engine()

        logger.info("  Ejecutando DDL (create_dw.sql)...")
        ejecutar_ddl(engine)

        logger.info("  Cargando tablas del modelo estrella...")
        cargar_dimensiones_y_hechos(engine, tablas)

        logger.info("-" * 60)
        logger.info("  ✓ Carga a base de datos completada exitosamente")

    except Exception as e:
        logger.error(f"  ✗ Error en la carga a BD: {e}")
        logger.info(
            "  Los CSVs procesados se exportaron correctamente en "
            "data/processed/ y pueden importarse manualmente."
        )
        raise
