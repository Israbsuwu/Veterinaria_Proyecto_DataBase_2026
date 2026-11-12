from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import pyodbc

app = Flask(__name__)
app.secret_key = 'pepe_pepito_secreto' 
DB_SERVER = r'MSI\SQLEXPRESS' 
DB_NAME = 'VetPepePepito'

def get_db_connection():
    conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};Trusted_Connection=yes;'
    return pyodbc.connect(conn_str)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT U.IdUsuario, U.Nombre, U.Correo, R.NombreRol 
            FROM USUARIO U INNER JOIN ROL R ON U.IdRol = R.IdRol
            WHERE U.Correo = ? AND U.Contrasena = ? AND U.Estado = 'Activo'
        """, (correo, contrasena))
        usuario = cursor.fetchone()
        conn.close()
        
        if usuario:
            session['user_id'] = usuario.IdUsuario
            session['user_nombre'] = usuario.Nombre
            session['user_rol'] = usuario.NombreRol
            return redirect(url_for('index'))
        else:
            flash('Correo o contraseña incorrectos.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Traer TODOS los Clientes reales de la BD
    cursor.execute("SELECT IdCliente, Nombre, Apellido, Cedula, Telefono FROM CLIENTE")
    clientes = [{'id': c.IdCliente, 'nombre': c.Nombre, 'apellido': c.Apellido, 'cedula': c.Cedula, 'tel': c.Telefono} for c in cursor.fetchall()]
    
    # 2. Traer TODAS las Mascotas reales de la BD
    cursor.execute("""
        SELECT M.IdMascota, M.Nombre, M.Especie, M.Raza, M.Sexo, M.IdCliente, E.Alergias 
        FROM MASCOTA M
        LEFT JOIN EXPEDIENTE_CLINICO E ON M.IdMascota = E.IdMascota
    """)
    mascotas = [{
        'id': m.IdMascota, 'duenoId': m.IdCliente, 'nombre': m.Nombre, 
        'especie': m.Especie, 'raza': m.Raza, 'sexo': m.Sexo, 
        'alergias': m.Alergias if m.Alergias else ''
    } for m in cursor.fetchall()]
    
    conn.close()
    
    # Le inyectamos los datos a la página
    return render_template('index.html', clientes=clientes, mascotas=mascotas)

# Rutas API (Backend para procesar formularios)
@app.route('/api/cliente', methods=['POST'])
def crear_cliente():
    datos = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Guardar en BD y devolver el nuevo ID autogenerado
        cursor.execute("""
            INSERT INTO CLIENTE (Nombre, Apellido, Cedula, Telefono, AceptaNotif)
            OUTPUT INSERTED.IdCliente
            VALUES (?, ?, ?, ?, 1)
        """, (datos['nombre'], datos['apellido'], datos['cedula'], datos['tel']))
        nuevo_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'id': nuevo_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/api/mascota', methods=['POST'])
def crear_mascota():
    datos = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Crear mascota
        cursor.execute("""
            INSERT INTO MASCOTA (Nombre, Especie, Raza, Sexo, IdCliente)
            OUTPUT INSERTED.IdMascota
            VALUES (?, ?, ?, ?, ?)
        """, (datos['nombre'], datos['especie'], datos['raza'], datos['sexo'], datos['duenoId']))
        nueva_mascota_id = cursor.fetchone()[0]
        
        # 2. Abrir automáticamente su expediente clínico y guardar alergias
        alergias_input = datos.get('alergias', '')
        cursor.execute("""
            INSERT INTO EXPEDIENTE_CLINICO (FechaApertura, EstadoReg, Alergias, IdMascota)
            VALUES (GETDATE(), 'Activo', ?, ?)
        """, (alergias_input, nueva_mascota_id))
        
        conn.commit()
        return jsonify({'success': True, 'id': nueva_mascota_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)