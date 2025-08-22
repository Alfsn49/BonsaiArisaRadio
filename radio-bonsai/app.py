import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anime-radio-secret'
# ✅ SOLO UNA INSTANCIA DE SocketIO, ya configurada
CORS(app)
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   logger=True,
                   engineio_logger=False,  # Desactiva en producción
                   ping_timeout=60,
                   ping_interval=25)

DB_PATH = 'pedidos.db'

def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)  # Borra la DB anterior (solo desarrollo)

    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        conn.execute('''
            CREATE TABLE pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                cancion TEXT,
                dedicatoria TEXT,
                artista TEXT,
                fecha_hora TEXT
            )
        ''')

        conn.execute('''
            CREATE TABLE comentarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                mensaje TEXT,
                fecha_hora TEXT
            )
        ''')

# Llamamos a init_db aquí para que se ejecute al importar el módulo,
# es decir, cuando Gunicorn o cualquier otro servidor arranque la app
init_db()

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row  # ✅ Esto hace que fetchall devuelva diccionarios

        pedidos = conn.execute(
            'SELECT nombre, cancion, dedicatoria, artista, fecha_hora FROM pedidos ORDER BY id DESC'
        ).fetchall()

        comentarios = conn.execute(
            'SELECT nombre, mensaje, fecha_hora FROM comentarios ORDER BY id DESC'
        ).fetchall()

    ruta_imgs = os.path.join(app.static_folder, 'img')
    imagenes = [f'img/{img}' for img in sorted(os.listdir(ruta_imgs)) if img.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    # Convertir Row objects a diccionarios normales
    pedidos = [dict(p) for p in pedidos]
    comentarios = [dict(c) for c in comentarios]

    return render_template('index.html', pedidos=pedidos, comentarios=comentarios, imagenes=imagenes)

@app.route('/pedido', methods=['POST'])
def pedido():
    nombre = request.form['nombre']
    cancion = request.form['cancion']
    dedicatoria = request.form.get('dedicatoria', '')
    artista = request.form.get('artista', '')
    fecha_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with sqlite3.connect('pedidos.db') as conn:
        conn.execute(
            'INSERT INTO pedidos (nombre, cancion, dedicatoria, artista, fecha_hora) VALUES (?, ?, ?, ?, ?)',
            (nombre, cancion, dedicatoria, artista, fecha_hora)
        )
        conn.commit()

    socketio.emit('nuevo_pedido', {
    'nombre': nombre,
    'cancion': cancion,
    'dedicatoria': dedicatoria,
    'artista': artista,
    'fecha_hora': fecha_hora
}, to=None)
    return '', 204

@app.route('/comentario', methods=['POST'])
def comentario():
    nombre = request.form['nombre']
    mensaje = request.form['mensaje']
    fecha_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            'INSERT INTO comentarios (nombre, mensaje, fecha_hora) VALUES (?, ?, ?)',
            (nombre, mensaje, fecha_hora)
        )
        conn.commit()

    socketio.emit('nuevo_comentario', {
        'nombre': nombre,
        'mensaje': mensaje,
        'fecha_hora': fecha_hora
    }, to=None)
    return '', 204

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000)  # Solo para desarrollo local
