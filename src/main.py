"""
==========================================================================
Pipeline ETL — Huella de Carbono de Hogares Colombianos
==========================================================================
Orquestador principal que ejecuta secuencialmente:

    1. EXTRACCIÓN  → Lectura de microdatos ECV (DANE) y tablas de referencia
    2. TRANSFORMACIÓN → Limpieza, cálculo de emisiones, modelo estrella
    3. VALIDACIÓN → Verificación de integridad antes de cargar
    4. CARGA → Exportar CSVs + insertar en base de datos

Uso:
    python src/main.py

Requisitos:
    - Microdatos de la ECV en data/raw/ (Servicios*.csv, Datos*.csv, etc.)
    - Archivo .env con configuración de BD (opcional, default: SQLite)
==========================================================================
"""

import os
import sys
import time
import logging
from dotenv import load_dotenv

# ── Agregar directorio src/ al path para imports locales ─────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract import extraer_datos_ecv, extraer_dimensiones_referencia
from transform import transformar
from validate import validar, ValidationError
from load import cargar


# =========================================================================
# CONFIGURACIÓN DE LOGGING
# =========================================================================

def _configurar_logging() -> None:
    """Configura el sistema de logging con salida a consola y archivo."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base_dir, "data")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "etl_pipeline.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(levelname)-8s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8", mode="w"),
        ],
    )


# =========================================================================
# PIPELINE PRINCIPAL
# =========================================================================

def ejecutar_pipeline() -> None:
    """Ejecuta el pipeline ETL completo: Extract → Transform → Validate → Load."""
    _configurar_logging()
    logger = logging.getLogger(__name__)

    # ── Cargar variables de entorno ─────────────────────────────
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info("Archivo .env cargado")
    else:
        logger.info(
            "No se encontró .env — se usará SQLite por defecto "
            "(data/huella_carbono_dw.db)"
        )

    inicio = time.time()

    logger.info("╔" + "═" * 58 + "╗")
    logger.info("║  ETL — HUELLA DE CARBONO DE HOGARES COLOMBIANOS (ODS 12) ║")
    logger.info("╚" + "═" * 58 + "╝")

    try:
        # ── FASE 1: EXTRACCIÓN ──────────────────────────────────
        t1 = time.time()
        ecv_data = extraer_datos_ecv()
        ref_data = extraer_dimensiones_referencia()
        logger.info(f"  ⏱  Extracción completada en {time.time() - t1:.1f}s")

        # ── FASE 2: TRANSFORMACIÓN ──────────────────────────────
        t2 = time.time()
        filas_fuente = len(ecv_data["servicios"])
        tablas = transformar(ecv_data, ref_data)
        logger.info(f"  ⏱  Transformación completada en {time.time() - t2:.1f}s")

        # ── FASE 2.5: VALIDACIÓN ─────────────────────────────────
        t2b = time.time()
        validar(tablas, filas_fuente)
        logger.info(f"  ⏱  Validación completada en {time.time() - t2b:.1f}s")

        # ── FASE 3: CARGA ───────────────────────────────────────
        t3 = time.time()
        cargar(tablas)
        logger.info(f"  ⏱  Carga completada en {time.time() - t3:.1f}s")

        # ── RESUMEN FINAL ───────────────────────────────────────
        total = time.time() - inicio
        logger.info("=" * 60)
        logger.info("  ✅ PIPELINE ETL EJECUTADO EXITOSAMENTE")
        logger.info(f"  ⏱  Tiempo total: {total:.1f} segundos")
        logger.info("=" * 60)

        # Imprimir conteo de registros por tabla
        logger.info("  Registros cargados:")
        for nombre, df in tablas.items():
            logger.info(f"    {nombre:.<35s} {len(df):>8,} filas")

    except FileNotFoundError as e:
        logger.error(f"\n❌ ARCHIVO NO ENCONTRADO:\n   {e}")
        logger.info(
            "\n💡 Asegúrate de que los microdatos de la ECV estén en "
            "data/raw/"
        )
        sys.exit(1)

    except ValidationError as e:
        logger.error(
            f"\n❌ VALIDACIÓN FALLIDA — el pipeline se detuvo antes de "
            f"cargar a la BD:\n   {e}"
        )
        sys.exit(1)

    except KeyError as e:
        logger.error(f"\n❌ COLUMNA FALTANTE EN LOS DATOS:\n   {e}")
        logger.info(
            "\n💡 Verifica que los archivos CSV tengan las columnas "
            "esperadas de la ECV (DANE)."
        )
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n❌ ERROR INESPERADO:\n   {type(e).__name__}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)


# =========================================================================
# PUNTO DE ENTRADA
# =========================================================================

if __name__ == "__main__":
    ejecutar_pipeline()