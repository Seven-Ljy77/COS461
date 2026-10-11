###############################################################################
# server-python.py
# Name:  刘嘉逸
# NetId: 10254602402
###############################################################################

import sys
import socket

RECV_BUFFER_SIZE = 2048
QUEUE_LENGTH = 10

def server(server_port):
    """TODO: Listen on socket and print received message to sys.stdout"""
    output_stream = getattr(sys.stdout, "buffer", sys.stdout)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("", server_port))
        listener.listen(QUEUE_LENGTH)
        while True:
            try:
                connection, address = listener.accept()
            except socket.error as error:
                sys.stderr.write("accept: %s\n" % error)
                continue
            try:
                while True:
                    try:
                        data = connection.recv(RECV_BUFFER_SIZE)
                    except socket.error as error:
                        sys.stderr.write("recv: %s\n" % error)
                        break
                    if not data:
                        break
                    output_stream.write(data)
                    output_stream.flush()
            finally:
                connection.close()
    finally:
        listener.close()


def main():
    """Parse command-line argument and call server function """
    if len(sys.argv) != 2:
        sys.exit("Usage: python server-python.py [Server Port]")
    server_port = int(sys.argv[1])
    server(server_port)

if __name__ == "__main__":
    main()
