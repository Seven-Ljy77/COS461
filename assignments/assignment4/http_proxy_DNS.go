/*****************************************************************************
 * http_proxy_DNS.go
 * Names: 刘嘉逸
 * NetIds: 10254602402
 *****************************************************************************/

package main

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"fmt"
	"io"
	"mime"
	"net"      // 用于监听 tcp 连接
	"net/http" // 用于解析 http 请求
	"net/url"
	"os"      // 用于获取命令行参数
	"strconv" // 处理字符串
	"strings"

	"golang.org/x/net/html"
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

	// 把上游响应原样发给客户端，同时留一份副本供 DNS 预取。
	var rawResponse bytes.Buffer
	_, err = io.Copy(io.MultiWriter(client, &rawResponse), response)
	if err != nil {
		fmt.Printf("Response forwarding failed: %v", err)
		return
	}
	go PrefetchResponse(&rawResponse, request)
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

// PrefetchResponse 从响应副本中提取 HTML，供后台 DNS 预取使用。
func PrefetchResponse(rawResponse *bytes.Buffer, request *http.Request) {
	reader := bufio.NewReader(rawResponse)
	response, err := http.ReadResponse(reader, request)
	if err != nil {
		return
	}
	// 跳过临时响应，例如 103 Early Hints，再读取最终响应。
	for response.StatusCode >= 100 && response.StatusCode < 200 {
		response.Body.Close()
		if response.StatusCode == 101 {
			return
		}
		response, err = http.ReadResponse(reader, request)
		if err != nil {
			return
		}
	}
	defer response.Body.Close()

	contentType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || contentType != "text/html" {
		return
	}

	// ReadResponse 会处理分块传输。gzip 正文还需要单独解压。
	var body io.Reader = response.Body
	encoding := strings.ToLower(strings.TrimSpace(response.Header.Get("Content-Encoding")))
	switch encoding {
	case "", "identity":
	case "gzip":
		uncompressed, err := gzip.NewReader(body)
		if err != nil {
			return
		}
		defer uncompressed.Close()
		body = uncompressed
	default:
		return
	}

	PrefetchLinks(body)
}

// PrefetchLinks 逐个读取 HTML 标签，找出 a 标签的 HTTP(S) 链接。
func PrefetchLinks(body io.Reader) {
	tokenizer := html.NewTokenizer(body)
	seen := make(map[string]bool)

	for {
		tokenType := tokenizer.Next()
		if tokenType == html.ErrorToken {
			return
		}
		if tokenType != html.StartTagToken && tokenType != html.SelfClosingTagToken {
			continue
		}

		token := tokenizer.Token()
		if token.Data != "a" {
			continue
		}
		for _, attr := range token.Attr {
			if attr.Key != "href" || !strings.HasPrefix(attr.Val, "http") {
				continue
			}
			link, err := url.Parse(attr.Val)
			if err != nil || link.Host == "" || (link.Scheme != "http" && link.Scheme != "https") {
				continue
			}

			// DNS 只需要主机名。SplitHostPort 也兼容课程 VM 的旧版 Go。
			host := link.Host
			if name, _, err := net.SplitHostPort(host); err == nil {
				host = name
			}
			host = strings.ToLower(strings.Trim(host, "[]"))
			if host == "" || net.ParseIP(host) != nil || seen[host] {
				continue
			}

			seen[host] = true
			net.LookupHost(host)
		}
	}
}
