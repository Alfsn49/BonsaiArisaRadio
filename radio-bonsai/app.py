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

    # ruta_imgs = os.path.join(app.static_folder, 'img')
    # imagenes = [f'img/{img}' for img in sorted(os.listdir(ruta_imgs)) if img.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    imagenes = [
        "https://cdn.donmai.us/sample/ff/5c/__yuel_granblue_fantasy_drawn_by_ma_ma_gobu__sample-ff5c88a1fbe0268b4a541066eeec2283.jpg",
        "https://cdn.donmai.us/sample/f9/b1/__aoba_moca_bang_dream_drawn_by_junji_17__sample-f9b134acb411baf52613e5e95d7fd9db.jpg",
        "https://cdn.donmai.us/sample/66/a9/__mitake_ran_and_aoba_moca_bang_dream_drawn_by_kiska_mnvy2332__sample-66a950c752fbd4e0d533860a1ce4e683.jpg",
        "https://cdn.donmai.us/sample/d9/5f/__takafuji_kako_idolmaster_and_1_more_drawn_by_east01_06__sample-d95f9166bfb0e74dad8dda3c78713cff.jpg",
        "https://cdn.donmai.us/sample/1a/2d/__imai_lisa_bang_dream_drawn_by_nanami_nunnun_0410__sample-1a2d352075e446d7bb5b5e196cad8e5b.jpg",
        "https://cdn.donmai.us/original/d9/5e/__togawa_sakiko_bang_dream_and_1_more_drawn_by_kanpozhan__d95e5564729dd925a4bcba4433f58159.png",
        "https://cdn.donmai.us/sample/40/d3/__nagasaki_soyo_bang_dream_and_1_more_drawn_by_e20__sample-40d39c975e1462533dc075b45e2eea90.jpg",
    ]

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
