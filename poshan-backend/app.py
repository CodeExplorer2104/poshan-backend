from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
import os
from datetime import datetime, timedelta
import jwt
from functools import wraps

app = Flask(__name__)
CORS(app, origins=os.environ.get("FRONTEND_URL", "*"))

SECRET_KEY = os.environ.get("SECRET_KEY", "shaleya-poshan-secret-2024")
FILE_NAME  = "monthly_meal_record.xlsx"

# ── USERS (change passwords!) ───────────────────────────────────
USERS = {
    "admin":   "school123",
    "teacher": "poshan456",
}
# ───────────────────────────────────────────────────────────────

MARATHI_DAYS = {
    "Monday": "सोमवार", "Tuesday": "मंगळवार", "Wednesday": "बुधवार",
    "Thursday": "गुरुवार", "Friday": "शुक्रवार", "Saturday": "शनिवार", "Sunday": "रविवार"
}

RECIPES = {
    "Harbara": {"jeera": 1,   "oil": 5,   "meeth": 2,   "mohri": 1},
    "Chana":   {"jeera": 1.2, "oil": 5.5, "meeth": 2,   "mohri": 1},
    "Moong":   {"jeera": 0.8, "oil": 4,   "meeth": 1.5, "mohri": 0.8},
    "Vatana":  {"jeera": 1,   "oil": 5,   "meeth": 2,   "mohri": 1},
}

PRICES  = {"jeera": 0.5, "oil": 0.2, "meeth": 0.1, "mohri": 0.3}
COLUMNS = [
    "तारीख (Date)", "वार (Day)", "एकूण विद्यार्थी (Total Students)",
    "उपस्थित विद्यार्थी (Present Students)", "घटक (Item)",
    "जिरे (Jeera)", "तेल (Oil)", "मीठ (Salt)", "मोहरी (Mustard)",
    "एकूण खर्च (Total Cost)"
]

# ── JWT HELPERS ─────────────────────────────────────────────────
def make_token(username):
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=8)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Token missing"}), 401
        try:
            data = jwt.decode(auth.split(" ")[1], SECRET_KEY, algorithms=["HS256"])
            request.username = data["sub"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

# ── AUTH ────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json() or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if username in USERS and USERS[username] == password:
        return jsonify({"token": make_token(username), "username": username})
    return jsonify({"error": "चुकीचे नाव किंवा पासवर्ड"}), 401

@app.route("/api/me")
@token_required
def me():
    return jsonify({"username": request.username})

# ── RECORDS ─────────────────────────────────────────────────────
def load_df():
    if os.path.exists(FILE_NAME):
        return pd.read_excel(FILE_NAME).reindex(columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)

def save_df(df):
    df.to_excel(FILE_NAME, index=False)

@app.route("/api/records", methods=["GET"])
@token_required
def get_records():
    df = load_df()
    records = df.fillna("").to_dict(orient="records")
    total_cost = float(df["एकूण खर्च (Total Cost)"].sum()) if not df.empty else 0
    return jsonify({"records": records, "total_cost": round(total_cost, 2), "count": len(records)})

@app.route("/api/records", methods=["POST"])
@token_required
def add_record():
    body = request.get_json() or {}
    date             = body["date"]
    total_students   = int(body["total_students"])
    present_students = int(body["present_students"])
    item             = body["item"]

    day_eng     = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
    day_marathi = MARATHI_DAYS[day_eng]
    recipe      = RECIPES[item]

    jeera = recipe["jeera"] * present_students
    oil   = recipe["oil"]   * present_students
    meeth = recipe["meeth"] * present_students
    mohri = recipe["mohri"] * present_students
    cost  = jeera*PRICES["jeera"] + oil*PRICES["oil"] + meeth*PRICES["meeth"] + mohri*PRICES["mohri"]

    new_row = pd.DataFrame([{
        "तारीख (Date)": date, "वार (Day)": day_marathi,
        "एकूण विद्यार्थी (Total Students)": total_students,
        "उपस्थित विद्यार्थी (Present Students)": present_students,
        "घटक (Item)": item, "जिरे (Jeera)": jeera, "तेल (Oil)": oil,
        "मीठ (Salt)": meeth, "मोहरी (Mustard)": mohri,
        "एकूण खर्च (Total Cost)": cost
    }]).reindex(columns=COLUMNS)

    df = load_df()
    df = pd.concat([df, new_row], ignore_index=True)
    save_df(df)

    return jsonify({"message": "Record saved", "cost": cost,
                    "jeera": jeera, "oil": oil, "meeth": meeth, "mohri": mohri})

@app.route("/api/records/<int:row_id>", methods=["PUT"])
@token_required
def update_record(row_id):
    body = request.get_json() or {}
    df = load_df()
    if row_id >= len(df):
        return jsonify({"error": "Record not found"}), 404
    df.loc[row_id, "तारीख (Date)"]                          = body.get("date")
    df.loc[row_id, "एकूण विद्यार्थी (Total Students)"]     = int(body.get("total"))
    df.loc[row_id, "उपस्थित विद्यार्थी (Present Students)"] = int(body.get("present"))
    save_df(df)
    return jsonify({"message": "Updated"})

@app.route("/api/records/<int:row_id>", methods=["DELETE"])
@token_required
def delete_record(row_id):
    df = load_df()
    if row_id >= len(df):
        return jsonify({"error": "Record not found"}), 404
    df = df.drop(index=row_id).reset_index(drop=True)
    save_df(df)
    return jsonify({"message": "Deleted"})

@app.route("/api/download")
@token_required
def download():
    if os.path.exists(FILE_NAME):
        return send_file(FILE_NAME, as_attachment=True)
    return jsonify({"error": "No records found"}), 404

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True)