# Veterinaria Pepe & Pepito — Sistema web y base de datos

Proyecto académico (Flask + SQL Server) para la gestión de una veterinaria: tienda de productos, portal clínico, panel administrativo, carta de vacunas y comprobantes imprimibles en PDF.

> **Rama de trabajo:** `avanzes-de-prueba` (no usar `main` para estos avances).

## Requisitos previos

- **Windows** (recomendado, por la conexión con SQL Server y ODBC).
- **Python 3.10+** instalado y disponible en `PATH`.
- **SQL Server** (Express/Developer/etc.) en ejecución.
- **ODBC Driver 17 for SQL Server** instalado.
- Una base de datos compatible con el proyecto:
  - **Demo usada en desarrollo:** `VeterinariaUNI_Demo`
  - **Esquema del proyecto:** `Vet_BDD.sql` (en la raíz del repositorio)

## 1. Obtener el proyecto y ubicarse en la rama

```bash
git clone https://github.com/Israbsuwu/Veterinaria_Proyecto_DataBase_2026.git
cd Veterinaria_Proyecto_DataBase_2026
git checkout avanzes-de-prueba
git pull origin avanzes-de-prueba
```

## 2. Crear y activar un entorno virtual (recomendado)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

En CMD:

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

## 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

Dependencias principales: Flask, pyodbc, Jinja2, Werkzeug.

## 4. Configurar la base de datos

Por defecto la aplicación se conecta con:

- **Servidor:** `.` (instancia local)
- **Base de datos:** `VeterinariaUNI_Demo`
- **Autenticación:** Windows (Trusted Connection)
- **Driver:** `ODBC Driver 17 for SQL Server`

Para usar otro servidor o base, define variables de entorno antes de ejecutar:

```powershell
$env:VET_DB_SERVER = "MI_SERVIDOR\SQLEXPRESS"
$env:VET_DB_NAME   = "VeterinariaUNI_Demo"
```

```cmd
set VET_DB_SERVER=MI_SERVIDOR\SQLEXPRESS
set VET_DB_NAME=VeterinariaUNI_Demo
```

### Script opcional (portal de clientes)

Si tu base no tiene contraseña para clientes, ejecuta en SQL Server:

- `sql/agregar_contrasena_cliente.sql`

> La app está preparada para variantes de esquema demo/real en varias tablas (productos, expedientes, etc.), sin requerir cambios de esquema para las funciones implementadas en esta rama.

## 5. Ejecutar la aplicación

```bash
python app.py
```

- Servidor de desarrollo: **http://127.0.0.1:5000** (modo debug, puerto 5000).
- Detén la app con `Ctrl + C`.

## 6. Rutas y módulos principales

| Ruta | Descripción |
| --- | --- |
| `/` | Tienda (catálogo desde BD, búsqueda/filtros, detalle, carrito). Precios en **C$**. |
| `/login` | Inicio de sesión del personal. |
| `/cliente/login` | Inicio de sesión de clientes. |
| `/mi-cuenta` | Portal del cliente (datos y mascotas). |
| `/portal-clinico` | Registro de propietario/mascota, expediente, **análisis de alergia**, carta de vacunas y consulta (personal). |
| `/dashboard` | Panel administrativo: resumen, inventario, productos (alta e imágenes), vencimientos, citas, proveedores, facturas, clientes y equipo. |
| `/tienda/comprobante` | Comprobante de compra imprimible/PDF (se genera al confirmar el pedido en la tienda). |

## 7. Funcionalidades destacadas en esta rama

- **Tienda:** catálogo dinámico (productos/categorías de la BD), imágenes por producto (`static/img/productos/producto_<id>.*`) e ilustraciones de respaldo por categoría, carrito con IVA 15% y **comprobante imprimible/PDF** al confirmar.
- **Portal clínico:** registro ampliado de clientes y mascotas (campos de BD), expediente con **análisis de alergia** (tipo de examen, tipo de alergia, animal/observaciones) registrado en el expediente, y **carta de vacunas/preventivos** (`REGISTRO_PREVENTIVO`) con documento de **seguimiento/próximas aplicaciones** imprimible.
- **Dashboard:** gestión de productos con **precio de venta y costo de compra** (C$), asociación opcional a proveedor (registro en compra/detalle), carga de imágenes de referencia y operaciones de inventario/citas/facturación existentes.
- **Archivos:** límite de subida configurado en 55 MB (imágenes de producto validadas como JPG/PNG/WEBP; imágenes de expediente previstas en `static/img/expedientes/`).

## 8. Notas

- Los precios se manejan y muestran en **córdobas nicaragüenses (C$)**.
- El carrito de la tienda se almacena en el navegador (`localStorage`). El comprobante generado es imprimible/guardable como PDF desde el navegador.
- Para producción se recomienda cambiar `app.secret_key`, desactivar `debug` y usar un servidor WSGI.
- Si hay problemas de conexión, verifica que SQL Server acepte conexiones locales, que el nombre de instancia en `VET_DB_SERVER` sea correcto y que el driver ODBC 17 esté instalado.
