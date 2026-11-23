# 华东师范大学数据科学与工程学院实验报告

- 课程名称：计算机网络
- 年级：大二
- 指导教师：赵明昊
- 姓名：刘嘉逸
- 学号：10254602402

## 一、实验任务

本次实验为 Assignment 4，使用 Go 实现 HTTP 代理，并增加 DNS 预取功能。

Part A 在 `http_proxy.go` 中实现并发 HTTP 代理。程序从命令行接收监听端口，接收客户端的 GET 请求，连接目标服务器，将请求转发给服务器，再将响应原样返回客户端。转发时使用路径加 Host 请求头的形式，并设置 `Connection: close`。对于不支持的方法、无效请求及代理捕获的处理错误，返回 HTTP 500。

Part B 在 `http_proxy_DNS.go` 中保留 Part A 的功能，并解析返回的 HTML，找到 a 标签中 href 以 http 开头的链接，提取主机名并调用 `net.LookupHost` 提前解析域名。解析 HTML 和 DNS 查询在后台 goroutine 中执行，避免客户端等待预取工作完成。

## 二、使用环境

| 用途 | 环境或工具 |
|---|---|
| 宿主系统与提交仓库 | Windows，`D:\programming\COS461-Public` |
| 代码编辑 | VS Code，通过 WSL 扩展连接 Ubuntu 22.04，使用 Go 扩展 |
| WSL 项目副本 | `/home/liujiayi/programming/COS461` |
| WSL Go 工具链 | Go 1.25.0，linux/amd64 |
| 最终编译与课程测试 | Vagrant、VirtualBox、课程提供的 Ubuntu 虚拟机 |
| 虚拟机作业目录 | `/vagrant/assignment4` |
| 测试工具 | telnet、Python 2 版课程脚本、ApacheBench（ab） |
| HTML 解析依赖 | 作业 src 目录中的 `golang.org/x/net/html` |

我在 WSL 中编辑和预编译，每完成阶段性工作后同步到 Windows 仓库，再由自己在 Vagrant 中重新编译、运行测试。老师提供的课程说明文件作为参考材料使用。

## 三、实验过程

### 1. 阅读说明并准备开发环境

开始时，我以为课程推荐 Python 2 意味着代理也需要 Python 2 编译。阅读说明和 Makefile 后，确认需要提交的是两个 Go 程序，Python 2 用于运行课程测试脚本。

考虑到虚拟机内直接编辑代码不方便，我选择使用 WSL 中的 VS Code 开发。通过 `uname -m` 确认架构为 x86_64，将下载到 Windows 桌面的 Go Linux amd64 压缩包解压到 WSL 的 `/usr/local`，在 `~/.bashrc` 中加入 Go 的 bin 路径。执行 `go version` 得到 `go version go1.25.0 linux/amd64`。随后在 VS Code 的 WSL 窗口安装 Go 扩展，获得补全、跳转和诊断功能。

我先在 WSL 中执行 `telnet www.baidu.com 80`，手动发送 GET 请求和 Host 请求头，观察到 HTTP 200、响应头以及 HTML 正文，理解了 HTTP 报文的基本组成。

### 2. Part A 的实现与语法学习

由于此前不熟悉 Go，我先请 AI 协助生成 Part A 初稿，再逐句阅读、提问，并修改注释和日志输出。重点学习了 package main、main 入口、import、多返回值、短变量声明、defer、goroutine，以及 fmt 输出和连接写入的区别。

程序首先检查命令行端口，再监听所有本机 IPv4 地址。主循环通过 Accept 接收连接，为每个连接启动一个 goroutine。

```go
listener, err := net.Listen("tcp4", ":"+os.Args[1])
if err != nil {
    fmt.Println(err)
    return
}
defer listener.Close()

for {
    client, err := listener.Accept()
    if err != nil {
        fmt.Println(err)
        return
    }
    go handleClient(client)
}
```

每个处理函数使用 `http.ReadRequest(bufio.NewReader(client))` 解析请求，检查方法和目标主机。ReadRequest 会填充 request.Host，因此删除了初稿里重复从 URL.Host 赋值的步骤。目标没有指定端口时补上 80，然后使用 net.Dial 主动连接目标服务器。

```go
request.Header.Set("Connection", "close")
err = request.Write(upstream)
```

Request.Write 会把完整 URL 转换为发送给源站的路径和查询参数，并写出 Host 请求头。例如，客户端请求 `http://www.baidu.com/`，代理向网站发送的请求目标为 `/`。

随后用 Peek(1) 等待第一个响应字节，成功后用 io.Copy 将状态行、响应头和正文原样转发。Peek 保留已查看的字节，后续转发仍从该字节开始。处理函数退出时，通过 defer 关闭客户端连接和上游连接。错误处理函数通过 fmt.Fprintf 写入客户端连接，返回完整的 HTTP 500 响应。

我在 WSL 启动代理后，另开终端连接 `127.0.0.1:8000`，发送访问百度的绝对 URL 请求，收到 HTTP 200 和百度首页 HTML，确认单个 GET 请求的转发过程能够完成。WSL 的基本测试脚本第一次有一个网址失败，重跑后达到 3/3。

### 3. Part B 的 DNS 预取实现

在保留 Part A 结构的基础上，B 部分增加响应副本和后台解析。

```go
var buffer bytes.Buffer
_, err = io.Copy(io.MultiWriter(client, &buffer), response)
if err != nil {
    fmt.Printf("Response forwarding failed: %v", err)
    return
}
go PrefetchResponse(&buffer, request)
```

MultiWriter 将每批响应字节依次写给客户端和内存缓冲区。完整响应转发结束后，后台 goroutine 从副本中解析 HTTP 响应，跳过 1xx 临时响应，检查 Content-Type 是否为 text/html，再读取正文中的链接。

HTML tokenizer 逐个识别标签和文字。程序保留开始标签和自闭合标签，再检查标签名是否为 a，遍历属性并筛选 href。通过 url.Parse 拆分 URL，只处理具有目标主机的 HTTP 和 HTTPS 链接。

```go
if attr.Key != "href" || !strings.HasPrefix(attr.Val, "http") {
    continue
}
link, err := url.Parse(attr.Val)
if err != nil || link.Host == "" ||
    (link.Scheme != "http" && link.Scheme != "https") {
    continue
}
```

预取前去掉端口和 IPv6 地址外的方括号，把主机名转成小写。使用 map 记录当前页面已处理过的域名，跳过重复域名和已经是 IP 地址的目标，最后调用 net.LookupHost。查询结果交由系统解析流程处理，程序无需保存 IP 列表。DNS 预取的目的是增加后续查询命中解析器缓存的机会。

本阶段由 AI 协助生成代码、解释语句并进行 WSL 编译和临时检查，我逐句学习后修改了变量名、注释并运行课程测试。目前保存的证据包括编译和代理测试结果，尚未包含 Wireshark 验证预取 DNS 查询的记录，也没有测量页面访问加速效果。

### 4. 解决编译环境差异

最初直接 make all 时，WSL 的现代 Go 默认采用模块模式，提示找不到 go.mod 和 HTML 解析包。尝试过生成 go.mod、go.sum，但课程虚拟机使用旧式 GOPATH 查找依赖，仍然到 assignment5/src 下寻找 HTML 库。后来统一使用老师提供的 src 目录，并删除临时模块配置。

WSL 中使用以下方式编译。

```bash
cd ~/programming/COS461/assignments/assignment4
export GO111MODULE=off
export GOPATH="$PWD"
make all
```

Vagrant 中使用以下方式编译。

```bash
cd /vagrant/assignment4
export GOPATH="$PWD"
make clean
make all
```

两个文件都包含 package main 和 main 函数，VS Code 按目录检查时会提示重复声明。Makefile 分别指定源文件构建两个独立程序，实际编译能够通过。

### 5. Vagrant 中的测试结果

我同步代码后，在 Vagrant 中重新编译并运行原版 Python 2 测试脚本。两份终端记录已按原文件复制到报告目录，完整结果可从以下链接查看。

- [http_proxy 完整测试记录](logs/test_for_http_proxy.txt)
- [http_proxy_DNS 完整测试记录](logs/test_for_http_proxy_DNS.txt)

```bash
python test_scripts/py2/test_proxy.py http_proxy 8080
python test_scripts/py2/test_proxy_conc.py http_proxy 8080
python test_scripts/py2/test_proxy.py http_proxy_DNS 8080
python test_scripts/py2/test_proxy_conc.py http_proxy_DNS 8080
```

| 检查项 | http_proxy | http_proxy_DNS |
|---|---|---|
| 虚拟机编译 | 通过 | 通过 |
| 基本网址转发 | 3/3 | 3/3 |
| 2、10 个客户端并发连接 | 通过 | 通过 |
| 2、10 个客户端并发获取 | 通过 | 通过 |
| 2、10 个客户端分段发送请求 | 通过 | 通过 |
| ab，20 次请求、并发 1 | 通过 | 通过 |
| ab，200 次请求、并发 10 | 超时，完成 199 次 | 超时，完成 199 次 |
| 并发脚本汇总 | 7/8 | 7/8 |

以下节选来自 http_proxy 的测试记录，两个程序的基本测试汇总相同。

```text
Summary:
        3 of 3 tests passed.
```

以下节选来自 http_proxy_DNS 的最后一项压测。

```text
    apr_pollset_poll: The timeout specified has expired (70007)
    Total of 199 requests completed
http://example.com/ with args -n 200 -c 10: FAILURE

Summary:
        Type multi-process: 7 of 8 tests passed.
```

测试中的部分 EOF 日志还出现在已经通过的并发连接测试附近。结合单项判定分析，不能仅凭日志里出现 EOF 就判定整个测试失败，应同时查看对应测试项和最终汇总。

### 6. 最后一项压测的排查

两份程序最后一项压测均未全部完成，我随后单独运行 ab 进行对照。在 Vagrant 直接访问 example.com，200 次请求、并发 10 的一轮测试全部完成，Failed requests 为 0，总耗时约 11.636 秒。

```
vagrant@cos461:/vagrant/assignment4$ ab -n 200 -c 10 http://example.com/
This is ApacheBench, Version 2.3 <$Revision: 1528965 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking example.com (be patient)
Completed 100 requests
Completed 200 requests
Finished 200 requests


Server Software:        cloudflare
Server Hostname:        example.com
Server Port:            80

Document Path:          /
Document Length:        577 bytes

Concurrency Level:      10
Time taken for tests:   11.636 seconds
Complete requests:      200
Failed requests:        0
Total transferred:      177612 bytes
HTML transferred:       115400 bytes
Requests per second:    17.19 [#/sec] (mean)
Time per request:       581.785 [ms] (mean)
Time per request:       58.179 [ms] (mean, across all concurrent requests)
Transfer rate:          14.91 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        1    4   5.3      2      29
Processing:   215  569 948.9    350    4775
Waiting:      210  555 950.0    339    4772
Total:        217  573 953.9    352    4803

Percentage of the requests served within a certain time (ms)
  50%    352
  66%    396
  75%    418
  80%    432
  90%    480
  95%   4633
  98%   4708
  99%   4764
 100%   4803 (longest request)
vagrant@cos461:/vagrant/assignment4$
```

经过代理的后续测试结果有波动。一轮完成了 200 次，但产生 26 个非 2xx 响应和长度差异；加入分阶段错误日志后，另一轮有 193 次正常转发、7 次错误，错误均为 read upstream response: EOF。这表示请求已完成写入，但上游在发回第一个响应字节前关闭了连接。另有几轮在完成 199 次或 195 次后因等待剩余请求而超时。

```
// 启动代理服务器
./http_proxy

// 另一个终端内
vagrant@cos461:/vagrant/assignment4$ ab -X 127.0.0.1:8000 -n 200 -c 10 http://example.com/
This is ApacheBench, Version 2.3 <$Revision: 1528965 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking example.com [through 127.0.0.1:8000] (be patient)
Completed 100 requests
Completed 200 requests
Finished 200 requests


Server Software:        cloudflare
Server Hostname:        example.com
Server Port:            80

Document Path:          /
Document Length:        589 bytes

Concurrency Level:      10
Time taken for tests:   15.834 seconds
Complete requests:      200
Failed requests:        9
   (Connect: 0, Receive: 0, Length: 9, Exceptions: 0)
Non-2xx responses:      9
Total transferred:      178260 bytes
HTML transferred:       112634 bytes
Requests per second:    12.63 [#/sec] (mean)
Time per request:       791.676 [ms] (mean)
Time per request:       79.168 [ms] (mean, across all concurrent requests)
Transfer rate:          10.99 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    2   5.3      0      29
Processing:   237  762 1039.4    448    5883
Waiting:      232  742 1039.4    418    5789
Total:        237  763 1039.6    448    5883

Percentage of the requests served within a certain time (ms)
  50%    448
  66%    493
  75%    611
  80%    840
  90%   1296
  95%   5012
  98%   5025
  99%   5047
 100%   5883 (longest request)
vagrant@cos461:/vagrant/assignment4$
```

我还关闭 Clash Verge 再次尝试，但仍出现完成 199 次后超时的情况。当前代码中的 Peek 和 io.Copy 都会等待上游数据，io.Copy 依赖上游关闭连接结束读取，程序没有设置网络读取超时。

对 WSL 与 Windows 的源码进行逐项检查后，两处代码内容一致，分别通过了 WSL Go 工具链的编译及 go vet 检查。结合已有基本测试和前七项并发测试，检查范围内未发现明确的主要功能实现错误。编译、静态检查和部分测试通过仍无法证明所有运行场景都正确。

我推测，本机访问国外 example.com 时的网络延迟、链路波动或上游连接行为可能影响高并发结果。不过直连曾全部通过，关闭 Clash 后也仍出现超时，因此现有记录尚不能确认最后一项失败完全由网络环境引起。最后一项保留实际失败结果和原因未确定的结论，现阶段停止继续排查。

## 四、总结

本次实验完成了两个代理程序，在课程虚拟机中编译成功，两份基本转发测试均通过 3/3，并发测试均通过 7/8。最后一项外网压测仍有请求未及时完成，报告保留了实际输出和排查过程。

通过逐句阅读和提问，我理解了 TCP 监听与主动连接的区别、每连接一个 goroutine 的处理方式、HTTP 请求和响应的组成，以及缓冲读取、字节转发和 DNS 预取的关系。我也认识到，编辑器诊断、编译通过、功能测试和性能测试分别提供不同层面的证据，判断结果需要结合真实输出。
