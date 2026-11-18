/*****************************************************************************
 * http_proxy.go
 * Names: 刘嘉逸
 * NetIds: 10254602402
 *****************************************************************************/

package main

import (
	"bufio"
	"fmt"
	"io"
	"net"      // 用于监听 tcp 连接
	"net/http" // 用于解析 http 请求
	"os"       // 用于获取命令行参数
	"strconv"  // 处理字符串
	"strings"
)

func main() {

	if len(os.Args) != 2 {
		fmt.Printf("Usage: %s <port>", os.Args[0])
		return
	}

	// := 是 go 的声明 + 赋值语法，可以在赋值的同时声明
	// strconv.Atoi 将字符串转换为 int，会返回两个值，因此同时赋值
	port, err := strconv.Atoi(os.Args[1])
	if err != nil || port < 1 || port > 65535 {
		fmt.Printf("Invalid port: %s", os.Args[1])
		return
	}

	// 开始 TCP 监听，显示指定 IPv4
	listener, err := net.Listen("tcp4", ":"+os.Args[1])
	if err != nil {
		fmt.Println(err)
		return
	}

	// main 函数执行结束时，关闭 TCP 连接
	defer listener.Close()

	fmt.Printf("HTTP proxy listening on %s\r\n", listener.Addr())
	for {
		// 等待 TCP 请求
		client, err := listener.Accept()
		if err != nil {
			fmt.Println(err)
			return
		}

		go handleClient(client)
	}
}

func handleClient(client net.Conn) {
	defer client.Close()

	// 用 bufio 库 (buffered I/O)，实现带缓冲区的 http 读取与解析
	request, err := http.ReadRequest(bufio.NewReader(client))
	if err != nil {
		ResponseError(client, err)
		return
	}

	if request.Method != "GET" {
		ResponseError(client, fmt.Errorf("unsupported method: %s", request.Method))
		return
	}
	if request.URL.Scheme != "" && request.URL.Scheme != "http" {
		ResponseError(client, fmt.Errorf("unsupported scheme: %s", request.URL.Scheme))
		return
	}
	if request.Host == "" {
		ResponseError(client, fmt.Errorf("missing target host"))
		return
	}

	// 如果没有显式指定端口，就添加默认端口 80
	// 如果地址不含 : 或以 ] 结尾，就添加默认端口
	address := request.Host
	if !strings.Contains(address, ":") || strings.HasSuffix(address, "]") {
		address += ":80"
	}

	// 代理服务器主动建立到目标地址的连接
	upstream, err := net.Dial("tcp", address)
	if err != nil {
		ResponseError(client, err)
		return
	}
	defer upstream.Close()

	// 显式设置请求头，然后请求目标地址 (request.Write)
	request.Header.Set("Connection", "close")
	err = request.Write(upstream)
	if err != nil {
		ResponseError(client, err)
		return
	}

	response := bufio.NewReader(upstream)
	if _, err := response.Peek(1); err != nil {
		ResponseError(client, err)
		return
	}

	// io.Copy 向浏览器返回请求
	_, err = io.Copy(client, response)
	if err != nil {
		fmt.Printf("Response forwarding failed: %v", err)
		return
	}
	fmt.Printf("Proxy success : %s\r\n", address)
}

func ResponseError(client net.Conn, cause error) {
	fmt.Printf("Proxy request failed: %v\r\n", cause)

	// 向浏览器返回 500 响应
	body := "Internal Error\n"
	fmt.Fprintf(client, "HTTP/1.1 500 Internal Error\r\n"+
		"Content-Type: text/plain\r\n"+
		"Content-Length: %d\r\n"+
		"Connection: close\r\n\r\n%s", len(body), body)
}
