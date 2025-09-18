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
        "https://cdn.donmai.us/sample/6b/35/__minato_yukina_bang_dream_drawn_by_kanade_kanade_3344__sample-6b35cb6f1432715b1d899d3979fd5e7b.jpg",
        "https://cdn.donmai.us/sample/a4/2d/__imai_lisa_bang_dream_drawn_by_kanade_kanade_3344__sample-a42d9484330a90f5b3347735d8f41a1a.jpg",
        "https://cdn.donmai.us/sample/28/1f/__misumi_uika_bang_dream_and_1_more_drawn_by_beniyomogi__sample-281fb72d88d7d136f1b79422b2ba5824.jpg",
        "https://cdn.donmai.us/sample/00/07/__ichigaya_arisa_bang_dream_drawn_by_e20__sample-00075aa3d57935ad342e61041f49e961.jpg",
        "https://cdn.donmai.us/sample/d1/7c/__aoba_moca_bang_dream_drawn_by_junji_17__sample-d17cfdbbef732b6b965b56fd06550745.jpg",
        "https://cdn.donmai.us/sample/e4/13/__togawa_sakiko_and_misumi_uika_bang_dream_and_1_more_drawn_by_kawai_akamai__sample-e413325800d88f8d7fa964a3e88c831c.jpg",
        "https://cdn.donmai.us/sample/8b/f9/__shiina_taki_bang_dream_and_1_more_drawn_by_raiden_kdsn3783__sample-8bf9b82f1786d0a12387f6d44a4aea9b.jpg",
        "https://cdn.donmai.us/sample/44/21/__mitake_ran_bang_dream_drawn_by_mihaya_mihaya1818__sample-4421421c0241b47b86174a2eed8cd895.jpg",
        "https://cdn.donmai.us/sample/b3/d8/__tsurumaki_kokoro_bang_dream_drawn_by_temari_rin__sample-b3d8bc572a3b1749bb4a869c718c3882.jpg",
        "https://cdn.donmai.us/sample/d5/57/__mitake_ran_bang_dream_drawn_by_sunnysalt_08__sample-d557994d14b95f0be0b89fe7a8efa63d.jpg",
        "https://cdn.donmai.us/sample/fa/94/__houshou_marine_and_mitake_ran_hololive_and_1_more_drawn_by_sunnysalt_08__sample-fa9442bc14259c7b3ce987609a8b2cc6.jpg",
        "https://cdn.donmai.us/sample/5a/49/__imai_lisa_and_minato_yukina_bang_dream_drawn_by_sunnysalt_08__sample-5a49dba7c3e25246e1736778cd6f0aa2.jpg",
        "https://cdn.donmai.us/sample/55/e5/__imai_lisa_bang_dream_drawn_by_nuruponnu__sample-55e54774a157824a955134ad813f03f0.jpg",
        "https://cdn.donmai.us/sample/57/76/__imai_lisa_and_minato_yukina_bang_dream_drawn_by_shih_lion__sample-577621041a4a6856513d8773a7875d6c.jpg",
        "https://cdn.donmai.us/sample/ff/86/__kawaragi_momoka_girls_band_cry_drawn_by_ayataka_syumimi__sample-ff8604082deef53ebc32914255d56f17.jpg",
        "https://cdn.donmai.us/sample/87/c6/__awa_subaru_girls_band_cry_drawn_by_niaochw__sample-87c67f9b91a13b47f9effb6f9a1ada07.jpg",
        "https://cdn.donmai.us/sample/1c/43/__iseri_nina_and_kawaragi_momoka_girls_band_cry_drawn_by_yanagi_marie__sample-1c43a8fcc0da77dd13ecb66155bfe022.jpg",
        "https://cdn.donmai.us/sample/39/fe/__awa_subaru_girls_band_cry_drawn_by_habsida_habsida_hpy__sample-39fead88541e7e202bb20e9c54a9cbe0.jpg",
        "https://cdn.donmai.us/sample/3d/52/__iseri_nina_and_kawaragi_momoka_girls_band_cry_and_1_more_drawn_by_habsida_habsida_hpy__sample-3d5247c4518bd8c4f0908e9ebb2f2fc2.jpg",
        "https://cdn.donmai.us/sample/88/60/__minase_iori_and_usa_chan_idolmaster_drawn_by_ap_bar__sample-886021936a4118f2c289f8ad623e93f4.jpg",
        "https://cdn.donmai.us/sample/38/d2/__minase_iori_idolmaster_drawn_by_baji_toufuu_bajitohfu__sample-38d27332ee6940b897d6d812c2d06f2e.jpg",
        "https://cdn.donmai.us/sample/40/16/__anyoji_hime_love_live_and_1_more_drawn_by_jin_oihlf__sample-40165e2bbda3855735678442bb806bbd.jpg",
        "https://cdn.donmai.us/original/2d/1c/__mifune_shioriko_love_live_and_1_more_drawn_by_mukiryoku_bato__2d1c4dfe76a2d51b8ccc4435ac6fed39.png",
        "https://cdn.donmai.us/sample/98/dc/__kosaka_honoka_love_live_and_1_more_drawn_by_curakuru__sample-98dc9fe29f079527f11e823cd6b84aba.jpg",
        "https://cdn.donmai.us/sample/6e/ff/__uehara_ayumu_love_live_and_1_more_drawn_by_kurono_pixiv1905129__sample-6eff1af1e07d503df8116e5da0634d3e.jpg",
        "https://cdn.donmai.us/sample/3e/f1/__osaka_shizuku_love_live_and_1_more_drawn_by_satolive20__sample-3ef10a2ca39dfbc99485cce241e9c0b4.jpg",
        "https://cdn.donmai.us/sample/c6/b9/__mia_taylor_love_live_and_1_more_drawn_by_shinonome_sakura__sample-c6b9e9057016951bbb4ece0ef8eda7a2.jpg",
        "https://cdn.donmai.us/sample/cb/47/__shibuya_kanon_love_live_and_1_more_drawn_by_frontrivers_kae__sample-cb472de6863e6c5453af508da85e8795.jpg",
        "https://cdn.donmai.us/sample/59/44/__shibuya_kanon_and_arashi_chisato_love_live_and_1_more_drawn_by_akane_akanene928__sample-5944659e163ee5973deef6fe1a492e84.jpg",
        "https://cdn.donmai.us/sample/50/86/__shibuya_kanon_hazuki_ren_sakurakoji_kinako_and_nanakusa_nanami_love_live_and_1_more_drawn_by_matcha_moti_matcha_427__sample-5086c86acef79799a530feb2af14bd3f.jpg",
        "https://cdn.donmai.us/sample/cc/82/__sakurai_momoka_idolmaster_and_1_more_drawn_by_yoshikirino__sample-cc827754022d0159109aac4267d2beaa.jpg",
        "https://cdn.donmai.us/sample/cd/fc/__sakurai_momoka_idolmaster_and_1_more_drawn_by_dakku_nira597__sample-cdfc4ff6abf43ee4b41139a91b5038a6.jpg",
        "https://cdn.donmai.us/sample/ff/3c/__sagisawa_fumika_idolmaster_and_1_more_drawn_by_karlp346pro__sample-ff3c2b52bda4f199dc625957697d40ff.jpg",
        "https://cdn.donmai.us/sample/fc/d8/__sagisawa_fumika_idolmaster_and_1_more_drawn_by_karlp346pro__sample-fcd8a65e6552110364ff6f9acdd08a83.jpg",
        "https://cdn.donmai.us/sample/69/85/__sagisawa_fumika_idolmaster_and_1_more_drawn_by_karlp346pro__sample-69851615f4ed9e372740ce305d1a91b5.jpg",
        "https://cdn.donmai.us/sample/b3/4c/__sagisawa_fumika_idolmaster_and_1_more_drawn_by_zhi_papercraft8559__sample-b34c5e028319bfc652de66915136b169.jpg",
        "https://cdn.donmai.us/sample/ee/ff/__sagisawa_fumika_idolmaster_and_1_more_drawn_by_tori_2020toryiu__sample-eeff4c0bc18d7f8ee2d971a237a72cfd.jpg",
        "https://cdn.donmai.us/sample/1f/1e/__shirokane_rinko_bang_dream_drawn_by_yue_mao_yukinihime__sample-1f1e4824aba291f07b71b0aed2a1997d.jpg",
        "https://cdn.donmai.us/sample/5e/21/__shirokane_rinko_bang_dream_drawn_by_izami_md__sample-5e2116120169876ac4898c3570fc302b.jpg",
        "https://cdn.donmai.us/sample/89/7b/__shirokane_rinko_bang_dream_drawn_by_sakurahara__sample-897bff4c036753ae57413da2781dd8f5.jpg",
        "https://cdn.donmai.us/sample/75/87/__shirokane_rinko_bang_dream_drawn_by_me_a_r_party428__sample-758734a8a86e9480277ab8e2f91652d2.jpg"        
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
