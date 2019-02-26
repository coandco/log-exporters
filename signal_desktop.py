#!/usr/bin/env python

import argparse
import json
import time
import os
import sys

from pysqlcipher import dbapi2 as sqlite
from contextlib import contextmanager
from unidecode import unidecode
from slugify import slugify
from emoji import demojize


DEBUG = False

if sys.platform.startswith('win32'):
    APPDATA = os.getenv('APPDATA')
    CONFIG_PATH = os.path.join(APPDATA, 'Signal', 'config.json')
    DB_PATH = os.path.join(APPDATA, 'Signal', 'sql', 'db.sqlite')
elif sys.platform.startswith('darwin'):
    CONFIG_PATH = os.path.expanduser('~/Library/Application Support/Signal/config.json')
    DB_PATH = os.path.expanduser('~/Library/Application Support/Signal/sql/db.sqlite')
else:
    CONFIG_PATH = os.path.expanduser('~/.config/Signal/config.json')
    DB_PATH = os.path.expanduser('~/.config/Signal/sql/db.sqlite')

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@contextmanager
def open_db(key, db_path):
    connection = None
    try:
        connection = sqlite.connect(db_path)
        connection.row_factory = dict_factory
        cur = connection.cursor()
        cur.execute("""PRAGMA key="x'%s'";""" % key)
        yield cur
    finally:
        if connection:
            connection.close()


def make_name(record):
    if record["name"]:
        return record["name"]
    elif record["profileName"]:
        return "~" + record["profileName"]
    elif record["type"] == "group":
        return "Unknown group"
    else:
        return str(record["id"])


def make_text_log(id_list, outgoing_name, message):
    time_string = time.strftime('[%Y-%m-%d %H:%M:%S]', time.localtime(int(message['received_at']) / 1000.0))

    message_type = message.get("type", "unknown")
    if message_type == "incoming":
        name = id_list[int(message["source"])]
        if message["attachments"]:
            attach_message = "[Attachment(s): %s] " % ", ".join(
                [x["fileName"] or x["contentType"] for x in message["attachments"]])
        else:
            attach_message = ''
        body = attach_message + demojize(message.get('body') or "")
    elif message_type == "outgoing":
        name = outgoing_name
        if message["attachments"]:
            attach_message = "[Attachment(s): %s] " % ", ".join(
                [x["fileName"] or x["contentType"] for x in message["attachments"]])
        else:
            attach_message = ''
        body = attach_message + demojize(message.get('body') or "")
    elif message_type == "keychange":
        name = id_list[int(message["key_changed"])]
        body = "[Safety number changed]"
    elif message_type == "verified-change":
        name = id_list[int(message["verifiedChanged"])]
        body = "[Contact verification status set to %s]" % message["verified"]
    else:
        if DEBUG:
            print("Error: message with unknown type")
            print("Message contents:")
            print(json.dumps(message, indent=4))
        return None

    outstring = u"{} {}: {}".format(time_string, name, body)
    return unidecode(outstring)


def process_convo(cur, id_list, convo_id, outgoing_name, output_dir):
    filename = "%s.txt" % slugify(demojize(id_list[convo_id]))
    with open(os.path.join(output_dir, filename), "w") as outfile:
        cur.execute("select json from messages where conversationId = ? order by sent_at asc", [convo_id])
        convo_objs = [json.loads(x["json"]) for x in cur.fetchall()]
        for message in convo_objs:
            line = make_text_log(id_list, outgoing_name, message)
            if line:
                outfile.write(line + "\n")


def main(key, db_path, outgoing_name, output_dir):
    with open_db(key, db_path) as cur:
        cur.execute("select * from conversations;")
        id_list = {x["id"]: make_name(x) for x in cur.fetchall()}
        for convo_id in id_list.keys():
            process_convo(cur, id_list, convo_id, outgoing_name, output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    key_methods = parser.add_mutually_exclusive_group()
    key_methods.add_argument('-j', '--json', default=CONFIG_PATH,
                             help="Location of Signal's config.json with the decryption key")
    key_methods.add_argument('-k', '--key', help="Decryption key for Signal Desktop database")
    parser.add_argument('-d', '--db-path', default=DB_PATH, help="Location of the encrypted Signal sqlite.db file")
    parser.add_argument('-i', '--i-am', default="me", help="Name to tag outgoing messages with")
    parser.add_argument('output_dir', help="Directory to output log files to")

    args = parser.parse_args()
    if args.key:
        resolved_key = args.key
    else:
        with open(args.json, 'r') as config:
            resolved_key = json.load(config).get("key")

    main(resolved_key, args.db_path, args.i_am, args.output_dir)
