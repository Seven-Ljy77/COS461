# 测试脚本说明

本目录下有同一套测试脚本的**两个版本**，测试内容与判定逻辑完全一致，仅支持的 Python 运行环境不同：

| 目录 | 运行环境 | 说明 |
|------|----------|------|
| `py2/` | Python 2.7 | 课程原始脚本，**未做任何修改**（字节级一致） |
| `py3/` | Python 3.6+ | Python 3 移植版，Windows / Linux / 课程虚拟机均可直接运行 |

> 注意：实验 PDF 和 README 中写的 `python test_scripts/test_proxy.py ...`
> 旧路径已不再存在，请按下面 NEW 的路径运行。

## 用法

在 `assignment4` 根目录（即 `http_proxy` / `http_proxy_DNS` 二进制所在目录）执行：

**Python 3 版（推荐，Windows 本机可直接跑）：**

```
python test_scripts/py3/test_proxy.py http_proxy <端口>        # 端口可省略，缺省随机
python test_scripts/py3/test_proxy_conc.py http_proxy <端口>

python test_scripts/py3/test_proxy.py http_proxy_DNS <端口>    # 测 DNS 预取版同理
```

**Python 2 版（课程虚拟机自带 python2 时）：**

```
python test_scripts/py2/test_proxy.py http_proxy <端口>
python test_scripts/py2/test_proxy_conc.py http_proxy <端口>
```

## Python 3 版与原版的差异（仅实现层面，测试行为不变）

- `print` 语句 → `print()` 函数；`urlparse` → `urllib.parse`
- `telnetlib`（Python 3.13 已从标准库删除）→ 内置 socket 实现的等效类，
  `read_all()` 同样是"读到对端关闭连接为止"，语义与原版完全一致
- `os.spawnl` / `os.kill` / `os.waitpid` → `subprocess.Popen`
  （`os.kill(pid, 0)` 在 Windows 上会真的杀死进程，原写法不可移植）
- HTTP 报文一律按 **bytes** 比较，与 Python 2 的行为一致
- `test_proxy_conc.py` 末尾的 apache benchmark 部分改为
  `subprocess` 调用 `ab`，**仍要求系统安装 ab**：
  - Linux：`sudo apt install apache2-utils`
  - Windows：可用 XAMPP / Apache HTTP Server 自带的 `ab.exe`（加入 PATH）
- 测试 URL 列表（`pub_urls`）、并发数、超时时长、比较逻辑均与原版一致

## 提示

- 代理二进制名直接写 `http_proxy` 即可（Windows 下会自动尝试 `http_proxy.exe`）。
- 三个默认测试网站（example.com 等）为境外站点，如网络不可达属网络问题，
  不是脚本或代理的问题；可自行修改 `pub_urls`（不影响评分）。
