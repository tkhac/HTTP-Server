from hashlib import md5
from time import strftime, localtime
from magic import Magic


def get_file_type(file_path):
    mime = Magic(mime=True)
    return mime.from_file(file_path)


def generate_tag(file_path):
    h = md5()
    file = open(file_path, 'rb')
    while 1:
        MB = file.read(1000000) # read 1 MB
        if not MB:
            break
        h.update(MB)
    file.close()
    return h.hexdigest()


def get_curr_date():
    return strftime("%a %b %d %H:%M:%S %Y", localtime())

