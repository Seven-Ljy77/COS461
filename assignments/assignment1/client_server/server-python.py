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

    # 设定输出逻辑为输出字节，不进行文本解码
    output_stream = getattr(sys.stdout, "buffer", sys.stdout)

    # 创建 socket 对象
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定至本机端口
        listener.bind(("", server_port))

        # 执行监听
        listener.listen(QUEUE_LENGTH)

        while True:
            try:
                connection, _ = listener.accept()    # connection 返回客户端 socket 对象，_ 返回客户端地址信息，但未使用
            except socket.error as error:
                sys.stderr.write("accept: %s\n" % error)
                continue
            try:
                while True:
                    try:
                        # 接受数据
                        data = connection.recv(RECV_BUFFER_SIZE)
                    except socket.error as error:
                        sys.stderr.write("recv: %s\n" % error)
                        break
                    if not data:
                        break

                    # 输出字节
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
