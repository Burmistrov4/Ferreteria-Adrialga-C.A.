# Guía de Despliegue en Render — Ferretería Adrialga C.A. ERP/POS

Este documento describe detalladamente los pasos para desplegar la aplicación ERP/POS de la **Ferretería Adrialga, C.A.** en la plataforma Render, utilizando una arquitectura redundante para evitar el apagado de instancias gratuitas mediante pings automáticos y servicios externos (UptimeRobot).

---

## 🏗️ Arquitectura de Despliegue en Render

El despliegue se gestiona automáticamente utilizando el archivo de especificación `render.yaml` (Blueprint), el cual configura dos servicios:
1. **Web Service (FastAPI + Uvicorn)**: Servicio web que sirve la aplicación y los endpoints.
2. **PostgreSQL Database**: Base de datos relacional administrada en producción.

---

## 🚀 Paso a Paso para Desplegar

### 1. Preparar el Repositorio de Git
Asegúrate de que todos los archivos necesarios están confirmados en tu repositorio de GitHub o GitLab:
- `requirements.txt` (Dependencias)
- `build.sh` (Script de instalación y migración)
- `Procfile` (Comando de arranque de producción)
- `render.yaml` (Blueprint del servicio)
- `app/` (Código fuente de la aplicación)
- `scripts/` (Scripts auxiliares de BD)

### 2. Desplegar Usando Render Blueprints
1. Inicia sesión en el panel de [Render](https://dashboard.render.com).
2. Haz clic en **New +** en la esquina superior derecha y selecciona **Blueprint**.
3. Conecta tu repositorio de GitHub/GitLab que contiene la aplicación de la Ferretería Adrialga.
4. Render leerá el archivo `render.yaml` y creará automáticamente:
   - El servicio de base de datos PostgreSQL (`adrialga-postgres-db`).
   - El servicio web FastAPI (`adrialga-ferreteria-pos`).
5. El proceso de construcción llamará a `build.sh`, el cual:
   - Instala las dependencias necesarias.
   - Ejecuta `scripts/init_prod_db.py` para crear de forma segura las tablas del esquema relacional y poblar los datos maestros (Alícuotas IVA, Roles, Usuario Admin Inicial, Formas de Pago, Correlativos).
6. Una vez completado, el servicio web iniciará con el comando definido en el `Procfile`.

---

## ⚡ Evitar la Suspensión del Servicio (Instancia Free)

Las instancias del plan gratuito de Render entran en modo de reposo (sleep) después de 15 minutos de inactividad, lo que causa demoras de hasta 50 segundos en la primera solicitud posterior. Para solucionar esto y garantizar **alta disponibilidad**, hemos implementado una estrategia de doble capa:

### Capa 1: Auto-Ping Asíncrono Interno (FastAPI)
La aplicación incluye un proceso en segundo plano asíncrono en `app/main.py`. Si la variable de entorno `RENDER_EXTERNAL_URL` está configurada, el servidor se auto-enviará un ping a su propio endpoint `/health` cada **10 minutos** para mantener el proceso activo y evitar que Render lo apague.

### Capa 2: Ping Externo Redundante (UptimeRobot - Recomendado)
Para complementar el auto-ping y monitorizar la salud del sistema externamente de manera profesional:
1. Regístrate de forma gratuita en [UptimeRobot](https://uptimerobot.com/).
2. Haz clic en **Add New Monitor**.
3. Selecciona el tipo de monitor: `HTTP(s)`.
4. Configura los siguientes detalles:
   - **Friendly Name**: `Ferretería Adrialga - HealthCheck`
   - **URL (or IP)**: Introduce la URL externa de tu servicio en Render (ej. `https://adrialga-ferreteria-pos.onrender.com/health`).
   - **Monitoring Interval**: Cada `5 minutos` o `10 minutos`.
5. Guarda el monitor. Esto asegurará tráfico continuo al endpoint de salud, previniendo el reposo de la instancia gratuita de forma 100% fiable y ofreciéndote alertas instantáneas por correo electrónico si el servicio se cae.

---

## 💾 Respaldos de Base de Datos en Producción

El archivo `scripts/backup_db.py` es un script multifuncional que soporta el respaldo tanto del entorno SQLite local como del entorno PostgreSQL de Render.

Para ejecutar un respaldo en producción:
- Accede a la pestaña **Shell** de tu Web Service en el panel de Render.
- Ejecuta el siguiente comando:
  ```bash
  python scripts/backup_db.py
  ```
- El script detectará automáticamente la variable `DATABASE_URL`, generará un dump estructurado de SQL mediante `pg_dump` y lo guardará con una estampa de tiempo en la carpeta `/backups` de la instancia.

---

## 🛠️ Variables de Entorno Configurables

Si decides configurar el servicio manualmente en lugar de usar Blueprints, utiliza estas variables:

| Variable | Descripción | Valor por Defecto / Ejemplo |
| :--- | :--- | :--- |
| `DATABASE_URL` | URI de conexión a la base de datos (PostgreSQL/SQLite) | Generada por Render o `sqlite:///adrialga.db` |
| `SECRET_KEY` | Clave secreta para codificación y seguridad de tokens JWT | Una cadena segura hexadecimal de 64 caracteres |
| `DEBUG` | Activa el modo de depuración de FastAPI | `False` en producción |
| `PORT` | Puerto en el que escucha el servidor web | `8000` (Render asigna esta variable automáticamente) |
| `RENDER_EXTERNAL_URL` | URL pública externa asignada por Render | `https://adrialga-ferreteria-pos.onrender.com` |
