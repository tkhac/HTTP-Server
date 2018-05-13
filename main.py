from sys import argv, exit
from socket import *
from json import load, JSONDecodeError
import threading
from server import serve_client_worker
import os

LOG_PATH = None


# Function which represents hosts server socket.
# Runs in multiple threads.
def host_worker(address, domains_to_paths):
    domains_to_logs = create_log_files(domains_to_paths)
    print(address[0] + ':' + address[1], 'UP')
    server_socket = create_server_socket(address[0], int(address[1]))
    while True:
        connection_socket, request_address = server_socket.accept()
        threading.Thread(target=serve_client_worker, name=request_address[0] + ':' + str(request_address[1]),
                         args=(connection_socket, domains_to_paths, domains_to_logs)).start()


def create_log_files(domains_to_paths):
    if not os.path.exists(LOG_PATH):
        os.mkdir(LOG_PATH)
    domains_to_logs = {}
    for domain in domains_to_paths:
        log = LOG_PATH + '/' + domain + '.log'
        domains_to_logs[domain] = log
        f = open(log, 'w')
        f.close()
    log = LOG_PATH + '/' + 'error' + '.log'
    domains_to_logs['error'] = log
    f = open(log, 'w')
    f.close()
    return domains_to_logs


def create_server_socket(ip, port):
    server_socket = socket(AF_INET, SOCK_STREAM)
    server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)  # ???
    server_socket.bind((ip, port))
    server_socket.listen(32)
    return server_socket


# Start threads for hosts.
def run_hosts(host_args):
    for host in host_args:
        threading.Thread(target=host_worker, name='Host: ' + host, args=(host.split(':'),
                                                                         host_args[host])).start()
    return 0


# Parses config so that it was passed host threads as arguments.
def parse_config(filename):
    config = None
    try:
        config_file = open(filename)
        config = load(config_file)  # parse json.
        config_file.close()
    except(FileNotFoundError, JSONDecodeError):
        print("FILE NOT FOUND OR NOT VALID JSON.")
        exit(1)

    global LOG_PATH
    LOG_PATH = config['log']

    args = {}
    for vhost in config['server']:
        address = vhost['ip'] + ':' + str(vhost['port'])
        doc_root = vhost['documentroot']
        if vhost['documentroot'][-1] == '/':
            doc_root = vhost['documentroot'][:-1]
        if address in args: # Checks if host already exists.
            args[address][vhost['vhost']] = doc_root
        else:
            args[address] = {vhost['vhost']: doc_root}
    return args


def main():
    if len(argv) < 2:
        print('NO CONFIG FILE.')
        return 0
    config_filename = argv[1]
    config = parse_config(config_filename) # arguments for host_worker.
    run_hosts(config)
    return 0


if __name__ == '__main__':
    main()

