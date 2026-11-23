/*****************************************************************************
 * http_proxy_DNS.go
 * Names: 刘嘉逸
 * NetIds: 10254602402
 *****************************************************************************/

package main

import (
	"bufio"
	"bytes"
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

	// 定义变量语法
	var buffer bytes.Buffer
	// 同时向两个地方写入内容，客户端和 rawResponse 变量
	_, err = io.Copy(io.MultiWriter(client, &buffer), response)
	if err != nil {
		fmt.Printf("Response forwarding failed: %v", err)
		return
	}
	// go 关键字表示启动一个 goroutine 并发执行这个函数
	go PrefetchResponse(&buffer, request)
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
func PrefetchResponse(buffer *bytes.Buffer, request *http.Request) {
	// 使用带缓冲区的读取器读取 buffer
	reader := bufio.NewReader(buffer)

	// 读取具体字节
	response, err := http.ReadResponse(reader, request)
	if err != nil {
		return
	}

	// 跳过临时响应，例如 103 Early Hints，再读取最终响应。
	// 如果状态码在 [100 , 200) 直接，则进入循环
	for response.StatusCode >= 100 && response.StatusCode < 200 {
		// 关闭当前的读取器
		response.Body.Close()
		if response.StatusCode == 101 { // 101 表示服务器要切换通信协议
			return
		}

		// 重新读取下一个响应
		// 例如 103 之后服务器可能会再回复下一个 200 响应 , 因此需要连续读取响应 , 直到服务器返回有效响应
		response, err = http.ReadResponse(reader, request)
		if err != nil {
			return
		}
	}
	defer response.Body.Close()

	// 检查 content-type 响应头是否为 text/html
	contentType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || contentType != "text/html" {
		return
	}

	PrefetchLinks(response.Body)
}

// PrefetchLinks 逐个读取 HTML 标签，找出 a 标签
func PrefetchLinks(body io.Reader) {
	// tokenizer 类似一个 iterator , 每次调用 .Next() 都会获得下一个 html 标签的类型
	// 如果要获取这个标签的具体内容 , 调用 .Token()
	tokenizer := html.NewTokenizer(body)

	// 定义一个字典，记录哪些 <a> 中的链接已经被处理过
	dict := make(map[string]bool)

	for {
		tokenType := tokenizer.Next()

		// 已经读取结束
		if tokenType == html.ErrorToken {
			return
		}

		// 如果当前标签不是开始标签 , 也不是自闭和标签 (类似 <input />) 就跳过
		if tokenType != html.StartTagToken && tokenType != html.SelfClosingTagToken {
			continue
		}

		// 取得具体标签内容
		token := tokenizer.Token()
		if token.Data != "a" {
			continue
		}

		// 迭代当前 <a> 标签的所有属性 : Attribute
		for _, attr := range token.Attr {
			// href 属性就是 <a> 要跳转的链接
			// 如果这个属性不是 href , 或者这个 href 属性不是以 http 开头的 , 都跳过 , 看下一个属性
			// 老师要求只预取以 HTTP 开头的链接
			if attr.Key != "href" || !strings.HasPrefix(attr.Val, "http") {
				continue
			}

			// 将这个地址用 url 对象切成 url 的格式 , 切分失败或不是 http / https 就跳过
			link, err := url.Parse(attr.Val)
			if err != nil || link.Host == "" || (link.Scheme != "http" && link.Scheme != "https") {
				continue
			}

			// 只取链接中的主机名 + 端口 , 例如 example.com:8000
			host := link.Host

			// SplitHostPort 将其拆成主机名和端口格式 , 并只保留主机名
			if name, _, err := net.SplitHostPort(host); err == nil {
				host = name
			}

			// 整理主机名 + 端口号 , 去掉 [] 以及全部小写
			host = strings.ToLower(strings.Trim(host, "[]"))
			if host == "" || net.ParseIP(host) != nil || dict[host] {
				continue
			}

			// 更新字典 , 这个主机名查询过了
			dict[host] = true

			// 进行一次 DNS 解析 , 查询该主机对应的 IP 地址
			// 只进行查询 , 不保存结果 , 是为了将结果存入 DNS 缓存 , 从而使后续用户点击时更有可能命中缓存 , 从而省去一次 DNS 查询的步骤
			net.LookupHost(host)
		}
	}
}
