import hashlib
import os
import re
from datetime import date, datetime

from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import pyodbc

from dashboard_data import (
    actualizar_estado_cita,
    cargar_catalogo,
    cargar_dashboard,
    crear_producto,
    crear_proveedor,
    obtener_factura,
    panel_vacio,
    registrar_movimiento,
)

app = Flask(__name__)
app.secret_key = 'pepe_pepito_secreto'
app.config['MAX_CONTENT_LENGTH'] = 55 * 1024 * 1024

CARPETA_PRODUCTOS = os.path.join(app.static_folder, 'img', 'productos')
CARPETA_EXPEDIENTES = os.path.join(app.static_folder, 'img', 'expedientes')
EXTENSIONES_IMAGEN = {'png', 'jpg', 'jpeg', 'webp'}

ARTE_CATEGORIAS = {
    'alimento seco y humedo para perros': 'alimento-perros.svg',
    'alimento y arena para gatos': 'alimento-gatos.svg',
    'antiparasitarios': 'antiparasitarios.svg',
    'higiene y cuidado': 'higiene.svg',
    'accesorios para perros': 'accesorios-perros.svg',
    'accesorios para gatos': 'accesorios-gatos.svg',
    'farmacia y primeros auxilios': 'farmacia.svg',
    'vacunas y pruebas preventivas': 'vacunas.svg',
    'suplementos nutricionales': 'suplementos.svg',
    'insumos clinicos': 'insumos.svg',
}


def _clave_categoria(nombre):
    texto = str(nombre or '').strip().lower()
    for acento, plano in (
        ('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'),
        ('ü', 'u'), ('ñ', 'n'),
    ):
        texto = texto.replace(acento, plano)
    return ' '.join(texto.split())


@app.template_global()
def arte_categoria(nombre):
    """Ilustración local que se usa cuando un producto no tiene foto propia."""
    archivo = ARTE_CATEGORIAS.get(_clave_categoria(nombre), 'producto.svg')
    return url_for('static', filename=f'img/categorias/{archivo}')


@app.template_global()
def imagen_producto(id_producto):
    """Devuelve la URL de la foto subida para un producto, si existe."""
    for extension in ('jpg', 'jpeg', 'png', 'webp'):
        nombre = f'producto_{int(id_producto)}.{extension}'
        if os.path.isfile(os.path.join(CARPETA_PRODUCTOS, nombre)):
            return url_for('static', filename=f'img/productos/{nombre}')
    return None


def validar_imagen(archivo):
    """Valida la extensión de una imagen subida y devuelve su extensión."""
    if archivo is None or not archivo.filename:
        return None
    extension = os.path.splitext(archivo.filename)[1].lower().lstrip('.')
    if extension not in EXTENSIONES_IMAGEN:
        raise ValueError('La imagen debe ser JPG, PNG o WEBP.')
    return extension


def guardar_imagen_producto(id_producto, archivo):
    """Guarda la foto con el id del producto y reemplaza la anterior."""
    extension = validar_imagen(archivo)
    if not extension:
        return None

    os.makedirs(CARPETA_PRODUCTOS, exist_ok=True)
    for existente in os.listdir(CARPETA_PRODUCTOS):
        if existente.lower().startswith(f'producto_{int(id_producto)}.'):
            try:
                os.remove(os.path.join(CARPETA_PRODUCTOS, existente))
            except OSError:
                pass

    nombre = f'producto_{int(id_producto)}.{extension}'
    archivo.save(os.path.join(CARPETA_PRODUCTOS, nombre))
    return nombre


# ---------------------------------------------------------------------------
# Filtros de presentación
# ---------------------------------------------------------------------------

@app.template_filter('moneda')
def filtro_moneda(valor):
    if valor is None or valor == '':
        return '—'
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return '—'
    return f'C$ {numero:,.2f}'


@app.template_filter('numero')
def filtro_numero(valor):
    try:
        return f'{int(valor):,}'
    except (TypeError, ValueError):
        return '0'


@app.template_filter('fecha')
def filtro_fecha(valor, formato='%d/%m/%Y'):
    if not valor:
        return '—'
    try:
        return valor.strftime(formato)
    except AttributeError:
        return str(valor)


@app.template_filter('fechahora')
def filtro_fechahora(valor):
    return filtro_fecha(valor, '%d/%m/%Y · %I:%M %p')


@app.template_filter('hora')
def filtro_hora(valor):
    return filtro_fecha(valor, '%I:%M %p')

# Servidor y base de datos. Se pueden cambiar sin tocar el código con las
# variables de entorno VET_DB_SERVER y VET_DB_NAME, por ejemplo:
#   set VET_DB_SERVER=MSI\SQLEXPRESS
#   set VET_DB_NAME=VetPepePepito
DB_SERVER = os.environ.get('VET_DB_SERVER', r'.')
DB_NAME = os.environ.get('VET_DB_NAME', 'VeterinariaUNI_Demo')

CORREO_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
TELEFONO_RE = re.compile(r'^[0-9+\-\s()]{8,20}$')
ROLES_RESPALDO = [{'id': 1, 'nombre': 'Administrador'}, {'id': 2, 'nombre': 'Veterinario'}]


def get_db_connection():
    conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};Trusted_Connection=yes;'
    return pyodbc.connect(conn_str)


def limpiar(valor):
    """Quita espacios sobrantes de un campo del formulario."""
    return (valor or '').strip()


def obtener_roles():
    """Roles disponibles para el registro (tabla ROL)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT IdRol, NombreRol FROM ROL ORDER BY IdRol")
        roles = [{'id': r.IdRol, 'nombre': r.NombreRol} for r in cursor.fetchall()]
        conn.close()
        return roles or ROLES_RESPALDO
    except Exception:
        return ROLES_RESPALDO


def buscar_usuario_por_correo(cursor, correo, esquema):
    cursor.execute(f"""
        SELECT U.IdUsuario, U.Nombre, U.Apellido, U.Telefono, U.Correo,
               U.{esquema['col_clave']} AS Clave, U.Estado, R.NombreRol
        FROM USUARIO U INNER JOIN ROL R ON U.IdRol = R.IdRol
        WHERE U.Correo = ?
    """, (correo,))
    return cursor.fetchone()


ESQUEMA_CACHE = {}


def detectar_esquema(cursor):
    """Detecta si USUARIO guarda la clave en texto (Contrasena) o en SHA-256 (ContrasenaHash)."""
    llave_cache = (DB_SERVER, DB_NAME)
    if llave_cache in ESQUEMA_CACHE:
        return ESQUEMA_CACHE[llave_cache]

    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'USUARIO'
    """)
    columnas = {str(fila[0]).lower() for fila in cursor.fetchall()}

    col_clave = 'ContrasenaHash' if 'contrasenahash' in columnas else 'Contrasena'
    if 'fecharegistro' in columnas:
        col_fecha = 'FechaRegistro'
    elif 'fechareg' in columnas:
        col_fecha = 'FechaReg'
    else:
        col_fecha = None

    cursor.execute("SELECT COLUMNPROPERTY(OBJECT_ID('USUARIO'), 'IdUsuario', 'IsIdentity')")
    identidad = cursor.fetchone()[0]

    esquema = {
        'col_clave': col_clave,
        'col_fecha': col_fecha,
        'hash': col_clave == 'ContrasenaHash',
        'id_identity': bool(identidad),
    }
    ESQUEMA_CACHE[llave_cache] = esquema
    return esquema


def clave_coincide(guardada, escrita, esquema):
    """Compara la clave escrita con la guardada, respetando el formato de la base."""
    if guardada is None:
        return False
    if esquema['hash']:
        calculada = hashlib.sha256(escrita.encode('utf-8')).hexdigest().upper()
        return str(guardada).strip().upper() == calculada
    return str(guardada) == escrita


def clave_para_guardar(contrasena, esquema):
    """Devuelve la clave lista para insertar según el formato de la base."""
    if esquema['hash']:
        return hashlib.sha256(contrasena.encode('utf-8')).hexdigest().upper()
    return contrasena


def nombre_columna_alergias(cursor):
    """La tabla EXPEDIENTE_CLINICO usa 'Alergias' o 'AlergiasConocidas' según la base."""
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'EXPEDIENTE_CLINICO'
          AND COLUMN_NAME IN ('Alergias', 'AlergiasConocidas')
    """)
    fila = cursor.fetchone()
    return fila[0] if fila else 'Alergias'


def valor_estado_expediente(cursor, columna):
    """Devuelve un estado válido para EXPEDIENTE_CLINICO según su restricción CHECK.

    La base demo usa EstadoRegistro ('ABIERTO'/'CERRADO') y la base real
    usa EstadoReg ('Activo'/'Archivado').
    """
    candidatos = ['ABIERTO', 'Activo', 'ACTIVO', 'A']
    try:
        cursor.execute("""
            SELECT cc.definition
            FROM sys.check_constraints cc
            JOIN sys.columns c
              ON c.object_id = cc.parent_object_id
             AND c.column_id = cc.parent_column_id
            WHERE cc.parent_object_id = OBJECT_ID('EXPEDIENTE_CLINICO')
              AND c.name = ?
        """, (columna,))
        definicion = cursor.fetchone()
        if definicion and definicion[0]:
            texto = str(definicion[0])
            for candidato in candidatos:
                if candidato in texto:
                    return candidato
    except Exception:
        pass

    # Sin CHECK legible: elegir por el nombre de la columna.
    return 'ABIERTO' if columna.lower() == 'estadoregistro' else 'Activo'


def columna_es_identidad(cursor, tabla, columna):
    cursor.execute("SELECT COLUMNPROPERTY(OBJECT_ID(?), ?, 'IsIdentity')",
                   (tabla, columna))
    fila = cursor.fetchone()
    return bool(fila[0]) if fila else False


def columnas_tabla(cursor, tabla):
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
    """, (tabla,))
    return {str(fila[0]).lower(): str(fila[0]) for fila in cursor.fetchall()}


def columna_id(cursor, tabla, *candidatos):
    """Devuelve el nombre real de la columna identificadora de una tabla."""
    columnas = columnas_tabla(cursor, tabla)
    for candidato in candidatos:
        if candidato.lower() in columnas:
            return columnas[candidato.lower()]
    return candidatos[0]


def iniciar_sesion(usuario):
    session.clear()
    session['user_id'] = usuario.IdUsuario
    session['user_nombre'] = usuario.Nombre
    session['user_apellido'] = usuario.Apellido
    session['user_correo'] = usuario.Correo
    session['user_rol'] = usuario.NombreRol
    session['user_tipo'] = 'personal'


def iniciar_sesion_cliente(cliente):
    session.clear()
    session['cliente_id'] = cliente.IdCliente
    session['user_nombre'] = cliente.Nombre
    session['user_apellido'] = cliente.Apellido
    session['user_correo'] = cliente.Correo
    session['user_rol'] = 'Cliente'
    session['user_tipo'] = 'cliente'


def es_personal():
    return session.get('user_tipo') == 'personal' and 'user_id' in session


def datos_usuario():
    nombre = session.get('user_nombre', '') or ''
    apellido = session.get('user_apellido', '') or ''
    return {
        'id': session.get('user_id'),
        'nombre': nombre,
        'apellido': apellido,
        'correo': session.get('user_correo', '') or '',
        'rol': session.get('user_rol', 'Personal') or 'Personal',
        'iniciales': (nombre[:1] + apellido[:1]).upper() or 'VP',
    }


def render_login(tab='login', datos=None, correo=''):
    return render_template('login.html', tab=tab, roles=obtener_roles(),
                           datos=datos or {}, correo=correo)


def render_cliente(tab='login', datos=None, correo=''):
    return render_template('login_cliente.html', tab=tab,
                           datos=datos or {}, correo=correo)


# ---------------------------------------------------------------------------
# Portal de clientes (tabla CLIENTE)
# ---------------------------------------------------------------------------

def columnas_cliente(cursor):
    """Detecta cómo están nombradas las columnas opcionales de CLIENTE."""
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'CLIENTE'
    """)
    columnas = {str(fila[0]).lower() for fila in cursor.fetchall()}
    cursor.execute("SELECT COLUMNPROPERTY(OBJECT_ID('CLIENTE'), 'IdCliente', 'IsIdentity')")
    identidad = cursor.fetchone()[0]
    return {
        'clave': 'Contrasena' if 'contrasena' in columnas else None,
        'notif': ('AceptaNotif' if 'aceptanotif' in columnas
                  else 'AceptaNotificaciones' if 'aceptanotificaciones' in columnas
                  else None),
        'id_identity': bool(identidad),
    }


def buscar_cliente_por_correo(cursor, correo, columnas):
    clave = columnas['clave'] or 'NULL'
    cursor.execute(f"""
        SELECT IdCliente, Nombre, Apellido, Cedula, Telefono, Correo, Direccion,
               {clave} AS Clave
        FROM CLIENTE
        WHERE Correo = ?
    """, (correo,))
    return cursor.fetchone()


def normalizar_cedula(valor):
    return re.sub(r'[\s\-]', '', (valor or '').strip()).upper()


def falta_columna_clave(mensaje='El portal de clientes necesita una actualización en la base de datos.'):
    flash(mensaje, 'error')
    return render_cliente('login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_tipo') == 'cliente':
        return redirect(url_for('index'))
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        correo = limpiar(request.form.get('correo')).lower()
        contrasena = request.form.get('contrasena') or ''

        if not correo or not contrasena:
            flash('Escribe tu correo y tu contraseña para entrar.', 'error')
            return render_login('login', correo=correo)

        esquema = None
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                esquema = detectar_esquema(cursor)
                usuario = buscar_usuario_por_correo(cursor, correo, esquema)
            finally:
                conn.close()
        except pyodbc.Error:
            flash('No se pudo conectar con la base de datos. Revisa que SQL Server esté encendido.', 'error')
            return render_login('login', correo=correo)

        if usuario is None or not clave_coincide(usuario.Clave, contrasena, esquema):
            flash('El correo o la contraseña no coinciden. Inténtalo de nuevo.', 'error')
            return render_login('login', correo=correo)

        if (usuario.Estado or '').strip().lower() != 'activo':
            flash('Tu cuenta está inactiva. Comunicate con la administración de la veterinaria.', 'error')
            return render_login('login', correo=correo)

        iniciar_sesion(usuario)
        return redirect(url_for('dashboard'))

    return render_login('login')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if session.get('user_tipo') == 'cliente':
        return redirect(url_for('index'))
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_login('registro')

    datos = {
        'nombre': limpiar(request.form.get('nombre')),
        'apellido': limpiar(request.form.get('apellido')),
        'telefono': limpiar(request.form.get('telefono')),
        'correo': limpiar(request.form.get('correo')).lower(),
        'rol': limpiar(request.form.get('rol')) or 'Veterinario',
    }
    contrasena = request.form.get('contrasena') or ''
    confirmar = request.form.get('confirmar') or ''

    errores = []
    if not datos['nombre']:
        errores.append('El nombre es obligatorio.')
    if not datos['apellido']:
        errores.append('El apellido es obligatorio.')
    if not TELEFONO_RE.match(datos['telefono']):
        errores.append('Escribe un teléfono válido (Ej. 8888-1234).')
    if not CORREO_RE.match(datos['correo']):
        errores.append('Escribe un correo electrónico válido.')
    if len(contrasena) < 6:
        errores.append('La contraseña debe tener al menos 6 caracteres.')
    if contrasena != confirmar:
        errores.append('Las contraseñas no coinciden.')

    if errores:
        for mensaje in errores:
            flash(mensaje, 'error')
        return render_login('registro', datos=datos, correo=datos['correo'])

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        esquema = detectar_esquema(cursor)

        # Si el correo ya existe, se intenta iniciar sesión con los mismos datos.
        existente = buscar_usuario_por_correo(cursor, datos['correo'], esquema)
        if existente is not None:
            if clave_coincide(existente.Clave, contrasena, esquema):
                if (existente.Estado or '').strip().lower() != 'activo':
                    flash('Tu cuenta está inactiva. Comunicate con la administración de la veterinaria.', 'error')
                    return render_login('login', correo=datos['correo'])
                iniciar_sesion(existente)
                return redirect(url_for('dashboard'))
            flash('Ese correo ya está registrado. Escribe la contraseña correcta para entrar.', 'error')
            return render_login('login', correo=datos['correo'])

        cursor.execute("SELECT IdRol FROM ROL WHERE NombreRol = ?", (datos['rol'],))
        fila_rol = cursor.fetchone()
        if fila_rol is None:
            flash('El rol seleccionado no existe en el sistema.', 'error')
            return render_login('registro', datos=datos, correo=datos['correo'])

        campos = ['Nombre', 'Apellido', 'Telefono', 'Correo', esquema['col_clave'], 'Estado', 'IdRol']
        marcas = ['?', '?', '?', '?', '?', "'Activo'", '?']
        parametros = [datos['nombre'], datos['apellido'], datos['telefono'], datos['correo'],
                      clave_para_guardar(contrasena, esquema), fila_rol.IdRol]
        if esquema['col_fecha']:
            campos.append(esquema['col_fecha'])
            marcas.append('GETDATE()')
        if not esquema['id_identity']:
            cursor.execute("SELECT ISNULL(MAX(IdUsuario), 0) + 1 FROM USUARIO")
            campos.insert(0, 'IdUsuario')
            marcas.insert(0, '?')
            parametros.insert(0, cursor.fetchone()[0])

        cursor.execute(f"""
            INSERT INTO USUARIO ({', '.join(campos)})
            OUTPUT INSERTED.IdUsuario
            VALUES ({', '.join(marcas)})
        """, parametros)
        cursor.fetchone()
        conn.commit()

        usuario = buscar_usuario_por_correo(cursor, datos['correo'], esquema)
        iniciar_sesion(usuario)
        return redirect(url_for('dashboard'))

    except pyodbc.IntegrityError:
        flash('No se pudo crear la cuenta: algún dato no cumple las reglas de la base. Revisa los campos.', 'error')
        return render_login('registro', datos=datos, correo=datos['correo'])
    except pyodbc.Error:
        flash('No se pudo crear la cuenta. Revisa la conexión con la base de datos.', 'error')
        return render_login('registro', datos=datos, correo=datos['correo'])
    finally:
        if conn is not None:
            conn.close()

@app.route('/cliente', methods=['GET', 'POST'])
def cliente_login():
    if session.get('user_tipo') == 'cliente':
        return redirect(url_for('index'))
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        correo = limpiar(request.form.get('correo')).lower()
        contrasena = request.form.get('contrasena') or ''

        if not correo or not contrasena:
            flash('Escribe tu correo y tu contraseña para entrar.', 'error')
            return render_cliente('login', correo=correo)

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            columnas = columnas_cliente(cursor)
            if columnas['clave'] is None:
                return falta_columna_clave(
                    'Falta agregar la columna Contrasena a la tabla CLIENTE. '
                    'Ejecuta el archivo sql/agregar_contrasena_cliente.sql.')
            cliente = buscar_cliente_por_correo(cursor, correo, columnas)
        except pyodbc.Error:
            flash('No se pudo conectar con la base de datos. Revisa que SQL Server esté encendido.', 'error')
            return render_cliente('login', correo=correo)
        finally:
            if conn is not None:
                conn.close()

        if cliente is None:
            flash('Ese correo todavía no está registrado. Crea tu cuenta para empezar.', 'error')
            return render_cliente('login', correo=correo)

        if not (cliente.Clave or '').strip():
            flash('Tu cuenta aún no está activada. Ve a "Crear cuenta" y usa tu cédula para activarla.', 'error')
            return render_cliente('registro', datos={'correo': correo}, correo=correo)

        if str(cliente.Clave) != contrasena:
            flash('La contraseña no coincide. Inténtalo de nuevo.', 'error')
            return render_cliente('login', correo=correo)

        iniciar_sesion_cliente(cliente)
        return redirect(url_for('index'))

    return render_cliente('login')


@app.route('/cliente/registro', methods=['GET', 'POST'])
def cliente_registro():
    if session.get('user_tipo') == 'cliente':
        return redirect(url_for('index'))
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_cliente('registro')

    datos = {
        'nombre': limpiar(request.form.get('nombre')),
        'apellido': limpiar(request.form.get('apellido')),
        'cedula': limpiar(request.form.get('cedula')),
        'telefono': limpiar(request.form.get('telefono')),
        'correo': limpiar(request.form.get('correo')).lower(),
        'direccion': limpiar(request.form.get('direccion')),
    }
    contrasena = request.form.get('contrasena') or ''
    confirmar = request.form.get('confirmar') or ''
    acepta = 1 if request.form.get('notificaciones') else 0

    errores = []
    if not datos['nombre']:
        errores.append('El nombre es obligatorio.')
    if not datos['apellido']:
        errores.append('El apellido es obligatorio.')
    if len(normalizar_cedula(datos['cedula'])) < 5:
        errores.append('Escribe una cédula válida.')
    if not TELEFONO_RE.match(datos['telefono']):
        errores.append('Escribe un teléfono válido (Ej. 8888-1234).')
    if not CORREO_RE.match(datos['correo']):
        errores.append('Escribe un correo electrónico válido.')
    if len(contrasena) < 6:
        errores.append('La contraseña debe tener al menos 6 caracteres.')
    if contrasena != confirmar:
        errores.append('Las contraseñas no coinciden.')

    if errores:
        for mensaje in errores:
            flash(mensaje, 'error')
        return render_cliente('registro', datos=datos, correo=datos['correo'])

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        columnas = columnas_cliente(cursor)
        if columnas['clave'] is None:
            return falta_columna_clave(
                'Falta agregar la columna Contrasena a la tabla CLIENTE. '
                'Ejecuta el archivo sql/agregar_contrasena_cliente.sql.')

        existente = buscar_cliente_por_correo(cursor, datos['correo'], columnas)
        if existente is not None:
            # El correo ya está en CLIENTE (normalmente lo registró el personal).
            if (existente.Clave or '').strip():
                if str(existente.Clave) == contrasena:
                    iniciar_sesion_cliente(existente)
                    return redirect(url_for('index'))
                flash('Ese correo ya tiene una cuenta creada. Escribe la contraseña correcta para entrar.', 'error')
                return render_cliente('login', correo=datos['correo'])

            # Cuenta sin contraseña: se activa validando la cédula registrada.
            if normalizar_cedula(existente.Cedula) != normalizar_cedula(datos['cedula']):
                flash('Ese correo ya está registrado en la veterinaria, pero la cédula no coincide '
                      'con la que tenemos. Verifícala o consúltanos en recepción.', 'error')
                return render_cliente('registro', datos=datos, correo=datos['correo'])

            cursor.execute("UPDATE CLIENTE SET Contrasena = ? WHERE IdCliente = ?",
                           (contrasena, existente.IdCliente))
            conn.commit()
            cliente = buscar_cliente_por_correo(cursor, datos['correo'], columnas)
            iniciar_sesion_cliente(cliente)
            return redirect(url_for('index'))

        campos = ['Nombre', 'Apellido', 'Cedula', 'Telefono', 'Correo', 'Direccion', 'Contrasena']
        marcas = ['?', '?', '?', '?', '?', '?', '?']
        parametros = [datos['nombre'], datos['apellido'], datos['cedula'], datos['telefono'],
                      datos['correo'], datos['direccion'] or None, contrasena]

        if columnas['notif']:
            campos.append(columnas['notif'])
            marcas.append('?')
            parametros.append(acepta)
        if not columnas['id_identity']:
            cursor.execute("SELECT ISNULL(MAX(IdCliente), 0) + 1 FROM CLIENTE")
            campos.insert(0, 'IdCliente')
            marcas.insert(0, '?')
            parametros.insert(0, cursor.fetchone()[0])

        cursor.execute(f"""
            INSERT INTO CLIENTE ({', '.join(campos)})
            OUTPUT INSERTED.IdCliente
            VALUES ({', '.join(marcas)})
        """, parametros)
        cursor.fetchone()
        conn.commit()

        cliente = buscar_cliente_por_correo(cursor, datos['correo'], columnas)
        iniciar_sesion_cliente(cliente)
        return redirect(url_for('index'))

    except pyodbc.IntegrityError:
        flash('No se pudo crear la cuenta: revisa la cédula y el correo.', 'error')
        return render_cliente('registro', datos=datos, correo=datos['correo'])
    except pyodbc.Error:
        flash('No se pudo crear la cuenta. Revisa la conexión con la base de datos.', 'error')
        return render_cliente('registro', datos=datos, correo=datos['correo'])
    finally:
        if conn is not None:
            conn.close()


@app.route('/mi-cuenta')
def mi_cuenta():
    if session.get('user_tipo') == 'personal':
        return redirect(url_for('dashboard'))
    if session.get('user_tipo') != 'cliente':
        return redirect(url_for('cliente_login'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT IdCliente, Nombre, Apellido, Cedula, Telefono, Correo, Direccion
            FROM CLIENTE WHERE IdCliente = ?
        """, (session['cliente_id'],))
        fila = cursor.fetchone()
        if fila is None:
            session.clear()
            return redirect(url_for('cliente_login'))

        cliente = {
            'nombre': fila.Nombre, 'apellido': fila.Apellido, 'cedula': fila.Cedula,
            'telefono': fila.Telefono, 'correo': fila.Correo, 'direccion': fila.Direccion,
        }

        cursor.execute("""
            SELECT M.Nombre, M.Especie, M.Raza, M.Sexo, M.Color,
                   E.CondicionesPreexistentes, E.ObservacionesGenerales
            FROM MASCOTA M
            LEFT JOIN EXPEDIENTE_CLINICO E ON M.IdMascota = E.IdMascota
            WHERE M.IdCliente = ?
            ORDER BY M.Nombre
        """, (session['cliente_id'],))
        mascotas = []
        for m in cursor.fetchall():
            condiciones = (m.CondicionesPreexistentes or '').strip()
            observaciones = (m.ObservacionesGenerales or '').strip()
            mascotas.append({
                'nombre': m.Nombre, 'especie': m.Especie, 'raza': m.Raza,
                'sexo': m.Sexo, 'color': m.Color or '',
                'condiciones': condiciones, 'observaciones': observaciones,
            })
    except pyodbc.Error:
        flash('No se pudo cargar tu cuenta. Revisa la conexión con la base de datos.', 'error')
        return redirect(url_for('cliente_login'))
    finally:
        if conn is not None:
            conn.close()

    return render_template('mi_cuenta.html', cliente=cliente, mascotas=mascotas)


@app.route('/logout')
def logout():
    tipo = session.get('user_tipo')
    session.clear()
    if tipo == 'cliente':
        return redirect(url_for('cliente_login'))
    return redirect(url_for('login'))


@app.route('/')
def index():
    """Tienda: solo catálogo y compra. El personal entra al panel para gestionar."""
    if session.get('user_tipo') == 'cliente':
        pass
    elif not es_personal():
        return redirect(url_for('login'))

    productos, categorias = [], []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        catalogo = cargar_catalogo(cursor)
        productos = catalogo['productos']
        categorias = catalogo['categorias']
        for producto in productos:
            producto['imagen'] = imagen_producto(producto['id'])
            producto['arte'] = arte_categoria(producto['categoria'])
    except pyodbc.Error:
        flash('No se pudo cargar el catálogo. Revisa la conexión con la base de datos.', 'error')
    finally:
        if conn is not None:
            conn.close()

    return render_template('index.html', productos=productos, categorias=categorias,
                           es_personal=es_personal())


@app.route('/portal-clinico')
def portal_clinico():
    """Expedientes y registro de pacientes, separado de la tienda."""
    if not es_personal():
        if session.get('user_tipo') == 'cliente':
            return redirect(url_for('index'))
        return redirect(url_for('login'))

    clientes, mascotas = [], []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT IdCliente, Nombre, Apellido, Cedula, Telefono, Correo, Direccion
            FROM CLIENTE
            ORDER BY Nombre, Apellido
        """)
        clientes = [{
            'id': c.IdCliente, 'nombre': c.Nombre, 'apellido': c.Apellido,
            'cedula': c.Cedula or '', 'tel': c.Telefono or '',
            'correo': c.Correo or '', 'direccion': c.Direccion or '',
        } for c in cursor.fetchall()]

        cursor.execute("""
            SELECT M.IdMascota, M.Nombre, M.Especie, M.Raza, M.Sexo, M.IdCliente,
                   M.Color, M.FechaNacimiento, M.SenasParticulares,
                   E.CondicionesPreexistentes, E.ObservacionesGenerales
            FROM MASCOTA M
            LEFT JOIN EXPEDIENTE_CLINICO E ON M.IdMascota = E.IdMascota
            ORDER BY M.Nombre
        """)
        for m in cursor.fetchall():
            nacimiento = ''
            if m.FechaNacimiento:
                try:
                    nacimiento = m.FechaNacimiento.strftime('%Y-%m-%d')
                except Exception:
                    nacimiento = str(m.FechaNacimiento)[:10]
            condiciones = (m.CondicionesPreexistentes or '').strip()
            observaciones = (m.ObservacionesGenerales or '').strip()
            analisis = condiciones or observaciones
            mascotas.append({
                'id': m.IdMascota, 'duenoId': m.IdCliente, 'nombre': m.Nombre,
                'especie': m.Especie or '', 'raza': m.Raza or '', 'sexo': m.Sexo or '',
                'color': m.Color or '', 'fecha_nacimiento': nacimiento,
                'senas': m.SenasParticulares or '',
                'condiciones': condiciones, 'observaciones': observaciones,
                'analisis_alergia': analisis,
            })
    except pyodbc.Error:
        flash('No se pudo cargar el portal clínico. Revisa la conexión con la base de datos.', 'error')
    finally:
        if conn is not None:
            conn.close()

    return render_template('portal_clinico.html', clientes=clientes, mascotas=mascotas,
                           usuario=datos_usuario())


# ---------------------------------------------------------------------------
# Panel de administración
# ---------------------------------------------------------------------------

@app.route('/dashboard')
def dashboard():
    if not es_personal():
        if session.get('user_tipo') == 'cliente':
            return redirect(url_for('index'))
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        datos = cargar_dashboard(cursor)
    except pyodbc.Error:
        datos = panel_vacio(
            'No se pudo conectar con la base de datos. Revisa que SQL Server esté encendido.')
    finally:
        if conn is not None:
            conn.close()

    return render_template('dashboard.html', usuario=datos_usuario(),
                           vista_inicial='resumen', **datos)


@app.route('/dashboard/proveedor', methods=['POST'])
def dashboard_proveedor():
    if not es_personal():
        return redirect(url_for('login'))

    datos = {
        'nombre': limpiar(request.form.get('nombre')),
        'telefono': limpiar(request.form.get('telefono')),
        'correo': limpiar(request.form.get('correo')).lower(),
        'direccion': limpiar(request.form.get('direccion')),
    }

    errores = []
    if len(datos['nombre']) < 3:
        errores.append('El nombre del proveedor debe tener al menos 3 caracteres.')
    if datos['telefono'] and not TELEFONO_RE.match(datos['telefono']):
        errores.append('El teléfono del proveedor no tiene un formato válido.')
    if datos['correo'] and not CORREO_RE.match(datos['correo']):
        errores.append('El correo del proveedor no tiene un formato válido.')

    if errores:
        for mensaje in errores:
            flash(mensaje, 'error')
        return redirect(url_for('dashboard', _anchor='proveedores'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = crear_proveedor(cursor, datos)
        conn.commit()
        flash(f'Proveedor “{nombre}” registrado correctamente.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    except pyodbc.IntegrityError:
        flash('No se pudo registrar el proveedor: revisa los datos.', 'error')
    except pyodbc.Error:
        flash('No se pudo registrar el proveedor. Revisa la conexión con la base de datos.', 'error')
    finally:
        if conn is not None:
            conn.close()

    return redirect(url_for('dashboard', _anchor='proveedores'))


@app.route('/dashboard/producto', methods=['POST'])
def dashboard_producto():
    if not es_personal():
        return redirect(url_for('login'))

    datos = {
        'nombre': limpiar(request.form.get('nombre')),
        'descripcion': limpiar(request.form.get('descripcion')),
        'id_categoria': request.form.get('id_categoria'),
        'unidad': limpiar(request.form.get('unidad')).upper() or 'UNIDAD',
        'precio': request.form.get('precio'),
        'costo_compra': request.form.get('costo_compra'),
        'id_proveedor': request.form.get('id_proveedor'),
        'id_usuario': session.get('user_id'),
        'stock_minimo': request.form.get('stock_minimo'),
        'controla_vencimiento': request.form.get('controla_vencimiento') in ('1', 'on', 'true'),
    }

    archivo = request.files.get('imagen')
    try:
        validar_imagen(archivo)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('dashboard', _anchor='productos'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        resultado = crear_producto(cursor, datos)
        conn.commit()

        if archivo is not None and archivo.filename:
            try:
                guardar_imagen_producto(resultado['producto_id'], archivo)
            except (OSError, ValueError):
                flash('El producto se guardó, pero la imagen no se pudo almacenar.', 'error')

        flash(f"Producto “{resultado['nombre']}” agregado al catálogo.", 'success')
    except ValueError as exc:
        if conn is not None:
            conn.rollback()
        flash(str(exc), 'error')
    except pyodbc.IntegrityError:
        if conn is not None:
            conn.rollback()
        flash('No se pudo crear el producto: revisa los datos.', 'error')
    except pyodbc.Error:
        if conn is not None:
            conn.rollback()
        flash('No se pudo crear el producto. Revisa la conexión con la base de datos.', 'error')
    finally:
        if conn is not None:
            conn.close()

    return redirect(url_for('dashboard', _anchor='productos'))


@app.route('/dashboard/producto/<int:id_producto>/imagen', methods=['POST'])
def dashboard_producto_imagen(id_producto):
    if not es_personal():
        return redirect(url_for('login'))

    archivo = request.files.get('imagen')
    if archivo is None or not archivo.filename:
        flash('Selecciona una imagen para el producto.', 'error')
        return redirect(url_for('dashboard', _anchor='productos'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM PRODUCTO WHERE IdProducto = ?", (id_producto,))
        if not cursor.fetchone()[0]:
            raise ValueError('El producto seleccionado ya no existe.')

        guardar_imagen_producto(id_producto, archivo)
        flash('Imagen del producto actualizada.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    except OSError:
        flash('No se pudo guardar la imagen del producto.', 'error')
    except pyodbc.Error:
        flash('No se pudo actualizar la imagen. Revisa la conexión con la base de datos.', 'error')
    finally:
        if conn is not None:
            conn.close()

    return redirect(url_for('dashboard', _anchor='productos'))


@app.route('/dashboard/movimiento', methods=['POST'])
def dashboard_movimiento():
    if not es_personal():
        return redirect(url_for('login'))

    try:
        id_lote = int(request.form.get('id_lote') or 0)
        cantidad = int(request.form.get('cantidad') or 0)
    except ValueError:
        flash('La cantidad o el lote no son válidos.', 'error')
        return redirect(url_for('dashboard', _anchor='vencimientos'))

    tipo = limpiar(request.form.get('tipo')).upper()
    motivo = limpiar(request.form.get('motivo')) or 'Ajuste desde el panel'

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        resultado = registrar_movimiento(
            cursor, id_lote, tipo, cantidad, motivo, session['user_id'])
        conn.commit()
        flash(
            f"Movimiento registrado: {resultado['tipo'].title()} de "
            f"{resultado['cantidad']} unidades del lote {resultado['lote']} "
            f"({resultado['producto']}). Stock del lote: "
            f"{resultado['stock_anterior']} → {resultado['stock_nuevo']}.",
            'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    except pyodbc.Error:
        flash('No se pudo registrar el movimiento. Revisa la conexión con la base de datos.', 'error')
    finally:
        if conn is not None:
            conn.close()

    return redirect(url_for('dashboard', _anchor='vencimientos'))


@app.route('/dashboard/cita/<int:id_reserva>/estado', methods=['POST'])
def dashboard_cita_estado(id_reserva):
    if not es_personal():
        return jsonify({'error': 'No autorizado.'}), 403

    datos = request.get_json(silent=True) or request.form
    estado = limpiar(datos.get('estado')).upper()

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        resultado = actualizar_estado_cita(cursor, id_reserva, estado)
        conn.commit()
        return jsonify({
            'success': True,
            'id': id_reserva,
            'anterior': resultado['anterior'],
            'estado': resultado['nuevo'],
        })
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except pyodbc.Error:
        return jsonify({'error': 'No se pudo actualizar la cita.'}), 500
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/factura/<int:id_venta>')
def api_factura(id_venta):
    if not es_personal():
        return jsonify({'error': 'No autorizado.'}), 403

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        factura = obtener_factura(cursor, id_venta)
        if factura is None:
            return jsonify({'error': 'La factura no existe.'}), 404
        return jsonify(factura)
    except pyodbc.Error:
        return jsonify({'error': 'No se pudo cargar la factura.'}), 500
    finally:
        if conn is not None:
            conn.close()


# Rutas API (Backend para procesar formularios)
@app.route('/api/cliente', methods=['POST'])
def crear_cliente():
    if not es_personal():
        return jsonify({'success': False, 'error': 'No autorizado.'}), 403

    datos = request.get_json(silent=True) or {}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        columnas = columnas_cliente(cursor)

        campos = ['Nombre', 'Apellido', 'Cedula', 'Telefono']
        parametros = [limpiar(datos.get('nombre')), limpiar(datos.get('apellido')),
                      limpiar(datos.get('cedula')), limpiar(datos.get('tel'))]
        marcas = ['?', '?', '?', '?']

        correo = limpiar(datos.get('correo')).lower()
        direccion = limpiar(datos.get('direccion'))
        if correo and 'correo' in columnas:
            campos.append('Correo')
            parametros.append(correo)
            marcas.append('?')
        if direccion and 'direccion' in columnas:
            campos.append('Direccion')
            parametros.append(direccion)
            marcas.append('?')

        if columnas.get('notif'):
            campos.append(columnas['notif'])
            parametros.append(1)
            marcas.append('?')

        if not columnas.get('id_identity', True):
            cursor.execute("SELECT ISNULL(MAX(IdCliente), 0) + 1 FROM CLIENTE")
            campos.insert(0, 'IdCliente')
            parametros.insert(0, cursor.fetchone()[0])
            marcas.insert(0, '?')

        cursor.execute(f"""
            INSERT INTO CLIENTE ({', '.join(campos)})
            OUTPUT INSERTED.IdCliente
            VALUES ({', '.join(marcas)})
        """, parametros)
        nuevo_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'id': nuevo_id})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)})
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/mascota', methods=['POST'])
def crear_mascota():
    if not es_personal():
        return jsonify({'success': False, 'error': 'No autorizado.'}), 403

    datos = request.get_json(silent=True) or {}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Crear mascota (IdMascota puede ser IDENTITY o no según la base).
        columnas_mascota = columnas_tabla(cursor, 'MASCOTA')
        campos = ['Nombre', 'Especie', 'Raza', 'Sexo', 'IdCliente']
        parametros = [limpiar(datos.get('nombre')), limpiar(datos.get('especie')),
                      limpiar(datos.get('raza')) or 'Criollo', limpiar(datos.get('sexo')),
                      datos.get('duenoId')]
        marcas = ['?', '?', '?', '?', '?']

        color = limpiar(datos.get('color'))
        nacimiento = limpiar(datos.get('fecha_nacimiento'))
        senas = limpiar(datos.get('senas'))
        if color and 'color' in columnas_mascota:
            campos.append('Color'); parametros.append(color); marcas.append('?')
        if nacimiento and 'fechanacimiento' in columnas_mascota:
            campos.append('FechaNacimiento'); parametros.append(nacimiento); marcas.append('?')
        if senas and 'senasparticulares' in columnas_mascota:
            campos.append('SenasParticulares'); parametros.append(senas); marcas.append('?')

        if not columna_es_identidad(cursor, 'MASCOTA', 'IdMascota'):
            cursor.execute("SELECT ISNULL(MAX(IdMascota), 0) + 1 FROM MASCOTA")
            campos.insert(0, 'IdMascota'); parametros.insert(0, cursor.fetchone()[0]); marcas.insert(0, '?')

        cursor.execute(f"""
            INSERT INTO MASCOTA ({', '.join(campos)})
            OUTPUT INSERTED.IdMascota
            VALUES ({', '.join(marcas)})
        """, parametros)
        nueva_mascota_id = cursor.fetchone()[0]

        # 2. Expediente clínico: análisis de alergia se registra después por el veterinario.
        columnas_exp = columnas_tabla(cursor, 'EXPEDIENTE_CLINICO')
        col_estado = ('EstadoRegistro' if 'estadoregistro' in columnas_exp
                      else 'EstadoReg' if 'estadoreg' in columnas_exp else None)
        col_alergias = nombre_columna_alergias(cursor)

        campos = ['FechaApertura', col_alergias, 'IdMascota']
        parametros = [date.today(), '', nueva_mascota_id]
        marcas = ['?', '?', '?']
        if col_estado:
            campos.append(col_estado)
            parametros.append(valor_estado_expediente(cursor, col_estado))
            marcas.append('?')

        col_exp_id = columna_id(cursor, 'EXPEDIENTE_CLINICO', 'IdExpediente', 'IdExp')
        if not columna_es_identidad(cursor, 'EXPEDIENTE_CLINICO', col_exp_id):
            cursor.execute(f"SELECT ISNULL(MAX({col_exp_id}), 0) + 1 FROM EXPEDIENTE_CLINICO")
            campos.insert(0, col_exp_id); parametros.insert(0, cursor.fetchone()[0]); marcas.insert(0, '?')

        cursor.execute(f"""
            INSERT INTO EXPEDIENTE_CLINICO ({', '.join(campos)})
            VALUES ({', '.join(marcas)})
        """, parametros)

        conn.commit()
        return jsonify({'success': True, 'id': nueva_mascota_id})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)})
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/expediente/alergia', methods=['POST'])
def guardar_analisis_alergia():
    """Guarda el análisis de alergia en el expediente usando columnas existentes."""
    if not es_personal():
        return jsonify({'success': False, 'error': 'No autorizado.'}), 403

    datos = request.get_json(silent=True) or {}
    id_mascota = datos.get('id_mascota')
    tipo_examen = limpiar(datos.get('tipo_examen'))
    tipo_alergia = limpiar(datos.get('tipo_alergia'))
    animal = limpiar(datos.get('animal'))
    observaciones = limpiar(datos.get('observaciones'))

    if not id_mascota:
        return jsonify({'success': False, 'error': 'Selecciona un paciente válido.'}), 400
    if not (tipo_examen or tipo_alergia or observaciones):
        return jsonify({'success': False, 'error': 'Indica al menos el tipo de examen, el tipo de alergia o una observación.'}), 400

    partes = []
    if tipo_examen:
        partes.append(f'Tipo de examen: {tipo_examen}')
    if tipo_alergia:
        partes.append(f'Tipo de alergia: {tipo_alergia}')
    if animal:
        partes.append(f'Animal: {animal}')
    resumen = ' | '.join(partes)
    condiciones = resumen[:300] if resumen else ''
    obs_texto = observaciones[:500] if observaciones else ''

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM MASCOTA WHERE IdMascota = ?", (id_mascota,))
        if not cursor.fetchone()[0]:
            return jsonify({'success': False, 'error': 'La mascota seleccionada no existe.'}), 404

        cursor.execute("SELECT COUNT(*) FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (id_mascota,))
        if cursor.fetchone()[0]:
            cursor.execute("""
                UPDATE EXPEDIENTE_CLINICO
                SET CondicionesPreexistentes = ?, ObservacionesGenerales = ?
                WHERE IdMascota = ?
            """, (condiciones, obs_texto, id_mascota))
        else:
            # Crear expediente si no existe (usa columnas disponibles).
            columnas_exp = columnas_tabla(cursor, 'EXPEDIENTE_CLINICO')
            col_estado = ('EstadoRegistro' if 'estadoregistro' in columnas_exp
                          else 'EstadoReg' if 'estadoreg' in columnas_exp else None)
            col_alergias = nombre_columna_alergias(cursor)
            campos = ['FechaApertura', col_alergias, 'CondicionesPreexistentes', 'ObservacionesGenerales', 'IdMascota']
            parametros = [date.today(), '', condiciones, obs_texto, id_mascota]
            marcas = ['?', '?', '?', '?', '?']
            if col_estado:
                campos.append(col_estado)
                parametros.append(valor_estado_expediente(cursor, col_estado))
                marcas.append('?')
            col_exp_id = columna_id(cursor, 'EXPEDIENTE_CLINICO', 'IdExpediente', 'IdExp')
            if not columna_es_identidad(cursor, 'EXPEDIENTE_CLINICO', col_exp_id):
                cursor.execute(f"SELECT ISNULL(MAX({col_exp_id}), 0) + 1 FROM EXPEDIENTE_CLINICO")
                campos.insert(0, col_exp_id); parametros.insert(0, cursor.fetchone()[0]); marcas.insert(0, '?')
            cursor.execute(f"""
                INSERT INTO EXPEDIENTE_CLINICO ({', '.join(campos)})
                VALUES ({', '.join(marcas)})
            """, parametros)

        conn.commit()
        return jsonify({'success': True, 'resumen': resumen, 'condiciones': condiciones})
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        return jsonify({'success': False, 'error': str(exc)})
    finally:
        if conn is not None:
            conn.close()


@app.errorhandler(413)
def archivo_demasiado_grande(error):
    destino = request.referrer or url_for('dashboard', _anchor='productos')
    flash('El archivo es demasiado grande. Límite general: 55 MB (imágenes de producto: 6 MB).', 'error')
    return redirect(destino)


if __name__ == '__main__':
    app.run(debug=True, port=5000)