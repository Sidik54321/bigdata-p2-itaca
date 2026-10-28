"""Ingesta de la base de datos de ITACA (PostgreSQL) con Spark vía JDBC.

Extrae las tablas del modelo y las deja en la zona raw:
    data/raw/<tabla>/fecha_ingesta=<AAAA-MM-DD>/anyo=<anyo>/part-*.json

    alumnos         -> anyo, nia, curso, turno, grupo
    modulos         -> anyo, curso, modulo, nombre_modulo   (tabla contenidos)
    calificaciones  -> anyo, nia, curso, modulo, nota, evaluacion
    grupos          -> anyo, grupo, nombre, turno, modalidad, aula, capacidad

Solo se leen las columnas del modelo (minimización de datos) y el NIA se
anonimiza con SHA-256 (10 primeros caracteres, igual que en la P1).
La tabla Horas no tiene origen en ITACA todavía: queda fuera de esta ingesta.

Uso (desde la raíz del proyecto):
    docker compose run --rm ingesta
"""

import os
from datetime import date

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

CONSULTAS = {
    "alumnos": """
        SELECT anyo, nia, curso, turno, grupo
        FROM alumnos
    """,
    "modulos": """
        SELECT anyo, curso, codigo AS modulo, nombre_cas AS nombre_modulo
        FROM contenidos
    """,
    "calificaciones": """
        SELECT anyo, alumno AS nia, curso, contenido AS modulo,
               nota_numerica AS nota, evaluacion
        FROM calificaciones
    """,
    "grupos": """
        SELECT anyo, codigo AS grupo, nombre, turno, modalidad, aula, capacidad
        FROM grupos
    """,
}

# Tablas que contienen (o referencian) el NIA y deben anonimizarse
TABLAS_CON_NIA = {"alumnos", "calificaciones"}


def leer_tabla(spark, tabla: str):
    url = f"jdbc:postgresql://{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    # Lectura en paralelo: una partición JDBC por curso académico
    return (
        spark.read.format("jdbc")
        .option("url", url)
        .option("driver", "org.postgresql.Driver")
        .option("user", os.environ["DB_USER"])
        .option("password", os.environ["DB_PASSWORD"])
        .option("dbtable", f"({CONSULTAS[tabla]}) AS {tabla}")
        .option("partitionColumn", "anyo")
        .option("lowerBound", 2021)
        .option("upperBound", 2026)
        .option("numPartitions", 5)
        .load()
    )


def anonimizar(df):
    return df.withColumn("nia", F.substring(F.sha2(F.trim("nia"), 256), 1, 10))


def main():
    spark = SparkSession.builder.appName("ingesta_itaca_jdbc").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    fecha = date.today().isoformat()

    for tabla in CONSULTAS:
        df = leer_tabla(spark, tabla)
        if tabla in TABLAS_CON_NIA:
            df = anonimizar(df)
        ruta = f"data/raw/{tabla}/fecha_ingesta={fecha}"
        df.write.mode("overwrite").partitionBy("anyo").json(ruta)
        print(f"[ingesta] {tabla}: {df.count()} registros -> {ruta}")

    spark.stop()


if __name__ == "__main__":
    main()
