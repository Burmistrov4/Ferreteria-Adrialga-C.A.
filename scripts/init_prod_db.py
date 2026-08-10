"""
Script de inicialización de la base de datos de producción — Ferretería Adrialga, C.A.
Crea todas las tablas y realiza el seeding de datos maestros de forma segura e idempotente.
"""
import sys
import os

# Asegurar que el directorio raíz esté en el PYTHONPATH para ejecuciones directas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.seed_data import run_seed

def main():
    print("=== INICIANDO CONFIGURACIÓN DE BASE DE DATOS DE PRODUCCIÓN ===")
    run_seed()
    print("=== BASE DE DATOS DE PRODUCCIÓN LISTA ===")

if __name__ == "__main__":
    main()
