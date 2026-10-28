"""Genera grupos.sql (mismo formato que alumnos.sql, cursos.sql...) a partir de
los grupos.xml exportados de ITACA, para cargarlos en PostgreSQL.

El Anyo se obtiene del atributo "curso" de la cabecera <centro> de cada XML.

Uso:
    python ingesta/generar_grupos_sql.py <carpeta Analisis_Academico> [salida]
    python ingesta/generar_grupos_sql.py ../bigdata-p1-itaca/data/exportaciones/Analisis_Academico
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

COLUMNAS = ["codigo", "nombre", "ensenanza", "linea", "turno", "modalidad", "aula", "capacidad"]


def literal(valor):
    return "'" + (valor or "").replace("'", "''") + "'"


def main():
    origen_dir = Path(sys.argv[1])
    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("grupos.sql")

    lineas = [
        "-- Tabla unificada grupos",
        "",
        "DROP TABLE IF EXISTS grupos;",
        "CREATE TABLE grupos (",
        *[f"    {c} TEXT," for c in COLUMNAS],
        "    anyo INTEGER",
        ");",
    ]
    for carpeta in sorted(p for p in origen_dir.iterdir() if p.is_dir()):
        xml = carpeta / "grupos.xml"
        if not xml.exists():
            print(f"[aviso] no existe {xml}")
            continue
        centro = ET.parse(xml).getroot()
        anyo = int(centro.get("curso"))
        filas = [
            "(" + ", ".join(literal(g.get(c)) for c in COLUMNAS) + f", {anyo})"
            for g in centro.iter("grupo")
        ]
        lineas += [
            "",
            f"-- ===== {carpeta.name} =====",
            f"-- Origen: {xml.as_posix()} · {len(filas)} filas",
            f"INSERT INTO grupos ({', '.join(COLUMNAS)}, anyo) VALUES",
            ",\n".join(filas) + ";",
        ]
        print(f"{carpeta.name}: {len(filas)} grupos")

    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {salida}")


if __name__ == "__main__":
    main()
