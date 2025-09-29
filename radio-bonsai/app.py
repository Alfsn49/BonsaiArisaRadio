import eventlet
eventlet.monkey_patch()

# Parche para psycopg2 y Eventlet (evita bloqueo en mainloop)
from psycogreen.eventlet import patch_psycopg
patch_psycopg()

from flask import Flask, render_template, request
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_mail import Mail
import sqlite3
import os
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv
import pytz
import uuid
import requests
from bs4 import BeautifulSoup
import pandas as pd
from threading import Thread
import time

# --- CONFIG ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
ENV = os.getenv("FLASK_ENV", "production")  # producción por defecto

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anime-radio-secret'

# Configuración de correo (ejemplo con Gmail)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS')
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

# ✅ FIX: asegurar carpeta de uploads
os.makedirs("static/uploads", exist_ok=True)

# --- CONEXIONES ---
def get_connection():
    return psycopg2.connect(DATABASE_URL)

def get_sqlite_connection():
    conn = sqlite3.connect("pedidos.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- INIT DB ---
def init_db():
    # Postgres
    with get_connection() as conn:
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

    # SQLite
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
                imagen TEXT,
                fecha_hora TIMESTAMP NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_fecha ON pedidos(fecha_hora DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comentarios_fecha ON comentarios(fecha_hora DESC)")

        # ✅ FIX: limpieza automática de datos viejos
        cur.execute("DELETE FROM pedidos WHERE fecha_hora < datetime('now','-7 day')")
        cur.execute("DELETE FROM comentarios WHERE fecha_hora < datetime('now','-7 day')")
        conn.commit()

init_db()

# --- HORA LOCAL ---
def obtener_hora_local(fecha_utc, tz_str='America/Guayaquil'):
    tz = pytz.timezone(tz_str)
    return fecha_utc.astimezone(tz)

# --- CACHE DE IMÁGENES ---
IMAGENES_CACHE = []
REFRESH_INTERVAL = 10 * 60  # 10 minutos

def cargar_imagenes():
    sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTBJwSmSRyJVBX4TvZkTsoxP3W5lszO1mldxvVyJOCKr7bqQeYcCWyPERBxibPWmiTI8lR5knv90y7A/pub?output=xlsx"
    try:
        df = pd.read_excel(sheet_url)
        df.columns = df.columns.str.strip()  # limpiar espacios
        if "url" not in df.columns:
            raise ValueError(f"Columnas disponibles: {df.columns.tolist()}")

        # eliminar comillas extra
        urls = df["url"].dropna().apply(lambda x: str(x).strip('"')).tolist()
        return urls

    except Exception as e:
        print("❌ Error cargando imágenes desde Google Sheets:", e)
        return []

def refrescar_imagenes_periodicamente():
    global IMAGENES_CACHE
    while True:
        imagenes = cargar_imagenes()
        if imagenes:
            IMAGENES_CACHE = imagenes
            print(f"✅ Se actualizaron {len(IMAGENES_CACHE)} imágenes desde Google Sheets")
        time.sleep(REFRESH_INTERVAL)

# Arrancar hilo daemon al iniciar
Thread(target=refrescar_imagenes_periodicamente, daemon=True).start()

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

    imagenes = IMAGENES_CACHE  # usar cache
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
        return {"message": "Usuario registrado con éxito"}, 201
    except psycopg2.Error:
        return {"error": "El email ya está registrado"}, 400

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password')

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, email, password FROM usuarios WHERE username = %s", (username,))
            user = cur.fetchone()

    if user and check_password_hash(user[3], password):
        return {"message": "Login exitoso", "usuario": {"id": user[0], "username": user[1], "email": user[2]}}, 200
    return {"error": "Credenciales incorrectas"}, 401

# --- Comentarios ---
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_link_preview(url):
    try:
        r = requests.get(url, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        return {
            "title": soup.find("title").text if soup.find("title") else url,
            "description": soup.find("meta", attrs={"name": "description"})["content"]
                if soup.find("meta", attrs={"name": "description"}) else "",
            "image": soup.find("meta", property="og:image")["content"]
                if soup.find("meta", property="og:image") else "",
            "url": url
        }
    except Exception:
        return None

@app.route('/comentario', methods=['POST'])
def comentario():
    nombre = request.form['nombre']
    mensaje = request.form['mensaje']
    fecha_hora = datetime.utcnow()

    preview = None
    for word in mensaje.split():
        if word.startswith("http"):
            preview = extract_link_preview(word)
            break

    file_url = None
    if 'imagen' in request.files:
        file = request.files['imagen']
        if file and allowed_file(file.filename):
            filename = f"{uuid.uuid4().hex}_{file.filename}"
            path = os.path.join("static/uploads", filename)
            file.save(path)
            file_url = f"/static/uploads/{filename}"

    with get_sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO comentarios (nombre, mensaje, imagen, fecha_hora) VALUES (?, ?, ?, ?)",
            (nombre, mensaje, file_url, fecha_hora)
        )
        conn.commit()

    socketio.emit('nuevo_comentario', {
        'nombre': nombre, 'mensaje': mensaje,
        'fecha_hora': fecha_hora.strftime('%Y-%m-%d %H:%M:%S'),
        'preview': preview,
        'imagen': file_url
    })
    return '', 204

# --- Ejecutar app ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    if ENV == "development":
        socketio.run(app, host='0.0.0.0', port=port, debug=True)
    else:
        print("⚡ Producción detectada: usar gunicorn -k eventlet -w 1 app:app")
