import os
import uuid
from flask import (
    Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
)
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

rooms = {}  # {room_code: {"users": {sid: name}, "chat": [messages], "tic_tac_toe": {...}}}

# ----- HTTP routes -----

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip()
        create = request.form.get("create")
        join = request.form.get("join")

        if not name:
            error = "Введите имя"
        else:
            if create:
                # Создать новую комнату
                room_code = str(uuid.uuid4())[:8]
                rooms[room_code] = {"users": {}, "chat": [], "tic_tac_toe": init_tic_tac_toe()}
                return redirect(url_for("room", code=room_code, name=name))
            elif join:
                if code not in rooms:
                    error = "Такой комнаты не существует"
                else:
                    return redirect(url_for("room", code=code, name=name))
    else:
        name = ""
        code = ""

    return render_template("home.html", error=error, name=request.form.get("name", ""), code=request.form.get("code", ""))


@app.route("/room/<code>")
def room(code):
    name = request.args.get("name", "").strip()
    if code not in rooms:
        return "Room does not exist", 404
    if not name:
        return redirect(url_for("index"))

    return render_template("room.html", code=code, name=name)


@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image part"})
    file = request.files["image"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No selected file"})
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # To avoid overwriting files, add uuid prefix
        filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        return jsonify({"success": True, "filename": filename})
    else:
        return jsonify({"success": False, "error": "File type not allowed"})


@app.route("/static/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ----- Utilities -----

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def init_tic_tac_toe():
    return {
        "board": [""] * 9,
        "turn": "X",
        "winner": None,
        "moves": 0,
    }


# ----- SocketIO events -----

@socketio.on("join")
def on_join(data):
    code = data.get("code")
    name = data.get("name")
    sid = request.sid

    if not code or not name or code not in rooms:
        emit("error", {"msg": "Invalid room or name"})
        return

    join_room(code)
    rooms[code]["users"][sid] = name

    # Send chat history to new user
    emit("chat_history", rooms[code]["chat"], to=sid)

    # Notify others
    emit("message", {"name": "System", "message": f"{name} присоединился к комнате.", "type": "text"}, room=code)
    emit("user_list", list(rooms[code]["users"].values()), room=code)


@socketio.on("leave")
def on_leave(data):
    code = data.get("code")
    sid = request.sid

    if code in rooms and sid in rooms[code]["users"]:
        name = rooms[code]["users"].pop(sid)
        leave_room(code)
        emit("message", {"name": "System", "message": f"{name} покинул комнату.", "type": "text"}, room=code)
        emit("user_list", list(rooms[code]["users"].values()), room=code)


@socketio.on("message")
def handle_message(data):
    code = data.get("code")
    message = data.get("data", "").strip()
    sid = request.sid

    if code not in rooms or sid not in rooms[code]["users"]:
        emit("error", {"msg": "Not in room"})
        return
    if not message:
        return

    name = rooms[code]["users"][sid]
    msg_obj = {"name": name, "message": message, "type": "text"}
    rooms[code]["chat"].append(msg_obj)

    emit("message", msg_obj, room=code)


@socketio.on("image")
def handle_image(data):
    code = data.get("code")
    filename = data.get("filename")
    sid = request.sid

    if code not in rooms or sid not in rooms[code]["users"]:
        emit("error", {"msg": "Not in room"})
        return

    name = rooms[code]["users"][sid]
    msg_obj = {"name": name, "message": filename, "type": "image"}
    rooms[code]["chat"].append(msg_obj)

    emit("message", msg_obj, room=code)


@socketio.on("typing")
def on_typing(data):
    code = data.get("code")
    sid = request.sid
    if code in rooms and sid in rooms[code]["users"]:
        name = rooms[code]["users"][sid]
        emit("typing", {"name": name}, room=code, include_self=False)


@socketio.on("stop_typing")
def on_stop_typing(data):
    code = data.get("code")
    sid = request.sid
    if code in rooms and sid in rooms[code]["users"]:
        emit("stop_typing", {}, room=code, include_self=False)


@socketio.on("clear_chat")
def on_clear_chat(data):
    code = data.get("code")
    sid = request.sid
    if code in rooms and sid in rooms[code]["users"]:
        name = rooms[code]["users"][sid]
        rooms[code]["chat"] = []
        emit("clear_chat", {"name": name}, room=code)


@socketio.on("shake_room")
def on_shake_room(data):
    code = data.get("code")
    sid = request.sid
    if code in rooms and sid in rooms[code]["users"]:
        name = rooms[code]["users"][sid]
        emit("shake", {"name": name}, room=code)


@socketio.on("change_name")
def on_change_name(data):
    code = data.get("code")
    new_name = data.get("new_name", "").strip()
    sid = request.sid
    if code in rooms and sid in rooms[code]["users"] and new_name:
        old_name = rooms[code]["users"][sid]
        rooms[code]["users"][sid] = new_name
        emit("name_changed", {"old_name": old_name, "new_name": new_name}, room=code)


# --- TIC-TAC-TOE game events ---

@socketio.on("tic_tac_toe_join")
def on_ttt_join(data):
    code = data.get("code")
    sid = request.sid
    if code not in rooms:
        emit("error", {"msg": "Room does not exist"})
        return
    # Send current game state
    emit("tic_tac_toe_update", rooms[code]["tic_tac_toe"], to=sid)


@socketio.on("tic_tac_toe_move")
def on_ttt_move(data):
    code = data.get("code")
    pos = data.get("pos")
    sid = request.sid

    if code not in rooms or sid not in rooms[code]["users"]:
        emit("error", {"msg": "Not in room"})
        return

    game = rooms[code]["tic_tac_toe"]
    if game["winner"]:
        emit("error", {"msg": "Game already finished"})
        return

    if pos is None or not (0 <= pos < 9):
        emit("error", {"msg": "Invalid move"})
        return

    if game["board"][pos] != "":
        emit("error", {"msg": "Cell already taken"})
        return

    # Make move
    game["board"][pos] = game["turn"]
    game["moves"] += 1

    # Check win
    if check_winner(game["board"], game["turn"]):
        game["winner"] = game["turn"]
    else:
        # Check draw
        if game["moves"] >= 9:
            game["winner"] = "Draw"
        else:
            game["turn"] = "O" if game["turn"] == "X" else "X"

    emit("tic_tac_toe_update", game, room=code)


@socketio.on("tic_tac_toe_reset")
def on_ttt_reset(data):
    code = data.get("code")
    if code in rooms:
        rooms[code]["tic_tac_toe"] = init_tic_tac_toe()
        emit("tic_tac_toe_update", rooms[code]["tic_tac_toe"], room=code)


# Tic-tac-toe win check
def check_winner(board, player):
    win_conditions = [
        [0,1,2],[3,4,5],[6,7,8],  # rows
        [0,3,6],[1,4,7],[2,5,8],  # cols
        [0,4,8],[2,4,6]           # diagonals
    ]
    for line in win_conditions:
        if all(board[i] == player for i in line):
            return True
    return False


if __name__ == "__main__":
    socketio.run(app, debug=True)
