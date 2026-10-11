###############################################################################
# client-python.py
# Name:  刘嘉逸
# NetId: 10254602402
###############################################################################

import sys
import socket

SEND_BUFFER_SIZE = 2048

def client(server_ip, server_port):
    """TODO: Open socket and send message from sys.stdin"""
    # 设定读取逻辑为读取字节，不进行文本解码
    input_stream = getattr(sys.stdin, "buffer", sys.stdin)

    # 这里的 connection 本身就是 python socket 对象
    connection = socket.create_connection((server_ip, server_port))
    try:
        while True:
            data = input_stream.read(SEND_BUFFER_SIZE)
            if not data:
                break
            connection.sendall(data)
    finally:
        connection.close()


def main():
    """Parse command-line arguments and call client function """
    if len(sys.argv) != 3:
        sys.exit("Usage: python client-python.py [Server IP] [Server Port] < [message]")
    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    client(server_ip, server_port)

if __name__ == "__main__":
    main()
