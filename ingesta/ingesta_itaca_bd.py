import os
import re
import json
import hashlib
import logging
from datetime import date
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingesta_itaca_bd")

# Solo se extraen las columnas del modelo (minimización de datos): la tabla
# alumnos contiene nombre, documento, teléfonos, email... que no se necesitan.
# "contenidos" es la tabla Modulos del modelo de datos.
# La tabla Horas no existe todavía en la BD de origen.
CONSULTAS = {
    "alumnos": """
        SELECT anyo AS "Anyo", nia AS "NIA", curso AS "Curso",
               turno AS "Turno", grupo AS "Grupo"
        FROM alumnos
    """,
    "contenidos": """
        SELECT anyo AS "Anyo", curso AS "Curso", codigo AS "Modulo",
               nombre_cas AS "Nombre_Modulo"
        FROM contenidos
    """,
    "calificaciones": """
        SELECT anyo AS "Anyo", alumno AS "NIA", curso AS "Curso",
               contenido AS "Modulo", nota_numerica AS "Nota",
               evaluacion AS "Evaluacion"
        FROM calificaciones
    """,
    "cursos": """
        SELECT anyo AS "Anyo", codigo AS "Codigo", nombre_cas AS "Nombre_Cas",
               padre AS "Padre"
        FROM cursos
    """,
    "grupos": """
        SELECT anyo AS "Anyo", codigo AS "Grupo", nombre AS "Nombre",
               turno AS "Turno", modalidad AS "Modalidad", aula AS "Aula",
               capacidad AS "Capacidad"
        FROM grupos
    """,
}

# Tablas que contienen (o referencian) el NIA y deben anonimizarse
TABLAS_CON_NIA = {"alumnos", "calificaciones"}

# NIA original -> NIA anonimizado. Se calcula una sola vez por NIA y se
# reutiliza en todas las tablas para que Alumnos y Calificaciones crucen.
_nias_anonimos: dict[str, str] = {}


def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def extraer_tabla(conexion, tabla: str) -> list[dict]:
    with conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(CONSULTAS[tabla])
        return [dict(fila) for fila in cur.fetchall()]


def anonimizar_nia(nia: str) -> str:
    nia = str(nia).strip()
    if nia not in _nias_anonimos:
        _nias_anonimos[nia] = hashlib.sha256(nia.encode()).hexdigest()[:10]
    return _nias_anonimos[nia]


def anonimizar(datos: list[dict]) -> list[dict]:
    for fila in datos:
        if fila.get("NIA") is not None:
            fila["NIA"] = anonimizar_nia(fila["NIA"])
    return datos


def guardar(datos: list[dict], nombre: str) -> None:
    fecha = date.today().isoformat()
    ruta = f"data/raw/{nombre}_{fecha}.json"
    os.makedirs("data/raw", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2, default=str)
    logger.info("Guardados %d registros en %s", len(datos), ruta)


def claves(datos: list[dict], *campos: str) -> set[tuple]:
    return {tuple(str(fila[c]).strip() for c in campos) for fila in datos}


def validar(tablas: dict[str, list[dict]]) -> None:
    """Comprobaciones del paso 5 sobre los datos que se van a guardar."""
    alumnos, calificaciones = tablas["alumnos"], tablas["calificaciones"]

    # Ningún NIA en claro: todos deben ser hashes de 10 caracteres hex
    hash_valido = re.compile(r"^[0-9a-f]{10}$")
    en_claro = [f for f in alumnos + calificaciones if not hash_valido.match(f["NIA"])]
    logger.info("NIA sin anonimizar: %d", len(en_claro))

    comprobaciones = [
        ("Modulo de Calificaciones en Contenidos (Modulo+Anyo+Curso)",
         claves(calificaciones, "Modulo", "Anyo", "Curso"),
         claves(tablas["contenidos"], "Modulo", "Anyo", "Curso")),
        ("Grupo de Alumnos en Grupos (Grupo+Anyo)",
         claves(alumnos, "Grupo", "Anyo"),
         claves(tablas["grupos"], "Grupo", "Anyo")),
        ("NIA de Calificaciones en Alumnos (NIA+Anyo+Curso)",
         claves(calificaciones, "NIA", "Anyo", "Curso"),
         claves(alumnos, "NIA", "Anyo", "Curso")),
        ("Curso de Alumnos en Cursos (Curso+Anyo)",
         claves(alumnos, "Curso", "Anyo"),
         claves(tablas["cursos"], "Codigo", "Anyo")),
    ]
    for descripcion, referenciadas, existentes in comprobaciones:
        huerfanas = referenciadas - existentes
        nivel = logging.WARNING if huerfanas else logging.INFO
        logger.log(nivel, "%s: %d claves sin correspondencia de %d",
                   descripcion, len(huerfanas), len(referenciadas))
        if huerfanas:
            logger.log(nivel, "  ejemplos: %s", sorted(huerfanas)[:5])


if __name__ == "__main__":
    conexion = conectar()
    try:
        tablas = {}
        for tabla in CONSULTAS:
            datos = extraer_tabla(conexion, tabla)
            if tabla in TABLAS_CON_NIA:
                datos = anonimizar(datos)
            tablas[tabla] = datos
    finally:
        conexion.close()

    for tabla, datos in tablas.items():
        guardar(datos, tabla)
    validar(tablas)
