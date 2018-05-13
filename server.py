from socket import *
import os
from utils import *
from wsgiref.handlers import format_date_time


#=====CONSTANTS=========

METHODS = ['GET', 'HEAD']  # supported methods.
KEEP_ALIVE_DURATION = 5
STATUS_CODES = {200: 'OK', 404: 'Not Found', 206: 'Partial Content', 416: 'Range Not Satisfiable',
                304: 'Not Modified'}

#=======================


def serve_client_worker(client_socket, domains_to_paths, domains_to_logs):
    client_socket.settimeout(KEEP_ALIVE_DURATION)
    while True:
        try:
            request = client_socket.recv(1024)  # waits for 5 seconds.
            if not request:  # Client closed connection. request is empty bytes-type.
                break
        except (timeout, ConnectionResetError):
            break
        #print(request.decode())
        parsed_request = parse_request(request.decode())
        if parsed_request == -1:
            print('INVALID REQUEST.')
            break

        status, response, file_info, log_info = process_request(parsed_request, domains_to_paths)

        if parsed_request['method'] == 'HEAD':
            log_info['content_length'] = '0'
        log_info['peer_addr'] = client_socket.getpeername()[0]
        log_info['status'] = str(status)
        save_log(log_info, parsed_request, domains_to_logs)

        client_socket.send(response.encode())
        if (status == 200 or status == 206) and parsed_request['method'] == 'GET':
            res = send_file(client_socket, file_info[0], *file_info[1])
            if res == -1:
                break

        if parsed_request.get('connection') != 'keep-alive':  # Connection: close
            break # Connection must be closed.
    client_socket.close()
    return 0


# Returns dictionary of request headers(keys in lower case). -1 if request is invalid.
def parse_request(request):
    headers = {}
    lines = request.splitlines()  # Request lines
    request_line = lines[0].split()
    if len(request_line) < 3:
        return -1
    headers['method'] = request_line[0]  # GET or HEAD
    headers['filename'] = request_line[1].replace('%20', ' ')  # deal spaces in search bar.
    headers['http_version'] = request_line[2]
    if headers['method'] not in METHODS or headers['http_version'] != 'HTTP/1.1':
        return -1
    lines = lines[1:]
    for line in lines:
        temp = line.lower().split(':')
        if len(temp) >= 2:
            headers[temp[0]] = temp[1].strip()  # remove leading and ending whitespaces.
    return headers


def send_file(client_socket, file_path, offset, count):
    file = open(file_path, 'rb')
    client_socket.settimeout(None)
    sent = None
    try:
        sent = client_socket.sendfile(file, offset=offset, count=count)
    except BrokenPipeError:
        print('PipeError')
        sent = -1
    client_socket.settimeout(KEEP_ALIVE_DURATION)
    file.close()
    return sent


def process_request(parsed_request, domains_to_paths):
    date = get_curr_date()
    log_info = {'date': '[' + date + ']'}
    response = 'Date: ' + date + '\r\n'
    response += 'Server: ' + 'Python/3.6 Anaconda\r\n'

    if parsed_request.get('connection') == 'keep-alive':
        response += 'Keep-Alive: timeout=' + str(KEEP_ALIVE_DURATION) + '\r\n'
        response += 'Connection: keep-alive\r\n'
    else:
        response += 'Connection: close\r\n'

    domain = parsed_request.get('host')  # Can be None, in which case domain_directory also will be None.
    domain_directory = domains_to_paths.get(domain)
    if domain_directory is None:  # Wrong Host
        msg = 'REQUESTED DOMAIN NOT FOUND\r\n'
        response = not_found(response, msg, parsed_request['http_version'])
        log_info['content_length'] = str(len(msg))
        return 404, response, None, log_info

    filename = parsed_request['filename']
    if filename == '/':
        filename = '/index.html'
    file_path = domain_directory + filename
    try:
        file_size = os.path.getsize(file_path) # will raise FileNotFoundError if file does not exist.
    except (FileNotFoundError, IsADirectoryError):
        msg = 'REQUESTED RESOURCE NOT FOUND\r\n'
        response = not_found(response, msg, parsed_request['http_version'])
        log_info['content_length'] = str(len(msg))
        return 404, response, None, log_info

    # At this point file exists.
    file_type = get_file_type(file_path)

    log_info['content_length'] = str(file_size)
    response += 'Accept-Ranges: bytes\r\n'
    response += 'Cache-Control: max-age=5\r\n'
    response += 'Last-Modified: ' + format_date_time(os.path.getmtime(file_path)) + '\r\n'
    response += 'Content-Type: ' + file_type + '\r\n'

    if parsed_request.get('range') is None:
        response += 'Content-Length: ' + str(file_size) + '\r\n'
        response += 'Etag: ' + str(generate_tag(file_path)) + '\r\n'
        file_hashcode = parsed_request.get('if-none-match')
        if file_hashcode is not None and file_hashcode == generate_tag(file_path):
            response = parsed_request['http_version'] + ' 304 ' + STATUS_CODES[304] + '\r\n' + response + '\r\n'
            return 304, response, (file_path, (0, None)), log_info
        response = parsed_request['http_version'] + ' 200 ' + STATUS_CODES[200] + '\r\n' + response + '\r\n'
        return 200, response, (file_path, (0, None)), log_info
    else:
        offset, bound, count = parse_range(parsed_request['range'], file_size)
        if offset == bound == count == -1: # Not Satisfiable ranges.
            response += 'Content-Range: bytes */' + str(file_size) + '\r\n'
            response = parsed_request['http_version'] + ' 416 ' + STATUS_CODES[416] + '\r\n' + response + '\r\n'
            return 416, response, None, log_info
        response = response.replace('Keep-Alive: timeout=' + str(KEEP_ALIVE_DURATION) + '\r\n', '')
        response += 'Content-Range: bytes ' + offset + '-' + bound + '/' + str(file_size) + '\r\n'
        response += 'Content-Length: ' + str(count) + '\r\n'
        log_info['content_length'] = str(count)
        response = parsed_request['http_version'] + ' 206 ' + STATUS_CODES[206] + '\r\n' + response + '\r\n'
        return 206, response, (file_path, (int(offset), count)), log_info


def not_found(response, msg, http_version):
    response += 'Content-Type: text/plain\r\n'
    response += 'Content-Length: ' + str(len(msg)) + '\r\n'
    response = http_version + ' 404 ' + STATUS_CODES[404] + '\r\n' + response + '\r\n'
    response += msg
    return response


def parse_range(rang, file_size):
    bytes_range = rang.split('=')[-1]  # remove bytes=
    split = bytes_range.split('-')
    if bytes_range[-1] == '-':
        if int(split[0]) < 0 or int(split[0]) >= file_size:
            return -1, -1, -1
        return split[0], str(file_size - 1), file_size - 1 - int(split[0]) + 1
    elif bytes_range[0] == '-':
        if int(split[1]) < 0 or int(split[1]) >= file_size:
            return -1, -1, -1
        return '0', split[1], int(split[1]) - 0 + 1
    else:
        if (int(split[1]) - int(split[0])) < 0 or (int(split[1]) - int(split[0])) >= file_size:
            return -1, -1, -1
        return split[0], split[1], int(split[1]) - int(split[0]) + 1


def save_log(log_info, parsed_request, domains_to_logs):
    log = log_info['date'] + ' ' + log_info['peer_addr'] + ' ' + parsed_request['host'] + ' ' + \
          parsed_request['filename'] + ' ' + log_info['status'] + ' ' + log_info['content_length'] \
          + ' "' + parsed_request['user-agent'] + '"\n'
    if parsed_request['host'] in domains_to_logs:
        file = open(domains_to_logs[parsed_request['host']], 'a')
        file.write(log)
        file.close()
    else:
        file = open(domains_to_logs['error'], 'a')
        file.write(log)
        file.close()

