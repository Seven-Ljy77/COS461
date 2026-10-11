/*****************************************************************************
 * server-c.c                                                                 
 * Name:  刘嘉逸
 * NetId: 10254602402
 *****************************************************************************/

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <netdb.h>
#include <netinet/in.h>
#include <errno.h>

#define QUEUE_LENGTH 10
#define RECV_BUFFER_SIZE 2048


// 创建 socket
int create_socket(struct addrinfo *result) {
    struct addrinfo *address;
    int listen_fd = -1;

    // 不断尝试能创建 socket 并和本机端口绑定的 result
    for (address = result ; address != NULL ; address = address->ai_next) {
        listen_fd = socket(address->ai_family , address->ai_socktype , address->ai_protocol);

        if (listen_fd == -1) { // 创建 socket 失败
            perror("socket");
            continue;
        }

        if (bind(listen_fd, address->ai_addr, address->ai_addrlen) == 0)
            break;
        else
            perror("bind");

        close(listen_fd);
        listen_fd = -1;
    }

    return listen_fd;
}


/* TODO: server()
 * Open socket and wait for client to connect
 * Print received message to stdout
 * Return 0 on success, non-zero on failure
*/
int server(char *server_port) {
    struct addrinfo hints = {0};
    struct addrinfo *result = NULL;

    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_PASSIVE;    // 生成用于 bind 的地址（宏的注释）

    // 第一项填写 NULL，默认生成 0.0.0.0
    int status = getaddrinfo(NULL, server_port, &hints, &result);

    if (status != 0) { // 失败
        fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(status));
        return 1;
    }

    int listen_fd = create_socket(result);

    freeaddrinfo(result);
    if (listen_fd == -1) // bind 失败
        return 1;
    
    // 让已绑定地址和端口的 socket 进入监听状态
    if (listen(listen_fd, QUEUE_LENGTH) == -1) {
        perror("listen");
        close(listen_fd);
        return 1;
    }

    while(1) {
        // 监听客户端连接，不需要获取客户端 ip 端口，也不需要获取缓冲区长度
        int client_fd = accept(listen_fd, NULL, NULL);
        if (client_fd == -1) {
            if (errno != EINTR)
                perror("accept");
            continue;
        }

        // 开始读取字节
        char buffer[RECV_BUFFER_SIZE];
        while(1) {
            // 接受数据，recv 返回实际接受长度
            ssize_t received = recv(client_fd, buffer, sizeof(buffer), 0);

            if (received == 0)
                break;
            if (received == -1) {
                if (errno == EINTR)
                    continue;
                perror("recv");
                break;
            }

            // offset 表示已经打印多少字节
            size_t offset = 0;
            while (offset < (size_t)received) {
                // fwrite 返回实际输出的长度
                size_t written = fwrite(buffer + offset , 1, (size_t)received - offset , stdout);

                if (written == 0 || ferror(stdout)) {
                    fprintf(stderr, "Failed to write standard output\n");
                    close(client_fd);
                    close(listen_fd);
                    return 1;
                }

                offset += written;
            }

            // 刷新缓冲区
            if (fflush(stdout) == EOF) {
                perror("fflush");
                close(client_fd);
                close(listen_fd);
                return 1;
            }
        }
        
        if (close(client_fd) == -1)
            perror("close");
    }

    return 0;
}

/*
 * main():
 * Parse command-line arguments and call server function
*/
int main(int argc, char **argv) {
  char *server_port;

  if (argc != 2) {
    fprintf(stderr, "Usage: ./server-c [server port]\n");
    exit(EXIT_FAILURE);
  }

  server_port = argv[1];
  return server(server_port);
}
