import eventlet
eventlet.monkey_patch()

# Parche para psycopg2 y Eventlet (evita bloqueo en mainloop)
from psycogreen.eventlet import patch_psycopg
patch_psycopg()

from flask import Flask, render_template, request
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_mail import Mail, Message
import sqlite3
import os
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import uuid


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
ENV = os.getenv("FLASK_ENV", "production")  # producción por defecto

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anime-radio-secret'
# Configuración de correo (ejemplo con Gmail)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')  # tu correo
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS')   # contraseña de aplicación
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)

CORS(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25
)

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def get_sqlite_connection():
    conn = sqlite3.connect("pedidos.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- INIT DB ---
def init_db():
    # --- Postgres ---
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES usuarios(id),
                    token TEXT UNIQUE NOT NULL,
                    expiracion TIMESTAMP NOT NULL
                )
            """)
            conn.commit()

    # --- SQLite ---
    with get_sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                cancion TEXT NOT NULL,
                dedicatoria TEXT,
                artista TEXT,
                fecha_hora TIMESTAMP NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS comentarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                fecha_hora TIMESTAMP NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_fecha ON pedidos(fecha_hora DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comentarios_fecha ON comentarios(fecha_hora DESC)")
        cur.execute("DELETE FROM pedidos WHERE fecha_hora < datetime('now','-7 day')")
        cur.execute("DELETE FROM comentarios WHERE fecha_hora < datetime('now','-7 day')")
        conn.commit()

init_db()

# --- HORA LOCAL ---
def obtener_hora_local(fecha_utc, tz_str='America/Guayaquil'):
    tz = pytz.timezone(tz_str)
    return fecha_utc.astimezone(tz)

# --- RUTAS ---
@app.route('/')
def index():
    # pedidos y comentarios vienen de SQLite
    with get_sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT nombre, cancion, dedicatoria, artista, fecha_hora FROM pedidos ORDER BY fecha_hora DESC LIMIT 150")
        pedidos = [
            {
                "nombre": r["nombre"],
                "cancion": r["cancion"],
                "dedicatoria": r["dedicatoria"],
                "artista": r["artista"],
                "fecha_hora": r["fecha_hora"]
            } for r in cur.fetchall()
        ]

        cur.execute("SELECT nombre, mensaje, fecha_hora FROM comentarios ORDER BY fecha_hora DESC LIMIT 150")
        comentarios = [
            {
                "nombre": r["nombre"],
                "mensaje": r["mensaje"],
                "fecha_hora": r["fecha_hora"]
            } for r in cur.fetchall()
        ]

    # las imágenes siguen igual
    imagenes = [
        "https://cdn.donmai.us/sample/ff/5c/__yuel_granblue_fantasy_drawn_by_ma_ma_gobu__sample-ff5c88a1fbe0268b4a541066eeec2283.jpg",
        "https://cdn.donmai.us/sample/f9/b1/__aoba_moca_bang_dream_drawn_by_junji_17__sample-f9b134acb411baf52613e5e95d7fd9db.jpg",
        "https://cdn.donmai.us/sample/66/a9/__mitake_ran_and_aoba_moca_bang_dream_drawn_by_kiska_mnvy2332__sample-66a950c752fbd4e0d533860a1ce4e683.jpg",
        "https://cdn.donmai.us/sample/d9/5f/__takafuji_kako_idolmaster_and_1_more_drawn_by_east01_06__sample-d95f9166bfb0e74dad8dda3c78713cff.jpg",
        "https://cdn.donmai.us/sample/1a/2d/__imai_lisa_bang_dream_drawn_by_nanami_nunnun_0410__sample-1a2d352075e446d7bb5b5e196cad8e5b.jpg",
        "https://cdn.donmai.us/original/d9/5e/__togawa_sakiko_bang_dream_and_1_more_drawn_by_kanpozhan__d95e5564729dd925a4bcba4433f58159.png",
        "https://cdn.donmai.us/sample/40/d3/__nagasaki_soyo_bang_dream_and_1_more_drawn_by_e20__sample-40d39c975e1462533dc075b45e2eea90.jpg",
    ]
    return render_template('index.html', pedidos=pedidos, comentarios=comentarios, imagenes=imagenes)


# --- Registro/Login ---
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return {"error": "No se recibieron datos"}, 400

    username = data.get('username')
    email = data.get('email', '').lower()
    password = data.get('password')
    if not username or not email or not password:
        return {"error": "Faltan campos"}, 400

    hashed_password = generate_password_hash(password)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usuarios (username, email, password) VALUES (%s, %s, %s)",
                    (username, email, hashed_password)
                )
                conn.commit()
        return {"message": "Usuario registrado con éxito", "usuario": {"username": username, "email": email}}, 201
    except psycopg2.Error:
        return {"error": "El email ya está registrado o hubo un problema"}, 400

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return {"error": "No se recibieron datos"}, 400

    username = data.get('username', '')
    password = data.get('password')

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, email, password FROM usuarios WHERE username = %s", (username,))
            user = cur.fetchone()

    if user and check_password_hash(user[3], password):
        return {"message": "Login exitoso", "usuario": {"id": user[0], "username": user[1], "email": user[2]}}, 200
    return {"error": "Credenciales incorrectas"}, 401

def send_async_email(msg):
    with app.app_context():
        mail.send(msg)

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email', '').lower()
    if not email:
        return {"error": "Se requiere el email"}, 400

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                return {"error": "Usuario no encontrado"}, 404

            token = str(uuid.uuid4())
            expiracion = datetime.utcnow() + timedelta(minutes=30)

            cur.execute(
                "INSERT INTO reset_tokens (user_id, token, expiracion) VALUES (%s, %s, %s)",
                (user[0], token, expiracion)
            )
            conn.commit()

    reset_link = f"https://bonsaiarisaradio.onrender.com/recuperacion?token={token}"
    html_body = f"<p>Haz click en el enlace para cambiar tu contraseña (válido 30 min):</p><a href='{reset_link}'>{reset_link}</a>"

    msg = Message("Recuperación de contraseña", sender=app.config['MAIL_USERNAME'], recipients=[email])
    msg.html = html_body

    # Spawn para enviar sin bloquear
    eventlet.spawn(send_async_email, msg)

    return {"message": "Correo de recuperación enviado"}


@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('password')

    if not token or not new_password:
        return {"error": "Faltan campos"}, 400

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, expiracion FROM reset_tokens WHERE token = %s", (token,))
            token_data = cur.fetchone()
            if not token_data:
                return {"error": "Token inválido"}, 400
            if datetime.utcnow() > token_data[1]:
                return {"error": "Token expirado"}, 400

            hashed_password = generate_password_hash(new_password)
            cur.execute("UPDATE usuarios SET password = %s WHERE id = %s", (hashed_password, token_data[0]))
            cur.execute("DELETE FROM reset_tokens WHERE token = %s", (token,))
            conn.commit()

    return {"message": "Contraseña actualizada con éxito"}



# --- Pedidos/Comentarios ---
@app.route('/pedido', methods=['POST'])
def pedido():
    nombre = request.form['nombre']
    cancion = request.form['cancion']
    dedicatoria = request.form.get('dedicatoria', '')
    artista = request.form.get('artista', '')
    fecha_hora = datetime.utcnow()

    with get_sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pedidos (nombre, cancion, dedicatoria, artista, fecha_hora) VALUES (?, ?, ?, ?, ?)",
            (nombre, cancion, dedicatoria, artista, fecha_hora)
        )
        conn.commit()

    socketio.emit('nuevo_pedido', {
        'nombre': nombre, 'cancion': cancion, 'dedicatoria': dedicatoria,
        'artista': artista, 'fecha_hora': fecha_hora.strftime('%Y-%m-%d %H:%M:%S')
    })
    return '', 204

@app.route('/comentario', methods=['POST'])
def comentario():
    nombre = request.form['nombre']
    mensaje = request.form['mensaje']
    fecha_hora = datetime.utcnow()

    with get_sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO comentarios (nombre, mensaje, fecha_hora) VALUES (?, ?, ?)",
            (nombre, mensaje, fecha_hora)
        )
        conn.commit()

    socketio.emit('nuevo_comentario', {
        'nombre': nombre, 'mensaje': mensaje,
        'fecha_hora': fecha_hora.strftime('%Y-%m-%d %H:%M:%S')
    })
    return '', 204


@app.route('/recuperacion')
def about():
    imagen_url = "https://cdn.donmai.us/sample/9e/fb/__takafuji_kako_idolmaster_and_2_more_drawn_by_papemo368__sample-9efb3f8b6354b1253d6de936db40079a.jpg"
    return render_template('recuperacion.html', imagen_url=imagen_url)

# --- Ejecutar app ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))  # Render asigna dinámicamente
    if ENV == "development":
        print("🚀 Modo desarrollo")
        socketio.run(app, host='0.0.0.0', port=port, debug=True)
    else:
        print("⚡ Producción detectada: usar gunicorn -k eventlet -w 1 app:app")
