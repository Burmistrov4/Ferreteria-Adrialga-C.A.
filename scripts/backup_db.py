"""
Script de Respaldo de Base de Datos — Ferretería Adrialga, C.A.
Soporta SQLite (copia de seguridad directa del archivo .db) y PostgreSQL (generación de dump SQL).
"""
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Asegurar que el directorio raíz esté en el PYTHONPATH para ejecuciones directas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import DATABASE_URL, BASE_DIR

def run_backup() -> bool:
    print("=== INICIANDO RESPALDO DE BASE DE DATOS ===")
    
    # Crear directorio de respaldos si no existe
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if DATABASE_URL.startswith("sqlite"):
        # Procesar ruta de SQLite
        db_path_str = DATABASE_URL.replace("sqlite:///", "")
        db_path = Path(db_path_str)
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path_str
            
        if not db_path.exists():
            print(f"[ERROR] No se encontró la base de datos SQLite en: {db_path}")
            return False
            
        backup_file = backup_dir / f"adrialga_backup_{timestamp}.db"
        try:
            shutil.copy2(db_path, backup_file)
            print(f"[ÉXITO] Respaldo de SQLite creado exitosamente en: {backup_file}")
            return True
        except Exception as e:
            print(f"[ERROR] Error al copiar base de datos SQLite: {e}")
            return False
            
    elif DATABASE_URL.startswith("postgresql"):
        print("[INFO] Detectada base de datos PostgreSQL. Utilizando pg_dump...")
        backup_file = backup_dir / f"adrialga_backup_{timestamp}.sql"
        
        # Comando para respaldar usando la URL de conexión de forma directa
        # -F p genera un archivo de texto plano SQL legible
        cmd = f'pg_dump "{DATABASE_URL}" -F p -f "{backup_file}"'
        print(f"[INFO] Ejecutando: pg_dump a {backup_file}")
        
        ret = os.system(cmd)
        if ret == 0:
            print(f"[ÉXITO] Respaldo de PostgreSQL creado exitosamente en: {backup_file}")
            return True
        else:
            print("[ERROR] No se pudo realizar el respaldo de PostgreSQL mediante pg_dump.")
            print("[CONSEJO] Asegúrate de que 'pg_dump' de PostgreSQL esté instalado en el sistema y disponible en el PATH.")
            return False
    else:
        print(f"[ERROR] Tipo de base de datos no soportado para respaldos automáticos: {DATABASE_URL}")
        return False

if __name__ == "__main__":
    run_backup()
