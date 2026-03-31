from flask import Flask, jsonify
print("Starting web")
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"message": "Flask server running!"})

def run_flask():
    app.run(host="0.0.0.0", port=8501, debug=False, use_reloader=False)
