import os
import json
import sqlite3
from datetime import datetime, date
from flask import Flask, jsonify, render_template, request
import paho.mqtt.publish as mqtt_publish

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "saya_dimsum.db")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Gunakan topic yang SAMA persis di app.py dan wokwi/sketch.ino.
MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "saya-dimsum/group3/queue/call")

MENU_PRICES = {"Dimsum": 15000, "Fried dimsum": 15000}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_no INTEGER NOT NULL,
                items TEXT NOT NULL,
                total_qty INTEGER NOT NULL,
                payment TEXT NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'progress',
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                stock_today INTEGER NOT NULL DEFAULT 50,
                stock_date TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO settings (id, stock_today, stock_date) VALUES (1, 50, ?)",
            (date.today().isoformat(),)
        )


def current_stock(conn):
    row = conn.execute("SELECT stock_today, stock_date FROM settings WHERE id=1").fetchone()
    if row["stock_date"] != date.today().isoformat():
        conn.execute(
            "UPDATE settings SET stock_today=50, stock_date=? WHERE id=1",
            (date.today().isoformat(),)
        )
        return 50
    return row["stock_today"]


def order_dict(row):
    return {
        "id": row["id"],
        "queue_no": row["queue_no"],
        "items": json.loads(row["items"]),
        "total_qty": row["total_qty"],
        "payment": row["payment"],
        "amount": row["amount"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def state():
    with db() as conn:
        stock = current_stock(conn)
        rows = conn.execute(
            "SELECT * FROM orders WHERE date(created_at)=? ORDER BY id DESC",
            (date.today().isoformat(),)
        ).fetchall()
        orders = [order_dict(r) for r in rows]
        progress = [o for o in orders if o["status"] == "progress"]
        done = [o for o in orders if o["status"] == "done"]
        sold_qty = sum(o["total_qty"] for o in orders)
        remaining = max(stock - sold_qty, 0)
        revenue = sum(o["amount"] for o in done)
        dimsum_sold = sum(o["items"].get("Dimsum", 0) for o in done)
        fried_sold = sum(o["items"].get("Fried dimsum", 0) for o in done)
        qris_count = sum(1 for o in done if o["payment"] == "QRIS")
        cash_count = sum(1 for o in done if o["payment"] == "Cash")
        return jsonify({
            "stock_today": stock,
            "sold_qty": sold_qty,
            "remaining": remaining,
            "revenue": revenue,
            "dimsum_sold": dimsum_sold,
            "fried_sold": fried_sold,
            "qris_count": qris_count,
            "cash_count": cash_count,
            "progress": progress,
            "done": done,
            "orders": orders,
        })


@app.post("/api/stock")
def update_stock():
    data = request.get_json(silent=True) or {}
    try:
        stock = int(data.get("stock", 50))
        if stock < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "Stok harus berupa angka 0 atau lebih."}), 400

    with db() as conn:
        conn.execute(
            "UPDATE settings SET stock_today=?, stock_date=? WHERE id=1",
            (stock, date.today().isoformat())
        )
    return jsonify({"ok": True, "stock": stock})


@app.post("/api/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    items = data.get("items", {})
    payment = data.get("payment")
    try:
        qty_dimsum = max(0, int(items.get("Dimsum", 0)))
        qty_fried = max(0, int(items.get("Fried dimsum", 0)))
    except (TypeError, ValueError, AttributeError):
        return jsonify({"error": "Jumlah menu tidak valid."}), 400

    total_qty = qty_dimsum + qty_fried
    if total_qty == 0:
        return jsonify({"error": "Pilih minimal satu menu."}), 400
    if payment not in ("QRIS", "Cash"):
        return jsonify({"error": "Pilih metode pembayaran."}), 400

    clean_items = {"Dimsum": qty_dimsum, "Fried dimsum": qty_fried}
    amount = qty_dimsum * MENU_PRICES["Dimsum"] + qty_fried * MENU_PRICES["Fried dimsum"]

    with db() as conn:
        stock = current_stock(conn)
        sold = conn.execute(
            "SELECT COALESCE(SUM(total_qty), 0) AS n FROM orders WHERE date(created_at)=?",
            (date.today().isoformat(),)
        ).fetchone()["n"]
        if total_qty > stock - sold:
            return jsonify({"error": f"Stok tidak cukup. Sisa stok: {max(stock-sold, 0)}."}), 400

        active = conn.execute(
            "SELECT MAX(queue_no) AS last_no FROM orders WHERE status='progress' AND date(created_at)=?",
            (date.today().isoformat(),)
        ).fetchone()["last_no"]
        # Nomor berikutnya = nomor antrean aktif terakhir + 1.
        # Jika tidak ada antrean aktif, nomor dimulai lagi dari 1.
        queue_no = (active + 1) if active is not None else 1
        created = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute("""
            INSERT INTO orders (queue_no, items, total_qty, payment, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'progress', ?)
        """, (queue_no, json.dumps(clean_items), total_qty, payment, amount, created))
        order_id = cur.lastrowid
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()

    return jsonify({"ok": True, "order": order_dict(row)}), 201


@app.post("/api/orders/<int:order_id>/done")
def complete_order(order_id):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id=? AND status='progress'", (order_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Pesanan tidak ditemukan atau sudah selesai."}), 404

        completed = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE orders SET status='done', completed_at=? WHERE id=?",
            (completed, order_id)
        )
        queue_no = row["queue_no"]

    # Website mengirim JSON {"nomor": n} ke topic MQTT saat tombol Done ditekan.
    mqtt_ok = True
    mqtt_error = None
    try:
        mqtt_publish.single(
            MQTT_TOPIC,
            payload=json.dumps({"nomor": queue_no}),
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            qos=0,
            retain=False,
            client_id=f"saya-dimsum-web-{os.getpid()}",
            keepalive=10,
        )
    except Exception as exc:
        mqtt_ok = False
        mqtt_error = str(exc)

    return jsonify({
        "ok": True,
        "queue_no": queue_no,
        "mqtt_sent": mqtt_ok,
        "mqtt_error": mqtt_error,
        "message": "Pesanan selesai dan masuk laporan." +
                   (" Panggilan MQTT terkirim." if mqtt_ok else " MQTT belum terkirim; cek koneksi broker.")
    })


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "mqtt_host": MQTT_HOST, "mqtt_topic": MQTT_TOPIC})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
