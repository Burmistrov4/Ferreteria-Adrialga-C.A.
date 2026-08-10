#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== Instalando dependencias de Python ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Inicializando base de datos de producción ==="
python scripts/init_prod_db.py

echo "=== Construcción completada con éxito ==="
