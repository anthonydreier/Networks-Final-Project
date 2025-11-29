# Author : Ayesha S. Dina
# Modified by: Denis Ulybyshev

import os
import socket
import time
from tkinter import Tk, Button, Label, filedialog, messagebox

# IP = "192.168.1.101" #"localhost"
IP = "localhost"
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

        self.recieve_button = Button(root, text="Recieve File", command=self.recieve_file(self))
        self.recieve_button.pack(pady=5)

def main():
    
    client = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    client.connect(ADDR)
    client.send('hello world CNT 3004 \n'.encode())
    # print('Client received:', client.recv(1024))
    # client.send('q\n'.encode())
    while True:  ### multiple communications
        data = client.recv(SIZE).decode(FORMAT)
        cmd, msg = data.split("@")
        if cmd == "OK":
            print(f"Receiving message from the server ... ")
            print(f"{msg}")
        elif cmd == "DISCONNECTED":
            print(f"{msg}")
            break
        
        data = input("> ") 
        data = data.split(" ")
        cmd = data[0]

        if cmd == "TASK":
            client.send(cmd.encode(FORMAT))
            #type TASK command in the client, then try LOGOUT

        elif cmd == "LOGOUT":
            client.send(cmd.encode(FORMAT))
            break


    print("Disconnected from the server.")
    client.close() ## close the connection

if __name__ == "__main__":
    main()

    
