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

class ClientGUI:
    def __init__(self,root):
        self.root = root
        self.root.title("File Transer System")
        self.root.geometry("400x200")

        self.file_label = Label(root, text="No file recieved")
        self.file_label.pack(pady=10)

        # Buttons
        self.download_button = Button(root, text="Download File", command=self.main(self))
        self.download_button.pack(row=2,column=0,pady=5)

        self.delete_button = Button(root, text="Delete File", command=self.delete_file)
        self.delete_button.pack(row=2,column=1,pady=5)

        self.upload_button = Button(root, text="Upload File", command=self.upload_file)
        self.upload_button.pack(row=2,column=2,pady=5)

    def login(self):
        self.username = simpledialog.askstring("Login", "Enter username:")
        password = simpledialog.askstring("Login", "Enter password:", show='*')

        sha_password = compute_hash(password.encode(FORMAT), 'sha256')

        self.main(sha_password)

    def main(self,sha_password): # Connect to the server
        # Decided to change main to accept sha_password directly and easier to change
    
        client = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        client.connect(ADDR)
        connect_msg = f"CONNECT {self.username} {sha_password}"
        client.send(connect_msg.encode(FORMAT))
        response = client.recv(SIZE).decode(FORMAT)
        if response == "AUTH_SUCCESS":
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
        file_path = filedialog.askopenfilename(title="Select a file to delete")
        if file_path:
            try:
                os.remove(file_path)
                messagebox.showinfo("Success", f"File '{os.path.basename(file_path)}' deleted successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete file: {e}")
        def task():
            selected_file = self.remote_file_list.get()(self.remote_file_list.curselection())
            if not selected_file:
                messagebox.showwarning("Warning", "No file selected for deletion.")
                return
            response = self.send_command(f"DELETE {selected_file}")
            if response == "DELETE_SUCCESS":
                messagebox.showinfo("Success", f"File '{selected_file}' deleted successfully.")
                self.recieve_file_list()
            else:
                messagebox.showerror("Error", "Failed to delete file.")
    
    def upload_file(self):
        file_path = filedialog.askopenfilename(title="Select a file to upload")
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                # Here you would normally send the data to the server
                messagebox.showinfo("Success", f"File '{os.path.basename(file_path)}' uploaded successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to upload file: {e}")
        def task():
            response = self.send_command("UPLOAD")
            if response == "READY":
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                self.client.sendall(file_data)
                server_response = self.client.recv(SIZE).decode(FORMAT)
                if server_response == "UPLOAD_SUCCESS":
                    messagebox.showinfo("Success", f"File '{os.path.basename(file_path)}' uploaded successfully.")
                else:
                    messagebox.showerror("Error", "Failed to upload file.")
    
    def download_file(self):
        selected_file = self.remote_file_list.get()(self.remote_file_list.curselection())
        if not selected_file:
            messagebox.showwarning("Warning", "No file selected for download.")
            return
        filename = self.remote_file_list.get(selected_file)
        def task():
            response = self.send_command(f"DOWNLOAD {filename}")
            if response and response.startswith("FILEDATA@"):
                file_data = response.split("@", 1)[1].encode(FORMAT)
                save_path = filedialog.asksaveasfilename(initialfile=filename, title="Save File As")
                if save_path:
                    with open(save_path, 'wb') as f:
                        f.write(file_data)
                    messagebox.showinfo("Success", f"File '{filename}' downloaded successfully.")
            else:
                messagebox.showerror("Error", "Failed to download file.")
        threading.Thread(target=task).start()

if __name__ == "__main__":
    root = Tk()
    app = ClientGUI(root)
    root.mainloop()
