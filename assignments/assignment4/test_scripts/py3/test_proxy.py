#!/usr/bin/env python3
#
# Python 3 port of the original Python 2 grader (test_proxy.py).
# The tested behavior is unchanged; only the runtime was modernized:
#   * print statement          -> print() function
#   * urlparse module          -> urllib.parse
#   * telnetlib (removed in Python 3.13) -> small socket helper below
#   * os.spawnl/os.kill/waitpid-> subprocess.Popen (works the same on the
#     course VM and on Windows; os.kill(pid, 0) would kill the proxy on
#     Windows)
#   * HTTP payloads are handled as bytes, so responses are compared
#     byte-for-byte exactly like the Python 2 original did.

import os
import random
import subprocess
import sys
import socket
import time
import threading
from urllib.parse import urlparse

try:
    import proxy_grade_private
    use_private = True
except ImportError:
    use_private = False

# pub_urls - The list of URLs to compare between the proxy
# and a direct connection.
#
# You can create additional automated tests for your proxy by
# adding URLs to this array.  This will have no effect on your
# grade, but may be helpful in testing and debugging your proxy.
#
# When you are testing against real web servers on the Internet,
# you may see minor differences between the proxy-fetched page and
# the regular page- possibly due to load balancing or dynamically
# generated content.  If there is only a single line that doesn't
# match between the two, it is likely a product of this sort of
# variation.
#
# Note that since this test script compares transaction output from
# the proxy and the direct connection, using invalid URLs may
# produce unexpected results, including the abnormal termination of
# the testing script.
#
pub_urls = ['http://example.com/', 'http://sns.princeton.edu/projects/',
            'http://randomwalker.info/'];

# timeout_secs - Individual tests will be killed if they do not
# complete within this span of time.
timeout_secs = 30.0
separator = "________________________________________\n"


class Telnet(object):
    """Minimal stand-in for the telnetlib.Telnet calls the original Python 2
    grader relied on (open/write/read_all/close).  read_all() blocks until
    the peer closes the connection, exactly like telnetlib did, so a proxy
    that fails to close the connection still triggers the test timeout."""

    def __init__(self, timeout=None):
        self.sock = None
        self.timeout = timeout

    def open(self, host, port):
        self.sock = socket.create_connection((host, int(port)), self.timeout)

    def write(self, data):
        if isinstance(data, str):
            data = data.encode('latin-1')
        self.sock.sendall(data)

    def read_all(self):
        chunks = []
        while True:
            data = self.sock.recv(65536)
            if not data:
                break
            chunks.append(data)
        return b''.join(chunks)

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None


def to_text(data):
    """Decode raw response bytes for display purposes only."""
    if isinstance(data, bytes):
        return data.decode('utf-8', 'replace')
    return str(data)


def resolve_binary(proxy_bin):
    """Keep the original os.spawnl() resolution behavior: a bare name such
    as "http_proxy" refers to the binary in the current directory."""
    if os.name == 'nt':
        if not os.path.exists(proxy_bin) and os.path.exists(proxy_bin + '.exe'):
            return proxy_bin + '.exe'
        return proxy_bin
    if os.sep not in proxy_bin:
        return os.path.join('.', proxy_bin)
    return proxy_bin


def main():
    global pub_urls
    try:
        proxy_bin = sys.argv[1]
    except IndexError:
        usage()
        sys.exit(2)
    try:
        if int(sys.argv[2]) >= 0:
            port = sys.argv[2]
        else:
            port = str(random.randint(1025, 49151))
    except (IndexError, ValueError):
        port = str(random.randint(1025, 49151))

    # the following arguments are only used for grading
    try:
        test_num = int(sys.argv[3])
    except IndexError:
        test_num = 1
    try:
        passcount_file = sys.argv[4]
    except IndexError:
        passcount_file = None
    try:
        testcount_file = sys.argv[5]
    except IndexError:
        testcount_file = None

    print('Binary: %s' % proxy_bin)
    print('Running on port %s\n' % port)

    # Start the proxy running in the background
    proxy_bin = resolve_binary(proxy_bin)
    proc = subprocess.Popen([proxy_bin, port])
    # Give the proxy time to start up and start listening on the port
    time.sleep(2)

    passcount = 0
    for url in pub_urls:
        print('### %d. Testing: ' % test_num + url)
        test_num += 1
        passed = run_test(compare_url, (url, port), proc)
        if proc.poll() is not None:
            print('!!!Proxy process experienced abnormal termination during test- restarting proxy!')
            (proc, port) = restart_proxy(proxy_bin, port)
            passed = False

        if passed:
            print('%s: SUCCESS' % url)
            passcount += 1
        else:
            print('%s: FAILURE' % url)
        print(separator)

    if (use_private):
        (priv_passed, test_count, proc) = proxy_grade_private.runall(port, proc, proxy_bin)

    # Cleanup
    terminate(proc)

    if passcount_file != None:
        with open(passcount_file, 'w') as f:
            f.write(str(passcount))

    if testcount_file != None:
        with open(testcount_file, 'w') as f:
            f.write(str(len(pub_urls)))

    print('Summary: ')
    print('\t%d of %d tests passed.' % (passcount, len(pub_urls)))
    if (use_private):
        print('%d of %d extended tests passed' % (priv_passed, test_count))


def usage():
    print("Usage: proxy_grader.py path/to/proxy/binary port")
    print("Omit the port argument for a randomly generated port.")


def run_test(test, args, child):
    '''
    Run a single test function, monitoring its execution with a timer thread.

    * test: A function to execute.  Should take a tuple as its sole
      argument and return True for a passed test, and False otherwise.
    * args: Tuple that contains the arguments to the test function
    * child: subprocess.Popen object of the running proxy

    The amount of time the monitor waits before killing the
    proxy process can be set by changing timeout_secs at the top of
    the file.

    Returns True for a passed test, False otherwise.
    '''
    monitor = threading.Timer(timeout_secs, do_timeout, [child])
    monitor.start()
    if not test(args):
        passed = False
    else:
        passed = True
    monitor.cancel()
    return passed


def compare_url(argtuple):
    '''
    Compare proxy output to the output from a direct server transaction.

    A simple sample test: download a web page via the proxy, and then fetch
    the same page directly from the server.  Compare the two pages for any
    differences, ignoring the Date header field if it is set.

    Argument tuples is in the form (url, port), where url is the URL to open, and
    port is the port the proxy is running on.
    '''
    (url, port) = argtuple
    urldata = urlparse(url)
    try:
        (host, hostport) = urldata[1].split(':')
    except ValueError:
        host = urldata[1]
        hostport = 80

    # Retrieve via proxy
    try:
        proxy_data = get_data('localhost', port, url)
    except socket.error:
        print('!!!! Socket error while attempting to talk to proxy!')
        return False

    # Retrieve directly
    direct_data = get_direct(host, hostport, urldata[2])

    # Compare responses
    return compare_responses(proxy_data, direct_data)


def compare_responses(proxy_data, direct_data, lenient_header=True):
    proxy_header = proxy_data.split(b"\r\n\r\n")[0]
    direct_header = direct_data.split(b"\r\n\r\n")[0]
    proxy_response_line = proxy_data.split(b"\r\n")[0]
    direct_response_line = direct_data.split(b"\r\n")[0]

    if b"200" in proxy_response_line:
        proxy_body = proxy_data.split(b"\r\n\r\n")[1].split(b"<html>")[-1]
    else:
        proxy_body = b""
    if b"200" in direct_response_line:
        direct_body = direct_data.split(b"\r\n\r\n")[1].split(b"<html>")[-1]
    else:
        direct_body = b""

    if proxy_response_line != direct_response_line:
        print("Response lines don't match:\n\nDirect: {}\nProxy:  {}\n".format(
            to_text(direct_response_line), to_text(proxy_response_line)))
        return False
    if not lenient_header:
        for proxy_h in proxy_header.split(b"\r\n"):
            if not proxy_h.startswith(b"Date") and not proxy_h.startswith(b"Expires") and not (proxy_h in direct_header):
                print("Headers don't match:\n\nDirect:\n{}\n\nProxy:\n{}\n".format(
                    to_text(direct_header), to_text(proxy_header)))
                return False
        for direct_h in direct_header.split(b"\r\n"):
            if not direct_h.startswith(b"Date") and not direct_h.startswith(b"Expires") and not (
                    direct_h in proxy_header):
                print("Headers don't match:\n\nDirect:\n{}\n\nProxy:\n{}\n".format(
                    to_text(direct_header), to_text(proxy_header)))
                return False
    if proxy_body != direct_body:
        print("HTML content doesn't match:\n\nDirect: {}\nProxy: {}\n".format(
            to_text(direct_body), to_text(proxy_body)))
        return False
    return True


def get_direct(host, port, url):
    '''Retrieve a URL using direct HTTP/1.1 GET.'''
    getstring = 'GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n'
    data = http_exchange(host, port, getstring % (url, host))
    return data


def get_data(host, port, url):
    '''Retrieve a URL using proxy HTTP/1.1 GET.'''
    getstring = 'GET %s HTTP/1.1\r\nConnection: close\r\n\r\n'
    data = http_exchange(host, port, getstring % url)
    # return data.split('\n')
    return data


def http_exchange(host, port, data):
    conn = Telnet()
    conn.open(host, port)
    conn.write(data)
    ret_data = conn.read_all()
    conn.close()
    return ret_data


def do_timeout(child):
    '''Callback run by the monitor threads to kill a long-running operation.'''
    print('!!!! Proxy transaction timed out after %d seconds' % timeout_secs)
    terminate(child)


def terminate(child):
    '''Stops and cleans up a running child process.'''
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def restart_proxy(binary, oldport):
    '''Restart the proxy on a new port number.'''
    newport = str(int(oldport) + 1)
    proc = subprocess.Popen([binary, newport])
    time.sleep(3)
    return (proc, newport)


if __name__ == '__main__':
    main()
