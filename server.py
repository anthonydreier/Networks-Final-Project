#!/usr/bin/env python3
import os
import socket
import threading
import hashlib
import time

from analysis import NetworkAnalysisModule  # Aidan's module

import re
# CONFIG ------------------------------------------>

HOST = "0.0.0.0" # bind all interfaces
PORT = 4450 # Change to whatever
ADDR = (HOST, PORT)

SIZE = 4096 # buffer size
FORMAT = "utf-8"
DATA_DIR = "server_data" # Will be made if not present

# Hard-coded users: username -> sha256(password).hexdigest()
# Example: password "num1EnronFan" -> use Python to compute once on CLIENT SIDE!!
# Example user:
# "jerma985": "7bf16394d20a1b309bf577cb835b6b44094876ffc70ada2606bcb9347b072de1",
USERS = {
    
}

# For "file currently being processed" requirement, ie don't destroy user data
file_locks = {}
file_locks_lock = threading.Lock()

# Analysis module imported that works on all client threads at once
analyzer = NetworkAnalysisModule(source="server", verbose=True)


# auto-naming function, jank but works kinda
TEXT_EXTS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
    ".py", ".java", ".c", ".cpp", ".h", ".hpp", ".log"
}

AUDIO_EXTS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"
}

VIDEO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v"
}

def _prefix_for_ext(ext: str) -> str:
    ext = (ext or "").lower()
    if ext in TEXT_EXTS:
        return "TS"
    if ext in AUDIO_EXTS:
        return "AS"
    if ext in VIDEO_EXTS:
        return "VS"
    return "FS"

def _looks_like_server_name(filename: str) -> bool:
    return re.match(r"^(TS|AS|VS|FS)\d{3,}(\.[^./\\]+)?$", filename, re.IGNORECASE) is not None

def _allocate_server_filename(dir_abs: str, prefix: str, ext: str) -> str:
    used = set()
    try:
        for name in os.listdir(dir_abs):
            m = re.match(rf"^{re.escape(prefix)}(\d{{3,}})(\.[^./\\]+)?$", name, re.IGNORECASE)
            if m:
                used.add(int(m.group(1)))
    except FileNotFoundError:
        pass

    n = 1
    while n in used:
        n += 1

    width = max(3, len(str(n)))
    return f"{prefix}{n:0{width}d}{ext}"

# UTILS ------------------------------------------>

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

# Don't let people traverse other files in the system, basically.
# Returns absolute path under DATA_DIR or raises ValueError.
def safe_path(rel_path: str) -> str:
    rel_path = rel_path.strip().lstrip("/\\")
    abs_path = os.path.abspath(os.path.join(DATA_DIR, rel_path))
    base = os.path.abspath(DATA_DIR)
    if not abs_path.startswith(base):
        raise ValueError("Invalid path")
    return abs_path

# Locks file when it's being edited
def acquire_file_lock(path: str) -> bool:
    with file_locks_lock:
        if file_locks.get(path, 0) > 0:
            return False
        file_locks[path] = file_locks.get(path, 0) + 1
        return True

# Unlocks file when done
def release_file_lock(path: str):
    with file_locks_lock:
        if path in file_locks:
            file_locks[path] -= 1
            if file_locks[path] <= 0:
                del file_locks[path]

# sha256 func
def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# COMMAND HANDLERS ------------------------------------------>

# EXPECTED USAGE: CONNECT <username> <sha256_hex_password>
# Handles incoming connections & auth
def handle_connect(conn, addr, parts, client_id):
    if len(parts) != 3:
        conn.sendall("ERROR@Usage: CONNECT <username> <sha256_hex_password>".encode(FORMAT))
        return False

    username, pw_hex = parts[1], parts[2]
    expected = USERS.get(username)

    auth_start = time.time()
    # I hate that this if statement works
    if expected and expected == pw_hex:
        dur = time.time() - auth_start
        analyzer.record_connection(client_id, "auth_success", dur)
        conn.sendall("OK@Authenticated".encode(FORMAT))
        return True
    else:
        dur = time.time() - auth_start
        analyzer.record_connection(client_id, "auth_fail", dur)
        conn.sendall("DISCONNECTED@Authentication failed".encode(FORMAT))
        return False

# EXPECTED USAGE: DIR
# Shows dir
def handle_dir(conn, client_id):
    entries = []
    for root, dirs, files in os.walk(DATA_DIR):
        rel_root = os.path.relpath(root, DATA_DIR)
        if rel_root == ".":
            rel_root = ""
        for d in dirs:
            entries.append(os.path.join(rel_root, d) + "/")
        for f in files:
            entries.append(os.path.join(rel_root, f))
    listing = ",".join(entries) if entries else "<empty>"
    conn.sendall(f"OK@{listing}".encode(FORMAT))

    analyzer.record_action(
        action_type="dir",
        filename="",
        file_size=0,
        duration=0.0,
        client_id=client_id,
        status="success",
    )

# EXPECTED USAGE: SUBFOLDER create <relative_path>
#                 SUBFOLDER delete <relative_path>
# Handles subdir creation/deletion
def handle_subfolder(conn, parts, client_id):
    if len(parts) < 3:
        conn.sendall("ERROR@Usage: SUBFOLDER <create|delete> <path>".encode(FORMAT))
        return

    subcmd = parts[1].lower()
    rel_path = " ".join(parts[2:])

    try:
        target = safe_path(rel_path)
    except ValueError:
        conn.sendall("ERROR@Invalid path".encode(FORMAT))
        return

    if subcmd == "create":
        try:
            os.makedirs(target, exist_ok=True)
            conn.sendall("OK@Folder created".encode(FORMAT))
            analyzer.record_action("subfolder_create", rel_path, 0, 0.0, client_id, "success")
        except Exception as e:
            conn.sendall(f"ERROR@{e}".encode(FORMAT))
            analyzer.record_action("subfolder_create", rel_path, 0, 0.0, client_id, "failure")

    elif subcmd == "delete":
        try:
            os.rmdir(target)  # will fail if not empty
            conn.sendall("OK@Folder deleted".encode(FORMAT))
            analyzer.record_action("subfolder_delete", rel_path, 0, 0.0, client_id, "success")
        except Exception as e:
            conn.sendall(f"ERROR@{e}".encode(FORMAT))
            analyzer.record_action("subfolder_delete", rel_path, 0, 0.0, client_id, "failure")
    else:
        conn.sendall("ERROR@Unknown SUBFOLDER subcommand".encode(FORMAT))

# EXPECTED USAGE: DELETE <remote_path>
# Handles deletions
def handle_delete(conn, parts, client_id):
    if len(parts) < 2:
        conn.sendall("ERROR@Usage: DELETE <path>".encode(FORMAT))
        return
    rel_path = " ".join(parts[1:])

    try:
        target = safe_path(rel_path)
    except ValueError:
        conn.sendall("ERROR@Invalid path".encode(FORMAT))
        return

    if not os.path.isfile(target):
        conn.sendall("ERROR@File does not exist".encode(FORMAT))
        return

    if not acquire_file_lock(target):
        conn.sendall("ERROR@File is currently being processed".encode(FORMAT))
        return

    try:
        os.remove(target)
        conn.sendall("OK@File deleted".encode(FORMAT))
        analyzer.record_action("delete", rel_path, 0, 0.0, client_id, "success")
    except Exception as e:
        conn.sendall(f"ERROR@{e}".encode(FORMAT))
        analyzer.record_action("delete", rel_path, 0, 0.0, client_id, "failure")
    finally:
        release_file_lock(target)

# EXPECTED USAGE: UPLOAD <remote_path> <filesize_bytes>
# Handles uploads to server
def handle_upload(conn, parts, client_id):
    if len(parts) < 3:
        conn.sendall("ERROR@Usage: UPLOAD <path> <filesize_bytes>".encode(FORMAT))
        return

    requested_rel = " ".join(parts[1:-1])
    
    try:
        filesize = int(parts[-1])
    except ValueError:
        conn.sendall("ERROR@filesize must be int".encode(FORMAT))
        return

    rel_dir = os.path.dirname(requested_rel).strip().lstrip("/\\")
    requested_name = os.path.basename(requested_rel)
    _, ext = os.path.splitext(requested_name)

    try:
        dir_abs = safe_path(rel_dir) if rel_dir else safe_path("")
    except ValueError:
        conn.sendall("ERROR@Invalid path".encode(FORMAT))
        return

    if _looks_like_server_name(requested_name):
        stored_name = requested_name
    else:
        prefix = _prefix_for_ext(ext)
        stored_name = _allocate_server_filename(dir_abs, prefix, ext)

    stored_rel = os.path.join(rel_dir, stored_name) if rel_dir else stored_name

    try:
        target = safe_path(stored_rel)
    except ValueError:
        conn.sendall("ERROR@Invalid path".encode(FORMAT))
        return

    os.makedirs(os.path.dirname(target), exist_ok=True)

    if os.path.exists(target):
        conn.sendall("OK@EXISTS".encode(FORMAT))
        ans = conn.recv(SIZE).decode(FORMAT).strip().lower()
        if ans != "y":
            conn.sendall("ERROR@Upload cancelled".encode(FORMAT))
            analyzer.record_action("upload", stored_rel, filesize, 0.0, client_id, "failure")
            return

    if not acquire_file_lock(target):
        conn.sendall("ERROR@File is currently being processed".encode(FORMAT))
        analyzer.record_action("upload", stored_rel, filesize, 0.0, client_id, "failure")
        return

    conn.sendall(f"READY@{filesize}".encode(FORMAT))

    start = time.time()
    remaining = filesize
    status = "success"

    try:
        with open(target, "wb") as f:
            while remaining > 0:
                chunk = conn.recv(min(SIZE, remaining))
                if not chunk:
                    status = "failure"
                    break
                f.write(chunk)
                remaining -= len(chunk)
    except Exception:
        status = "failure"

    duration = time.time() - start
    release_file_lock(target)

    analyzer.record_action("upload", stored_rel, filesize, duration, client_id, status)

    if status == "success" and remaining == 0:
        conn.sendall(f"OK@Upload complete: {stored_rel}".encode(FORMAT))
    else:
        conn.sendall("ERROR@Upload incomplete".encode(FORMAT))

def handle_download(conn, parts, client_id):
    if len(parts) < 2:
        conn.sendall("ERROR@Usage: DOWNLOAD <path>".encode(FORMAT))
        return

    rel_path = " ".join(parts[1:])

    try:
        target = safe_path(rel_path)
    except ValueError:
        conn.sendall("ERROR@Invalid path".encode(FORMAT))
        return

    if not os.path.isfile(target):
        conn.sendall("ERROR@File not found".encode(FORMAT))
        return

    if not acquire_file_lock(target):
        conn.sendall("ERROR@File is currently being processed".encode(FORMAT))
        return

    filesize = os.path.getsize(target)
    conn.sendall(f"FILEINFO@{filesize}".encode(FORMAT))
    ack = conn.recv(SIZE).decode(FORMAT).strip()

    if ack.upper() != "READY":
        release_file_lock(target)
        return

    start = time.time()
    status = "success"

    try:
        with open(target, "rb") as f:
            while True:
                chunk = f.read(SIZE)
                if not chunk:
                    break
                conn.sendall(chunk)
    except Exception:
        status = "failure"

    duration = time.time() - start
    release_file_lock(target)

    analyzer.record_action("download", rel_path, filesize, duration, client_id, status)


# CLIENT THREAD ------------------------------------------>

def handle_client(conn, addr):
    client_id = f"{addr[0]}:{addr[1]}"
    print(f"[NEW CONNECTION] {client_id}")
    analyzer.record_connection(client_id, "connect")

    authenticated = False

    try:
        while True:
            data = conn.recv(SIZE)
            if not data:
                break
            text = data.decode(FORMAT).strip()
            if not text:
                continue

            parts = text.split()
            cmd = parts[0].upper()

            if not authenticated:
                if cmd == "CONNECT":
                    authenticated = handle_connect(conn, addr, parts, client_id)
                    if not authenticated:
                        # handle_connect already sent DISCONNECTED
                        break
                else:
                    conn.sendall("ERROR@You must CONNECT first".encode(FORMAT))
                continue

            # After this point, client is authenticated, we can start receiving commands
            if cmd == "DIR":
                handle_dir(conn, client_id)
            elif cmd == "SUBFOLDER":
                handle_subfolder(conn, parts, client_id)
            elif cmd == "DELETE":
                handle_delete(conn, parts, client_id)
            elif cmd == "UPLOAD":
                handle_upload(conn, parts, client_id)
            elif cmd == "DOWNLOAD":
                handle_download(conn, parts, client_id)
            elif cmd in ("LOGOUT", "QUIT", "EXIT"):
                analyzer.record_connection(client_id, "disconnect")
                conn.sendall("DISCONNECTED@Goodbye".encode(FORMAT))
                break
            else:
                conn.sendall("ERROR@Unknown command".encode(FORMAT))

    except Exception as e:
        print(f"[ERROR] Client {client_id}: {e}")
    finally:
        conn.close()
        print(f"[DISCONNECTED] {client_id}")


# SERVER LOOP ------------------------------------------>

def start_server():
    ensure_data_dir()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(ADDR)
    server.listen(5)

    print(f"[LISTENING] Server on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server.accept()
            # Multithreading is easy, actually
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping server...")
    finally:
        analyzer.stop()
        server.close()


if __name__ == "__main__":
    start_server()
