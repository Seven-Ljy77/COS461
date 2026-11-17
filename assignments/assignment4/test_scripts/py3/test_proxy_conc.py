#!/usr/bin/env python3
#
# Python 3 port of the original Python 2 grader (test_proxy_conc.py).
# The tested behavior is unchanged; only the runtime was modernized:
#   * print statement          -> print() function
#   * urlparse module          -> urllib.parse
#   * telnetlib (removed in Python 3.13) -> small socket helper below
#   * os.spawnl/os.kill/waitpid-> subprocess.Popen (works the same on the
#     course VM and on Windows; os.kill(pid, 0) would kill the proxy on
#     Windows)
#   * os.popen4 (ab section)   -> subprocess.Popen with merged stdout/stderr
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

from time import sleep


class ThreadPool:
    """Flexible thread pool class.  Creates a pool of threads, then
    accepts tasks that will be dispatched to the next available
    thread."""

    def __init__(self, numThreads):

        """Initialize the thread pool with numThreads workers."""

        self.__threads = []
        self.__resizeLock = threading.Condition(threading.Lock())
        self.__taskLock = threading.Condition(threading.Lock())
        self.__tasks = []
        self.__processed = 0
        self.__isJoining = False
        self.setThreadCount(numThreads)

    def setThreadCount(self, newNumThreads):

        """ External method to set the current pool size.  Acquires the
        resizing lock, then calls the internal version to do real
        work."""

        # Can't change the thread count if we're shutting down the pool!
        if self.__isJoining:
            return False

        self.__resizeLock.acquire()
        try:
            self.__setThreadCountNolock(newNumThreads)
        finally:
            self.__resizeLock.release()
            return True

    def __setThreadCountNolock(self, newNumThreads):

        """Set the current pool size, spawning or terminating threads
        if necessary.  Internal use only; assumes the resizing lock is
        held."""

        # If we need to grow the pool, do so
        while newNumThreads > len(self.__threads):
            newThread = ThreadPoolThread(self)
            self.__threads.append(newThread)
            newThread.start()
        # If we need to shrink the pool, do so
        while newNumThreads < len(self.__threads):
            self.__threads[0].goAway()
            del self.__threads[0]

    def getThreadCount(self):

        """Return the number of threads in the pool."""

        self.__resizeLock.acquire()
        try:
            return len(self.__threads)
        finally:
            self.__resizeLock.release()

    def queueTask(self, task, args=None, taskCallback=None):

        """Insert a task into the queue.  task must be callable;
        args and taskCallback can be None."""

        if self.__isJoining == True:
            return False
        if not callable(task):
            return False

        self.__taskLock.acquire()
        try:
            self.__tasks.append((task, args, taskCallback))
            return True
        finally:
            self.__taskLock.release()

    def getNextTask(self):

        """ Retrieve the next task from the task queue.  For use
        only by ThreadPoolThread objects contained in the pool."""

        self.__taskLock.acquire()
        try:
            if self.__tasks == []:
                return (None, None, None)
            else:
                self.__processed = self.__processed + 1
                task = self.__tasks.pop(0)
                return task
        finally:
            self.__taskLock.release()

    def joinAll(self, waitForTasks=True, waitForThreads=True):

        """ Clear the task queue and terminate all pooled threads,
        optionally allowing the tasks and threads to finish."""

        # Mark the pool as joining to prevent any more task queueing
        self.__isJoining = True

        # Wait for tasks to finish
        if waitForTasks:
            while self.__tasks != []:
                sleep(0.1)

        # Tell all the threads to quit
        self.__resizeLock.acquire()
        try:
            # Wait until all threads have exited
            if waitForThreads:
                for t in self.__threads:
                    t.goAway()
                for t in self.__threads:
                    t.join()
                    del t
            self.__setThreadCountNolock(0)
            self.__isJoining = True

            # Reset the pool for potential reuse
            self.__isJoining = False
        finally:
            self.__resizeLock.release()


class ThreadPoolThread(threading.Thread):
    """ Pooled thread class. """

    threadSleepTime = 0.1

    def __init__(self, pool):

        """ Initialize the thread and remember the pool. """

        threading.Thread.__init__(self)
        self.__pool = pool
        self.__isDying = False

    def run(self):

        """ Until told to quit, retrieve the next task and execute
        it, calling the callback if any.  """

        while self.__isDying == False:
            cmd, args, callback = self.__pool.getNextTask()
            # If there's nothing to do, just sleep a bit
            if cmd is None:
                sleep(ThreadPoolThread.threadSleepTime)
            elif callback is None:
                cmd(args)
            else:
                callback(cmd(args))

    def goAway(self):

        """ Exit the run loop next time through."""

        self.__isDying = True


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

pub_conc = ['http://example.com/']
pub_ab = ['http://example.com/', ]
ab_conc = ['-n 20 -c 1', '-n 200 -c 10']

sleep_time = 5
# timeout_secs - Individual tests will be killed if they do not
# complete within this span of time.
timeout_secs = 60.0
concurrency_tries = [2, 10]
tries = 1
separator = "________________________________________\n"


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

    c = 0
    while (c < tries):
        c += 1
        print('Binary: %s' % proxy_bin)
        print('Running on port %s\n' % port)

        # Start the proxy running in the background
        proxy_bin = resolve_binary(proxy_bin)
        proc = subprocess.Popen([proxy_bin, port])

        # Give the proxy time to start up and start listening on the port
        time.sleep(sleep_time)

        totalcount = 0
        passcount = 0

        for count in concurrency_tries:
            for url in pub_conc:
                totalcount += 1
                print('### %d. Testing %d concurrent connects to %s' % (test_num, count, url))
                passed = run_test(concurrent_connect, (count, port, url), proc)
                if proc.poll() is not None:
                    print('!!!Proxy process experienced abnormal termination during test- restarting proxy!')
                    (proc, port) = restart_proxy(proxy_bin, port, proc)
                    passed = False

                if passed:
                    print('Connect to %s, %d concurrently: SUCCESS' % (url, count))
                    passcount += 1
                else:
                    print('Connect to %s, %d concurrently: FAILURE' % (url, count))
                test_num += 1
                print(separator)

        for count in concurrency_tries:
            for url in pub_conc:
                totalcount += 1
                print('### %d. Testing %d concurrent fetches to %s' % (test_num, count, url))
                passed = run_test(concurrent_fetch, (count, port, url), proc)
                if proc.poll() is not None:
                    print('!!!Proxy process experienced abnormal termination during test- restarting proxy!')
                    (proc, port) = restart_proxy(proxy_bin, port, proc)
                    passed = False

                if passed:
                    print('Fetch to %s, %d concurrently: SUCCESS' % (url, count))
                    passcount += 1
                else:
                    print('Fetch to %s, %d concurrently: FAILURE' % (url, count))
                test_num += 1
                print(separator)

        for count in concurrency_tries:
            for url in pub_conc:
                totalcount += 1
                print('### %d. Testing %d concurrent split fetches' % (test_num, count))
                passed = run_test(concurrent_fetch_broken, (count, port, url), proc)
                if proc.poll() is not None:
                    print('!!!Proxy process experienced abnormal termination during test- restarting proxy!')
                    (proc, port) = restart_proxy(proxy_bin, port, proc)
                    passed = False

                if passed:
                    print('Fetch to %s, %d concurrently: SUCCESS' % (url, count))
                    passcount += 1
                else:
                    print('Fetch to %s, %d concurrently: FAILURE' % (url, count))
                test_num += 1
                print(separator)

        for arg in ab_conc:
            for url in pub_ab:
                totalcount += 1
                print('### %d. Testing apache benchmark on args [%s]' % (test_num, arg))
                cmdstr = "ab -X 127.0.0.1:%s %s %s" % (port, arg, url)

                success = False
                # os.popen4() equivalent: run ab with stdout and stderr merged
                abproc = subprocess.Popen(cmdstr, shell=True,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT,
                                          universal_newlines=True)
                for line in abproc.stdout:
                    line = line.rstrip('\r\n')
                    print("    %s" % line.strip())
                    if line.find("Failed requests:        0") >= 0:
                        success = True
                abproc.wait()

                if success:
                    print('%s with args %s: SUCCESS' % (url, arg))
                    passcount += 1
                else:
                    print('%s with args %s: FAILURE' % (url, arg))
                    (proc, port) = restart_proxy(proxy_bin, port, proc)
                test_num += 1
                print(separator)

        # Cleanup
        terminate(proc)

        if passcount_file != None:
            with open(passcount_file, 'w') as f:
                f.write(str(passcount))

        if testcount_file != None:
            with open(testcount_file, 'w') as f:
                f.write(str(totalcount))

        print('Summary: ')
        print('\tType %s: %d of %d tests passed.' % ("multi-process", passcount, totalcount))
        port = str(random.randint(1025, 49151))


def usage():
    print("Usage: proxy_tester.py path/to/proxy/binary [port]")
    print("  Omit the port argument for a randomly generated port.")


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


def concurrent_connect(argtuple):
    global _connected

    count, port, url = argtuple

    pool = ThreadPool(count)
    for cnt in range(count):
        pool.queueTask(do_connect, ('localhost', port))
    pool.joinAll()

    result = compare_url((url, port))

    for item in _connected:
        if item[1] == True:
            item[0].close()
        else:
            result = False
    _connected = []
    return result


def concurrent_fetch(argtuple):
    global _connected
    global _success

    _success = 0

    count, port, url = argtuple

    pool = ThreadPool(count)
    for cnt in range(count):
        pool.queueTask(do_http_send, ('localhost', port, url))
    pool.joinAll()

    result = compare_url((url, port))

    pool = ThreadPool(count)
    for item in _connected:
        if item[1] == True:
            pool.queueTask(do_http_read, (item[0], item[2]))
    pool.joinAll()

    _connected = []
    return _success == count and result


def concurrent_fetch_broken(argtuple):
    global _connected
    global _success

    _success = 0

    count, port, url = argtuple

    pool = ThreadPool(count)
    for cnt in range(count):
        pool.queueTask(do_http_send_partial, ('localhost', port, url))
    pool.joinAll()

    result = compare_url((url, port))

    connected = _connected

    pool = ThreadPool(count)
    for item in connected:
        if item[1] == True:
            pool.queueTask(do_http_send_finish, item[0])
    pool.joinAll()

    pool = ThreadPool(count)
    for item in _connected:
        if item[1] == True:
            pool.queueTask(do_http_read, (item[0], item[2]))
    pool.joinAll()

    _connected = []
    return _success == count and result


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
    return data


_connected = []
_success = 0


def do_connect(argtuple):
    global _connected
    host, port = argtuple
    conn = Telnet()
    try:
        conn.open(host, port)
        _connected.append((conn, True))
    except socket.error:
        print('!!! do_connect: Socket error while attempting to talk to proxy: %s port %s' % (host, port))
        _connected.append((conn, False))


def do_http_send(argtuple):
    global _connected
    host, port, url = argtuple
    conn = Telnet()
    try:
        data = 'GET %s HTTP/1.1\r\nConnection: close\r\n\r\n' % url
        conn.open(host, port)
        conn.write(data)
        _connected.append((conn, True, url))
    except socket.error:
        print('!!!! do_http_send: Socket error while attempting to talk to proxy: %s port %s' % (host, port))
        _connected.append((conn, False, url))


def do_http_read(argtuple):
    global _success

    conn, url = argtuple
    try:
        proxy_data = conn.read_all()
        conn.close()

        urldata = urlparse(url)
        try:
            (host, hostport) = urldata[1].split(':')
        except ValueError:
            host = urldata[1]
            hostport = 80

        # Retrieve directly
        direct_data = get_direct(host, hostport, urldata[2])

        passed = compare_responses(proxy_data, direct_data)

        if passed:
            _success += 1
    except socket.error:
        print('!!!! do_http_read: Socket error while attempting to talk to proxy')


def do_http_send_partial(argtuple):
    global _connected
    host, port, url = argtuple
    conn = Telnet()
    try:
        data = 'GET %s ' % url
        conn.open(host, port)
        conn.write(data)
        _connected.append((conn, True, url))
    except socket.error:
        print('!!!! do_http_send_partial: Socket error while attempting to talk to proxy: %s port %s' % (host, port))
        _connected.append((conn, False, url))


def do_http_send_finish(conn):
    try:
        data = 'HTTP/1.1\r\nConnection: close\r\n\r\n'
        conn.write(data)
    except socket.error:
        print('!!!! do_http_send_finish: Socket error while attempting to talk to proxy')


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
    '''Stops and cleans up a running child process.  Idempotent: a proxy
    that already exited is simply ignored (the Python 2 original asserted
    liveness here and crashed when called twice).'''
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=sleep_time)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def restart_proxy(binary, oldport, oldchild):
    '''Restart the proxy on a new port number.'''
    terminate(oldchild)
    newport = str(int(oldport) + 1)
    proc = subprocess.Popen([binary, newport])
    time.sleep(sleep_time)
    return (proc, newport)


if __name__ == '__main__':
    main()
