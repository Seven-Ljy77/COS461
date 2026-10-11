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

/* TODO: server()
 * Open socket and wait for client to connect
 * Print received message to stdout
 * Return 0 on success, non-zero on failure
*/
int server(char *server_port) {
  struct addrinfo hints = {0};
  struct addrinfo *result = NULL;
  struct addrinfo *address;
  int listen_fd = -1;
  int reuse = 1;
  char buffer[RECV_BUFFER_SIZE];

  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_flags = AI_PASSIVE;
  int status = getaddrinfo(NULL, server_port, &hints, &result);
  if (status != 0) {
    fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(status));
    return 1;
  }

  for (address = result; address != NULL; address = address->ai_next) {
    listen_fd = socket(address->ai_family, address->ai_socktype,
                       address->ai_protocol);
    if (listen_fd == -1) {
      perror("socket");
      continue;
    }
    if (setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR,
                   &reuse, sizeof(reuse)) == -1) {
      perror("setsockopt");
    } else if (bind(listen_fd, address->ai_addr, address->ai_addrlen) == 0) {
      break;
    } else {
      perror("bind");
    }
    close(listen_fd);
    listen_fd = -1;
  }
  freeaddrinfo(result);
  if (listen_fd == -1)
    return 1;
  if (listen(listen_fd, QUEUE_LENGTH) == -1) {
    perror("listen");
    close(listen_fd);
    return 1;
  }

  for (;;) {
    int client_fd = accept(listen_fd, NULL, NULL);
    if (client_fd == -1) {
      if (errno != EINTR)
        perror("accept");
      continue;
    }
    for (;;) {
      ssize_t received = recv(client_fd, buffer, sizeof(buffer), 0);
      if (received == 0)
        break;
      if (received == -1) {
        if (errno == EINTR)
          continue;
        perror("recv");
        break;
      }
      size_t offset = 0;
      while (offset < (size_t)received) {
        size_t written = fwrite(buffer + offset, 1,
                                (size_t)received - offset, stdout);
        if (written == 0 || ferror(stdout)) {
          fprintf(stderr, "Failed to write standard output\n");
          close(client_fd);
          close(listen_fd);
          return 1;
        }
        offset += written;
      }
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
