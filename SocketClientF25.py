import os
import socket
import threading
from tkinter import Tk, Button, Label, filedialog, messagebox, simpledialog
import hashlib


def compute_hash(data: bytes, algorithm: str = 'sha256') -> str:
    """Compute and return the hex digest of `data` using `algorithm`.

    - `data` must be bytes. For large files prefer incremental hashing.
    - `algorithm` defaults to 'sha256' but any algorithm supported by hashlib is allowed.
    """
    try:
        h = hashlib.new(algorithm)
        h.update(data)
        return h.hexdigest()
    except Exception:
        # Fallback: return empty string on error
        return ""

# IP = "192.168.1.101" #"localhost"
IP = "129.213.84.251"
PORT = 4450
ADDR = (IP,PORT)
SIZE = 1024 ## byte .. buffer size
FORMAT = "utf-8"
SERVER_DATA_PATH = "server_data"

class FileClient:
    def __init__(self,master):
        self.sockect = None
        self.client = None
        self.remote_file_list = None
        self.username = None
        self.master = root
        self.master.title("File Transfer System")
        self.master.geometry("400x200")

        self.file_label = Label(root, text="No file recieved")
        self.file_label.grid(pady=10)

        # Buttons
        self.download_button = Button(root, text="Download File", command=self.download_file)
        self.download_button.grid(row=2,column=0,pady=5)

        self.delete_button = Button(root, text="Delete File", command=self.delete_file)
        self.delete_button.grid(row=2,column=1,pady=5)

        self.upload_button = Button(root, text="Upload File", command=self.upload_file)
        self.upload_button.grid(row=2,column=2,pady=5)

    def login(self):
        self.username = simpledialog.askstring("Login", "Enter username:")
        password = simpledialog.askstring("Login", "Enter password:", show='*')

        sha_password = compute_hash(password.encode(FORMAT), 'sha256')

        self.main(sha_password)

    def main(self,sha_password): # Connect to the server
        # Decided to change main to accept sha_password directly and easier to change
    
        self.client = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.client.connect(ADDR)
        self.connect_msg = f"CONNECT {self.username} {sha_password}"
        self.client.send(self.connect_msg.encode(FORMAT))
        self.response = client.recv(SIZE).decode(FORMAT)
        if self.response == "auth_success":
            messagebox.showinfo("Success", "Connected and authenticated successfully.")
        else:
            messagebox.showerror("Error", "Authentication failed.")
            client.close()
            return

        print("Disconnected from the server.")
        client.close() ## close the connection

    def send_command(self, command):
        if not self.client:
            messagebox.showerror("Error", "Not connected to server.")
            return None
        try:
            self.client.send(command.encode(FORMAT))
            response = self.client.recv(SIZE).decode(FORMAT)
            return response
        except Exception as e:
            messagebox.showerror("Error", f"Communication error: {e}")
            return None

    def recieve_file_list(self):
        def task():
            response = self.send_command("TASK")
            if response:
                files = response.split(",")
                self.remote_file_list.delete(0, 'end')
                for file in files:
                    self.remote_file_list.insert('end', file)
                self.file_label.config(text="File list updated.")
        threading.Thread(target=task).start()

    def delete_file(self):
        selected = self.remote_file_list.curselection()
        if not selected:
            messagebox.showerror("Info", "Please select a file.")
            return
        filename = self.remote_file_list.get(selected)
        
        def task():
            try:
                self.send_command(f"DELETE {filename}")
                response = self.sockect.recv(SIZE).decode(FORMAT)
                if response == "success":
                    self.file_label.config(text="File deleted.")
                    self.recieve_file_list()
                else:
                    messagebox.showerror("Error", f"Communication error: {response}")
            except Exception as e:
                messagebox.showerror("Error", f"Communication error: {e}")
        threading.Thread(target=task).start()
    
    def upload_file(self):
        file_path = filedialog.askopenfilename(title="Select a file to upload")
        if not file_path:
            return
        filename = os.path.basename(file_path)
        filesize = os.path.getsize(file_path)
        
        def task():
            try:
                self.send_command(f"UPLOAD {filename} {filesize}")
                response = self.send_command(f"LIST {filename}")
                if response == "success":
                    with open(file_path, 'rb') as f:
                        sent = 0
                        self.progress['value'] = 0
                        while sent < filesize:
                            chunk = f.read(SIZE)
                            if not chunk:
                                break
                            self.sockect.sendall(chunk)
                            sent += len(chunk)
                            self.progress['value'] = (sent/filesize) * 100
                            self.master.update()
                    server_response = self.socket.recv(SIZE).decode(FORMAT)
                    self.status_label.config(text=server_response)
                else:
                    messagebox.showerror("Error", f"Communication error: {response}")
            except Exception as e:
                messagebox.showerror("Error", f"Communication error: {e}")
        threading.Thread(target=task).start()
    
    def download_file(self):
        selected_file = self.remote_file_list.curselection()
        if not selected_file:
            messagebox.showwarning("Warning", "No file selected for download.")
            return
        filename = self.remote_file_list.get(selected_file[0])
        save_path = filedialog.asksaveasfilename(initialfile=filename)
        if not save_path:
            return

        def task():
            try:
                self.send_command(f"DOWNLOAD {filename}")
                response = self.socket.recv(SIZE).decode(FORMAT).decode(FORMAT)
                if response == "success":
                    filesize = int(response.split(" ")[1])
                    self.socket.sendall(response.encode(FORMAT))

                    with open(save_path, 'wb') as f:
                        received_size = 0
                        self.progress['value'] = 0
                        while received_size < filesize:
                            chunk = self.socket.recv(min(SIZE, filesize - received_size))
                            if not chunk:
                                break
                            f.write(chunk)
                            received_size += len(chunk)
                            self.progress['value'] = (received_size / filesize) * 100
                            self.master.update()
                    self.status_label.config(text=response)
                else:
                    messagebox.showerror("Error", f"Communication error: {response}")
            except Exception as e:
                messagebox.showerror("Error", f"Communication error: {e}")
        threading.Thread(target=task).start()

if __name__ == "__main__":
    root = Tk()
    client = FileClient(root)
    root.mainloop()
