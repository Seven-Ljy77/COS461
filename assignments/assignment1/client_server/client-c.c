/*****************************************************************************
 * client-c.c                                                                 
 * Name:
 * NetId:
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


/* TODO: client()
 * Open socket and send message from stdin.
 * Return 0 on success, non-zero on failure
*/
int client(char *server_ip, char *server_port) {
  struct addrinfo hints = {0};
  struct addrinfo *result = NULL;
  struct addrinfo *address;
  int sockfd = -1;
  char buffer[SEND_BUFFER_SIZE];
  size_t bytes_read;

  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  int status = getaddrinfo(server_ip, server_port, &hints, &result);
  if (status != 0) {
    fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(status));
    return 1;
  }

  for (address = result; address != NULL; address = address->ai_next) {
    sockfd = socket(address->ai_family, address->ai_socktype,
                    address->ai_protocol);
    if (sockfd == -1) {
      perror("socket");
      continue;
    }
    if (connect(sockfd, address->ai_addr, address->ai_addrlen) == 0)
      break;
    perror("connect");
    close(sockfd);
    sockfd = -1;
  }
  freeaddrinfo(result);
  if (sockfd == -1)
    return 1;

  while ((bytes_read = fread(buffer, 1, sizeof(buffer), stdin)) > 0) {
    size_t offset = 0;
    while (offset < bytes_read) {
      ssize_t sent = send(sockfd, buffer + offset, bytes_read - offset,
                          MSG_NOSIGNAL);
      if (sent == -1 && errno == EINTR)
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
  if (ferror(stdin)) {
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
