#!/usr/bin/python

import yaml
import time
import sys
from emoji import demojize
from unidecode import unidecode

if len(sys.argv) < 2:
    print("Usage: %s [path/to/message.json]" % sys.argv[0])
    exit(1)

MESSAGES = open(sys.argv[1], 'r').read()
PARSED_MESSAGE_BLOB = yaml.safe_load(MESSAGES)
INORDER_MESSAGES = reversed(PARSED_MESSAGE_BLOB['messages'])

for message in INORDER_MESSAGES:
    time_string = time.strftime('[%Y-%m-%d %H:%M:%S]', time.localtime(int(message['timestamp_ms']) / 1000.0))
    message_string = demojize(message['content'].encode('latin-1').decode('utf-8'))
    if message['type'] == 'Share':
        message_string = message['share']['link']
    outstring = u"{} {}: {}".format(time_string, message['sender_name'], message_string)
    print(unidecode(outstring))