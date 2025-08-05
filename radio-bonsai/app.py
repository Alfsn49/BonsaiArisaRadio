from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anime-radio-secret'
# ✅ SOLO UNA INSTANCIA DE SocketIO, ya configurada
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

DB_PATH = 'pedidos.db'

def init_db():
    if os.path.exists('pedidos.db'):
        os.remove('pedidos.db')  # Elimina el archivo anterior

    with sqlite3.connect('pedidos.db') as conn:
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

# Llamamos a init_db aquí para que se ejecute al importar el módulo,
# es decir, cuando Gunicorn o cualquier otro servidor arranque la app
init_db()

@app.route('/')
def index():
    with sqlite3.connect('pedidos.db') as conn:
        pedidos = conn.execute(
            'SELECT nombre, cancion, dedicatoria, artista, fecha_hora FROM pedidos ORDER BY id DESC'
        ).fetchall()

    ruta_imgs = os.path.join(app.static_folder, 'img')
    imagenes = [f'img/{img}' for img in sorted(os.listdir(ruta_imgs)) if img.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    return render_template('index.html', pedidos=pedidos, imagenes=imagenes)

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
    }, broadcast=True)
    return '', 204

if __name__ == '__main__':
    # Solo se ejecuta si arrancas la app con python app.py directamente (útil para desarrollo)
    socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')
