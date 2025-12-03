#!/usr/bin/env python3
import os
import socket
import hashlib
import threading
from tkinter import Tk, Button, Label, Listbox, Scrollbar, END, SINGLE, filedialog, messagebox, simpledialog

IP = "129.213.84.251"
PORT = 4450
ADDR = (IP, PORT)

SIZE = 4096
FORMAT = "utf-8"


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode(FORMAT)).hexdigest()


class FileClientGUI:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Socket File Client")
        self.root.geometry("520x320")

        self.client: socket.socket | None = None
        self.username: str | None = None

        self.status = Label(root, text="Not connected")
        self.status.pack(pady=6)

        # listbox + scrollbar
        frame = root
        self.scroll = Scrollbar(frame)
        self.scroll.pack(side="right", fill="y")

        self.remote_list = Listbox(frame, selectmode=SINGLE, yscrollcommand=self.scroll.set, width=70, height=12)
        self.remote_list.pack(padx=8, pady=6)
        self.scroll.config(command=self.remote_list.yview)

        # buttons
        btnrow = root
        Button(btnrow, text="Connect", width=12, command=self.connect).pack(side="left", padx=6, pady=8)
        Button(btnrow, text="DIR (Refresh)", width=12, command=self.dir_refresh).pack(side="left", padx=6, pady=8)
        Button(btnrow, text="Upload", width=12, command=self.upload_file).pack(side="left", padx=6, pady=8)
        Button(btnrow, text="Download", width=12, command=self.download_file).pack(side="left", padx=6, pady=8)
        Button(btnrow, text="Delete", width=12, command=self.delete_file).pack(side="left", padx=6, pady=8)

        Button(root, text="Subfolder (create/delete)", command=self.subfolder).pack(pady=4)
        Button(root, text="Logout/Quit", command=self.logout).pack(pady=4)

    # ---------- low-level helpers ----------
    def _set_status(self, msg: str):
        self.status.config(text=msg)

    def _recv_text(self) -> str:
        data = self.client.recv(SIZE)
        if not data:
            raise ConnectionError("Server closed connection")
        return data.decode(FORMAT).strip()

    def _send_text(self, msg: str):
        self.client.sendall(msg.encode(FORMAT))

    def _require_conn(self) -> bool:
        if not self.client:
            messagebox.showerror("Error", "Not connected.")
            return False
        return True

    # ---------- operations ----------
    def connect(self):
        if self.client:
            messagebox.showinfo("Info", "Already connected.")
            return

        username = simpledialog.askstring("Login", "Enter username:")
        if not username:
            return
        password = simpledialog.askstring("Login", "Enter password:", show="*")
        if password is None:
            return

        pw_hex = sha256_hex(password)

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(ADDR)
            self.client = s
            self.username = username

            self._send_text(f"CONNECT {username} {pw_hex}")
            resp = self._recv_text()

            if resp.startswith("OK@"):
                self._set_status(f"Connected as {username}")
                self.dir_refresh()
            else:
                messagebox.showerror("Auth failed", resp)
                self.client.close()
                self.client = None
                self.username = None
                self._set_status("Not connected")
        except Exception as e:
            messagebox.showerror("Error", f"Connect failed: {e}")
            try:
                if self.client:
                    self.client.close()
            finally:
                self.client = None
                self.username = None
                self._set_status("Not connected")

    def dir_refresh(self):
        if not self._require_conn():
            return

        def task():
            try:
                self._send_text("DIR")
                resp = self._recv_text()
                if not resp.startswith("OK@"):
                    self.root.after(0, lambda: messagebox.showerror("DIR error", resp))
                    return

                listing = resp.split("@", 1)[1]
                entries = [] if listing == "<empty>" else listing.split(",")

                def update_ui():
                    self.remote_list.delete(0, END)
                    for e in entries:
                        self.remote_list.insert(END, e)

                self.root.after(0, update_ui)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"DIR failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def subfolder(self):
        if not self._require_conn():
            return
        action = simpledialog.askstring("Subfolder", "Action: create or delete?")
        if not action:
            return
        path = simpledialog.askstring("Subfolder", "Path (relative to server_data):")
        if not path:
            return

        def task():
            try:
                self._send_text(f"SUBFOLDER {action.strip().lower()} {path.strip()}")
                resp = self._recv_text()
                self.root.after(0, lambda: messagebox.showinfo("Subfolder", resp))
                self.dir_refresh()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Subfolder failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def delete_file(self):
        if not self._require_conn():
            return
        sel = self.remote_list.curselection()
        if not sel:
            messagebox.showwarning("Delete", "Select a file first.")
            return
        name = self.remote_list.get(sel[0])
        if name.endswith("/"):
            messagebox.showwarning("Delete", "Select a file (not a folder).")
            return

        def task():
            try:
                self._send_text(f"DELETE {name}")
                resp = self._recv_text()
                if resp.startswith("OK@"):
                    self.root.after(0, lambda: messagebox.showinfo("Delete", resp))
                    self.dir_refresh()
                else:
                    self.root.after(0, lambda: messagebox.showerror("Delete failed", resp))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Delete failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def upload_file(self):
        if not self._require_conn():
            return
        local_path = filedialog.askopenfilename(title="Select a file to upload")
        if not local_path:
            return

        default_remote = os.path.basename(local_path)
        remote_path = simpledialog.askstring("Upload", "Remote path (relative to server_data):", initialvalue=default_remote)
        if not remote_path:
            return

        filesize = os.path.getsize(local_path)

        def task():
            try:
                self._send_text(f"UPLOAD {remote_path} {filesize}")

                # server may reply OK@EXISTS, READY@..., or ERROR@...
                while True:
                    resp = self._recv_text()
                    if resp == "OK@EXISTS":
                        overwrite = messagebox.askyesno("Upload", "Remote file exists. Overwrite?")
                        self._send_text("y" if overwrite else "n")
                        if not overwrite:
                            cancel_msg = self._recv_text()
                            self.root.after(0, lambda: messagebox.showinfo("Upload", cancel_msg))
                            return
                        continue

                    if resp.startswith("READY@"):
                        break

                    if resp.startswith("ERROR@") or resp.startswith("DISCONNECTED@"):
                        self.root.after(0, lambda: messagebox.showerror("Upload failed", resp))
                        return

                    self.root.after(0, lambda: messagebox.showerror("Upload failed", f"Unexpected: {resp}"))
                    return

                # send file bytes
                with open(local_path, "rb") as f:
                    remaining = filesize
                    while remaining > 0:
                        chunk = f.read(min(SIZE, remaining))
                        if not chunk:
                            break
                        self.client.sendall(chunk)
                        remaining -= len(chunk)

                final = self._recv_text()
                if final.startswith("OK@"):
                    self.root.after(0, lambda: messagebox.showinfo("Upload", final))
                    self.dir_refresh()
                else:
                    self.root.after(0, lambda: messagebox.showerror("Upload failed", final))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Upload failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def download_file(self):
        if not self._require_conn():
            return
        sel = self.remote_list.curselection()
        if not sel:
            messagebox.showwarning("Download", "Select a file first.")
            return

        name = self.remote_list.get(sel[0])
        if name.endswith("/"):
            messagebox.showwarning("Download", "Select a file (not a folder).")
            return

        save_path = filedialog.asksaveasfilename(initialfile=os.path.basename(name), title="Save as")
        if not save_path:
            return

        def task():
            try:
                self._send_text(f"DOWNLOAD {name}")
                resp = self._recv_text()
                if resp.startswith("ERROR@"):
                    self.root.after(0, lambda: messagebox.showerror("Download failed", resp))
                    return
                if not resp.startswith("FILEINFO@"):
                    self.root.after(0, lambda: messagebox.showerror("Download failed", f"Unexpected: {resp}"))
                    return

                filesize = int(resp.split("@", 1)[1])
                self._send_text("READY")

                remaining = filesize
                with open(save_path, "wb") as f:
                    while remaining > 0:
                        chunk = self.client.recv(min(SIZE, remaining))
                        if not chunk:
                            raise ConnectionError("Server closed connection mid-download")
                        f.write(chunk)
                        remaining -= len(chunk)

                self.root.after(0, lambda: messagebox.showinfo("Download", f"Saved {filesize} bytes to:\n{save_path}"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Download failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def logout(self):
        if not self.client:
            self.root.destroy()
            return
        try:
            self._send_text("LOGOUT")
            _ = self._recv_text()
        except Exception:
            pass
        try:
            self.client.close()
        finally:
            self.client = None
            self.username = None
            self._set_status("Not connected")
            self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    app = FileClientGUI(root)
    root.mainloop()
