/*****************************************************************************
 * client-c.c                                                                 
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

#define SEND_BUFFER_SIZE 2048


// 根据 getaddrinfo 的 result 创建 socket
int create_socket(struct addrinfo *result) {
    struct addrinfo *address;
    int sockfd = -1;
    
    // 这里起始没有循环，根据老师要求进行修改（不用循环 result）
    for (address = result; address == result ; address = address->ai_next) {
        // socket 函数三个参数：地址类型，socket 类型，协议
        //                     AF_INET  SOCK_STREAM  0
        sockfd = socket(address->ai_family , address->ai_socktype , address->ai_protocol);

        if (sockfd == -1) { // 失败
            perror("socket");
            // 这个 socket 创建失败，换下一个备选地址
            continue;
        }

        if (connect(sockfd, address->ai_addr, address->ai_addrlen) == 0) // 当前地址连接成功，确定使用这个，直接退出
            break;

        // 当前地址连接不上
        perror("connect");
        close(sockfd);

        // 有可能 socket 创建成功但 connect 连接不上，因此还要赋值
        sockfd = -1;
    }

    return sockfd;
}


/* TODO: client()
 * Open socket and send message from stdin.
 * Return 0 on success, non-zero on failure
*/
int client(char *server_ip, char *server_port) {
    struct addrinfo *result = NULL;     // getaddrinfo 函数最后返回多个地址，以链表形式存储在 result 中
    struct addrinfo hints = {0};        // hints 变量只用来放入 getaddrinfo 函数中，用于参考给 result 赋值

    // 设定参考值
    hints.ai_family = AF_INET;          // 定义地址类型为 IPv4
    hints.ai_socktype = SOCK_STREAM;    // 定义 socket 类型

    // getaddrinfo 这个函数会解析地址，将多个地址以链表形式存入 result，hints 仅用来参考赋值
    int status = getaddrinfo(server_ip, server_port, &hints, &result);

    if (status != 0) {
        // getaddrinfo 未成功时没有分配内存，不用 free
        fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(status));     // gai_strerror 函数用于将 getaddrinfo 返回的状态码解析为错误信息
        return 1;
    }
    
    int sockfd = create_socket(result);

    // connect 连接成功后，会在 socket 内记录地址以及端口信息，result 可以释放
    freeaddrinfo(result);
    if (sockfd == -1) // 所有地址都失败
        return 1;

    // buffer 用于存读取的字节，bytes_read 存读取的字节数
    char buffer[SEND_BUFFER_SIZE];
    size_t bytes_read;  // fread 返回 size_t 类型，因此 bytes_read 使用 size_t 类型
    
    // 从 stdin 读取字节，stdin 在运行程序时通过 < 指定
    // 写入 buffer 变量（缓冲区）
    // fread 返回当此读取的字节数
    while ((bytes_read = fread(buffer, 1, sizeof(buffer), stdin)) > 0) {
        // 单次读取最多 SEND_BUFFER_SIZE 个字节

        // offset 变量记录当此的 SEND_BUFFER_SIZE 个字节，已经发送了几个
        size_t offset = 0;
        while (offset < bytes_read) {
            // 通过 socket 发送数据，sockfd 指定 socket
            // 第二个参数 buffer + offset 指定发送字节的起始地址
            // 第三个参数 bytes_read - offset 表示希望发送字节的长度
            // 第四个参数控制发送行为，填 0
            // 函数返回值表示本次实际发送的字节长度
            ssize_t sent = send(sockfd , buffer + offset , bytes_read - offset , MSG_NOSIGNAL);
            // send 返回 ssize_t 类型

            // send 返回 0 表示本次未能发送
            // send 返回 -1 表示报错
            if (sent == -1 && errno == EINTR)   // 被系统中断 （？
                continue;
            
            if (sent <= 0) {
                if (sent == -1)
                    perror("send");
                else
                    fprintf(stderr, "send: no progress\n");
                close(sockfd);
                return 1;
            }
            offset += (size_t)sent;
        }
    }

    // 只有 ferror(stdin) 返回 0 时表示读取结束
    // 返回非零表示读取报错
    if (ferror(stdin) != 0) {
        fprintf(stderr, "Failed to read standard input\n");
        close(sockfd);
        return 1;
    }

    if (close(sockfd) == -1) {
        perror("close");
        return 1;
    }
    
    return 0;
}

/*
 * main()
 * Parse command-line arguments and call client function
*/
int main(int argc, char **argv) {
    char *server_ip;
    char *server_port;

    if (argc != 3) {
        fprintf(stderr, "Usage: ./client-c [server IP] [server port] < [message]\n");
        exit(EXIT_FAILURE);
    }

    server_ip = argv[1];
    server_port = argv[2];
    return client(server_ip, server_port);
}
