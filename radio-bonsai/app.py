from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anime-radio-secret'
socketio = SocketIO(app)

# 🗃️ Base de datos: crear si no existe
def init_db():
    if not os.path.exists('pedidos.db'):
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

@app.route('/')
def index():
    with sqlite3.connect('pedidos.db') as conn:
        pedidos = conn.execute(
            'SELECT nombre, cancion, dedicatoria, artista, fecha_hora FROM pedidos ORDER BY id DESC'
        ).fetchall()
     
    # Leer las imágenes del slider desde static/img
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
    })
    return '', 204


if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
