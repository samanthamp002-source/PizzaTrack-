import sqlite3
import os
import tempfile  # Integrado para manejar rutas seguras en Linux/Servidores
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'pizzatrack_secret_key'

# ==========================================
#  CONFIGURACIÓN DE RUTA ABSOLUTA PARA SQLITE
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.name == 'nt':  # Si estás ejecutando en Windows (Tu computadora local)
    DB_PATH = os.path.join(BASE_DIR, 'pizzatrack_v4.db')
else:  # Si se ejecuta en un servidor Linux de producción (Render, Railway, VPS)
    # Conserva la persistencia unificando la ruta absoluta del directorio del proyecto
    DB_PATH = os.path.join(BASE_DIR, 'pizzatrack_v4.db')

print(f"📌 Base de datos activa y protegida en la ruta: {DB_PATH}")

# Diccionario con los dos turnos autorizados para el sistema
ADMIN_TURNS = {
    "cajero_matutino": {
        "pass": "turno123", 
        "nombre_completo": "Trabajador (Turno Matutino)"
    },
    "cajero_vespertino": {
        "pass": "turno456", 
        "nombre_completo": "Trabajador (Turno Vespertino)"
    }
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombres TEXT NOT NULL,
                correo TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                tamano TEXT,
                ingredientes TEXT,
                total REAL,
                fecha TEXT, 
                estado TEXT DEFAULT 'Preparando',
                metodo_pago TEXT DEFAULT 'Ninguno',
                progreso INTEGER DEFAULT 0,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
        ''')
        try:
            conn.execute('ALTER TABLE pedidos ADD COLUMN progreso INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute('ALTER TABLE pedidos ADD COLUMN metodo_pago TEXT DEFAULT "Ninguno"')
        except sqlite3.OperationalError:
            pass
        conn.commit()

# ESTA LÍNEA ASEGURA QUE LA BD SE INSTANCIE AUTOMÁTICAMENTE EN PRODUCCIÓN
init_db()

@app.route('/')
def bienvenida(): 
    return render_template('bienvenida.html')

# ==========================================
#          AUTENTICACIÓN ADMINISTRATIVA
# ==========================================

@app.route('/login_pizzero', methods=['GET', 'POST'])
def login_pizzero():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        contrasena = request.form.get('password') 
        
        # Validamos si el usuario ingresado existe en nuestro diccionario de turnos
        if usuario in ADMIN_TURNS and contrasena == ADMIN_TURNS[usuario]["pass"]:
            session['admin_autenticado'] = True
            # Guardamos dinámicamente el nombre del turno que ingresó
            session['admin_user'] = ADMIN_TURNS[usuario]["nombre_completo"]
            
            # Limpiamos explícitamente mensajes viejos para evitar alertas en cascada
            session.pop('_flashes', None) 
            return redirect(url_for('pizzero'))
        else:
            session.pop('_flashes', None) # Limpieza previa
            flash('Usuario o contraseña de turno incorrectos.', 'danger')
            return redirect(url_for('login_pizzero'))
            
    return render_template('login_pizzero.html')

@app.route('/logout_pizzero')
def logout_pizzero():
    session.pop('admin_autenticado', None)
    session.pop('admin_user', None)
    session.pop('_flashes', None)
    return redirect(url_for('login_pizzero'))

# ==========================================
#          AUTENTICACIÓN CLIENTES
# ==========================================

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        # LIMPIEZA CLAVE: Evita que se acumulen errores anteriores en la sesión
        session.pop('_flashes', None)
        
        # Corrección de mapeo inteligente: lee tanto en singular (HTML) como en plural
        nom = request.form.get('nombre') or request.form.get('nombres')
        ape = request.form.get('apellido') or request.form.get('apellidos')
        cor = request.form.get('correo')
        pas = request.form.get('password')
        conf_pas = request.form.get('confirm_password')
        
        # Limpiamos espacios en blanco accidentales antes de validar
        if nom: nom = nom.strip()
        if ape: ape = ape.strip()
        if cor: cor = cor.strip()

        if not all([nom, ape, cor, pas, conf_pas]):
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template('registro.html')
            
        if pas != conf_pas:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('registro.html')
            
        # Validación estricta que respalda las indicaciones del HTML
        if len(pas) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
            return render_template('registro.html')
        if not re.search(r"[A-Z]", pas):
            flash('La contraseña debe incluir al menos una letra mayúscula.', 'danger')
            return render_template('registro.html')
        if not re.search(r"[0-9]", pas):
            flash('La contraseña debe incluir al menos un número.', 'danger')
            return render_template('registro.html')
            
        try:
            with get_db_connection() as conn:
                # Se unifican el nombre y apellido en el campo único 'nombres' de la tabla usuarios
                nombre_completo = f"{nom} {ape}"
                conn.execute('INSERT INTO usuarios (nombres, correo, password) VALUES (?,?,?)', 
                             (nombre_completo, cor, generate_password_hash(pas)))
                conn.commit()
            
            # Limpiamos antes de mandar el mensaje de éxito al login
            session.pop('_flashes', None)
            flash('¡Cuenta creada con éxito! Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Este correo electrónico ya está registrado.', 'danger')
        except Exception as e:
            print(f"Error en BD Registro: {e}")
            flash('Error al registrar en la base de datos.', 'danger')
            
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session.pop('_flashes', None) # Limpieza para que no se sumen errores antiguos
        c = request.form.get('correo')
        p = request.form.get('password')
        
        if not c or not p:
            flash('Por favor, llena todos los campos.', 'danger')
            return render_template('login.html')
            
        with get_db_connection() as conn:
            user = conn.execute('SELECT * FROM usuarios WHERE correo = ?', (c,)).fetchone()
            
        if user and check_password_hash(user['password'], p):
            session.update({'user_id': user['id'], 'nombre': user['nombres']})
            session.pop('_flashes', None)
            return redirect(url_for('index'))
            
        flash('El correo electrónico o la contraseña son incorrectos.', 'danger')
        
    return render_template('login.html')

@app.route('/index')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('index.html', nombre=session.get('nombre'))

@app.route('/ordenar', methods=['POST'])
def ordenar():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    detalle_completo = request.form.get('ingredientes')
    sz_index = request.form.get('size')
    
    try:
        tamanos = ["Chica", "Mediana", "Grande"]
        tamano_txt = tamanos[int(sz_index)] if sz_index else "N/A"
        
        total_final = 0.0
        if detalle_completo:
            items = detalle_completo.split('|')
            for item in items:
                if ':' in item:
                    try:
                        total_final += float(item.split(':')[1])
                    except ValueError:
                        pass

        fecha_completa = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO pedidos (usuario_id, tamano, ingredientes, total, fecha, estado, metodo_pago, progreso) 
                VALUES (?,?,?,?,?,?,?,1)
            ''', (
                session['user_id'], 
                tamano_txt, 
                detalle_completo, 
                total_final, 
                fecha_completa, 
                'Preparando', 
                'Ninguno'
            ))
            conn.commit()
        return redirect(url_for('carrito'))
    except Exception as e:
        print(f"Error al ordenar: {e}")
        return redirect(url_for('index'))

@app.route('/carrito')
def carrito():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
        
    try:
        with get_db_connection() as conn:
            compras = conn.execute('SELECT * FROM pedidos WHERE usuario_id = ? ORDER BY id DESC', (session['user_id'],)).fetchall()
            
            total_carrito = sum(
                float(compra['total'] if compra['total'] else 0) for compra in compras 
                if compra['estado'] not in ['Pagado', 'Entregado', 'Archivado']
            )
            
        return render_template('carrito.html', compras=compras, total_carrito=total_carrito, nombre=session.get('nombre'))
    except Exception as e:
        print(f"Error crítico en la vista del carrito: {e}")
        return redirect(url_for('index'))

@app.route('/eliminar_pedido/<int:id>', methods=['GET', 'POST'])
def eliminar_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        session.pop('_flashes', None)
        with get_db_connection() as conn:
            conn.execute('DELETE FROM pedidos WHERE id = ? AND usuario_id = ?', (id, session['user_id']))
            conn.commit()
        flash('Orden eliminada correctamente.', 'success')
    except Exception as e:
        flash('No se pudo eliminar la orden.', 'danger')
    return redirect(url_for('carrito'))

# ==========================================
#          PANEL ADMINISTRATIVO (PIZZERO)
# ==========================================

@app.route('/pizzero')
def pizzero():
    if not session.get('admin_autenticado'):
        return redirect(url_for('login_pizzero'))

    fecha_filtro = request.args.get('fecha_historial')
    if not fecha_filtro:
        fecha_filtro = datetime.now().strftime('%Y-%m-%d')

    with get_db_connection() as conn:
        pedidos = conn.execute('''
            SELECT p.*, u.nombres AS cliente_nombre 
            FROM pedidos p
            INNER JOIN usuarios u ON p.usuario_id = u.id
            WHERE p.fecha LIKE ? AND p.estado != 'Archivado'
            ORDER BY 
                CASE p.estado
                    WHEN 'Preparando' THEN 1
                    WHEN 'Casi Lista' THEN 2
                    WHEN 'Lista' THEN 3
                    WHEN 'Pagado' THEN 4
                    WHEN 'Entregado' THEN 5
                    ELSE 6
                END ASC, 
                p.id DESC
        ''', (f"{fecha_filtro}%",)).fetchall()
        
        corte_general = 0.0
        recaudado_tarjeta = 0.0
        recaudado_efectivo = 0.0
        ordenes_en_cocina = 0
        
        for p in pedidos:
            if p['estado'] in ['Preparando', 'Casi Lista', 'Lista']:
                ordenes_en_cocina += 1
                
            if p['estado'] in ['Pagado', 'Entregado']:
                val_total = float(p['total'] if p['total'] else 0)
                corte_general += val_total
                if p['metodo_pago'] == 'Tarjeta':
                    recaudado_tarjeta += val_total
                elif p['metodo_pago'] == 'Efectivo':
                    recaudado_efectivo += val_total

    return render_template(
        'pizzero.html', 
        pedidos=pedidos, 
        total_dia=corte_general,
        tarjeta=recaudado_tarjeta,
        efectivo=recaudado_efectivo,
        activas=ordenes_en_cocina,
        fecha_actual=fecha_filtro
    )

@app.route('/cambiar_estado/<int:id>/<nuevo_estado>')
def cambiar_estado(id, nuevo_estado):
    if not session.get('admin_autenticado'):
        return redirect(url_for('login_pizzero'))

    progreso_map = {
        'Preparando': 1,
        'Casi Lista': 2,
        'Lista': 3,
        'Entregado': 5
    }
    
    with get_db_connection() as conn:
        if nuevo_estado in ['Pago Efectivo', 'Pago Tarjeta']:
            real_metodo = 'Tarjeta' if nuevo_estado == 'Pago Tarjeta' else 'Efectivo'
            conn.execute('UPDATE pedidos SET estado = "Pagado", metodo_pago = ?, progreso = 4 WHERE id = ?', (real_metodo, id))
        else:
            progreso_val = progreso_map.get(nuevo_estado, 1)
            conn.execute('UPDATE pedidos SET estado = ?, progreso = ? WHERE id = ?', (nuevo_estado, progreso_val, id))
        conn.commit()
    return redirect(url_for('pizzero'))

@app.route('/admin/eliminar_orden/<int:id>', methods=['POST'])
def admin_eliminar_orden(id):
    if not session.get('admin_autenticado'):
        return jsonify({"success": False, "error": "No autorizado"}), 403
    try:
        with get_db_connection() as conn:
            conn.execute('DELETE FROM pedidos WHERE id = ?', (id,))
            conn.commit()
        return jsonify({"success": True, "message": f"Orden #{id} removida."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/pagar/<int:pedido_id>')
def pagar(pedido_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    with get_db_connection() as conn:
        pedido = conn.execute('SELECT * FROM pedidos WHERE id = ?', (pedido_id,)).fetchone()
    if not pedido:
        return redirect(url_for('carrito'))
    return render_template('pagar.html', pedido=pedido)

@app.route('/procesar_pago', methods=['POST'])
def procesar_pago():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    pedido_id = request.form.get('pedido_id')
    metodo = request.form.get('metodo_pago')
    
    with get_db_connection() as conn:
        if not pedido_id or pedido_id == "":
            ultimo_pedido = conn.execute(
                'SELECT id FROM pedidos WHERE usuario_id = ? ORDER BY id DESC LIMIT 1', 
                (session['user_id'],)
            ).fetchone()
            if ultimo_pedido:
                pedido_id = ultimo_pedido['id']
        
        metodo_db = 'Tarjeta' if metodo == 'tarjeta' else 'Efectivo'
        conn.execute('UPDATE pedidos SET estado = "Pagado", metodo_pago = ?, progreso = 4 WHERE id = ?', (metodo_db, pedido_id))
        conn.commit()
            
    return redirect(url_for('seguimiento'))

@app.route('/seguimiento')
def seguimiento():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
        
    try:
        with get_db_connection() as conn:
            pedidos = conn.execute('''
                SELECT * FROM pedidos 
                WHERE usuario_id = ? AND estado NOT IN ('Archivado')
                ORDER BY id DESC
            ''', (session['user_id'],)).fetchall()
            
        return render_template('seguimiento.html', pedidos=pedidos, nombre=session.get('nombre'))
    except Exception as e:
        print(f"Error asíncrono en seguimiento: {e}")
        return redirect(url_for('index'))

# ==========================================
#          CORTE Y REPORTE DE CAJA
# ==========================================

@app.route('/realizar_corte', methods=['POST'])
def realizar_corte():
    if not session.get('admin_autenticado'):
        return redirect(url_for('login_pizzero'))

    fecha_corte = request.form.get('fecha_corte')
    if not fecha_corte:
        fecha_corte = datetime.now().strftime('%Y-%m-%d')
        
    try:
        session.pop('_flashes', None)
        with get_db_connection() as conn:
            totales = conn.execute('''
                SELECT 
                    SUM(total) as general,
                    SUM(CASE WHEN metodo_pago = 'Tarjeta' THEN total ELSE 0 END) as tarjeta,
                    SUM(CASE WHEN metodo_pago = 'Efectivo' THEN total ELSE 0 END) as efectivo,
                    COUNT(id) as total_ordenes
                FROM pedidos
                WHERE fecha LIKE ? AND estado IN ('Pagado', 'Entregado')
            ''', (f"{fecha_corte}%",)).fetchone()
            
            if not totales or totales['general'] is None or totales['general'] == 0:
                flash('No existen ventas liquidadas para realizar un corte en esta fecha.', 'warning')
                return redirect(url_for('pizzero'))
                
            conn.execute('''
                UPDATE pedidos 
                SET estado = 'Archivado' 
                WHERE fecha LIKE ? AND estado IN ('Pagado', 'Entregado')
            ''', (f"{fecha_corte}%",))
            
            conn.commit()
            
        return redirect(url_for('reporte_corte', 
                                fecha=fecha_corte, 
                                total=totales['general'], 
                                tarjeta=totales['tarjeta'], 
                                efectivo=totales['efectivo'],
                                ordenes=totales['total_ordenes']))
    except Exception as e:
        print(f"Error crítico en corte de caja: {e}")
        flash('Error interno al intentar procesar el corte.', 'danger')
        return redirect(url_for('pizzero'))

@app.route('/reporte_corte')
def reporte_corte():
    if not session.get('admin_autenticado'):
        return redirect(url_for('login_pizzero'))

    datos_reporte = {
        'fecha': request.args.get('fecha'),
        'total': float(request.args.get('total', 0)),
        'tarjeta': float(request.args.get('tarjeta', 0)),
        'efectivo': float(request.args.get('efectivo', 0)),
        'ordenes': request.args.get('ordenes', 0),
        'atendido_por': session.get('admin_user', 'Trabajador General')
    }
    return render_template('reporte_corte.html', reporte=datos_reporte)

if __name__ == '__main__':
    app.run(debug=True)