#!/usr/bin/env python

import subprocess
import mimetypes
import argparse
import tempfile
import sqlite3
import shutil
import json
import time
import sys
import os
import re

from distutils.spawn import find_executable
from contextlib import contextmanager
from hashlib import md5
from pathlib import Path
from datetime import datetime
from typing import Iterable
from packaging import version

from unidecode import unidecode
from slugify import slugify
from emoji import demojize

DEBUG = False

if sys.platform.startswith('win32'):
    APPDATA = os.getenv('APPDATA')
    CONFIG_PATH = os.path.join(APPDATA, 'Signal', 'config.json')
    DB_PATH = os.path.join(APPDATA, 'Signal', 'sql', 'db.sqlite')
    ATTACHMENT_PATH = os.path.join(APPDATA, 'Signal', 'attachments.noindex')
elif sys.platform.startswith('darwin'):
    CONFIG_PATH = os.path.expanduser('~/Library/Application Support/Signal/config.json')
    DB_PATH = os.path.expanduser('~/Library/Application Support/Signal/sql/db.sqlite')
    ATTACHMENT_PATH = os.path.expanduser('~/Library/Application Support/Signal/attachments.noindex')
else:
    CONFIG_PATH = os.path.expanduser('~/.config/Signal/config.json')
    DB_PATH = os.path.expanduser('~/.config/Signal/sql/db.sqlite')
    ATTACHMENT_PATH = os.path.expanduser('~/.config/Signal/attachments.noindex')

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@contextmanager
def open_db(key, db_path):
    connection = None
    tmpfd = None
    tmpfilename = None

    decryption_sql = (r'''PRAGMA key="x'{0}'"; '''
                      "ATTACH DATABASE '{1}' as foo KEY ''; "
                      "SELECT sqlcipher_export('foo'); "
                      "DETACH DATABASE foo; ")

    try:
        tmpfd, tmpfilename = tempfile.mkstemp()
        os.close(tmpfd)
        tmpfd = None
        decryption_cmd = ['sqlcipher',
                          db_path,
                          decryption_sql.format(key, tmpfilename)]
        subprocess.check_call(decryption_cmd)

        connection = sqlite3.connect(tmpfilename)
        connection.row_factory = dict_factory
        cur = connection.cursor()
        cur.execute("""PRAGMA key="x'%s'";""" % key)
        yield cur
    finally:
        if connection:
            connection.close()
        if tmpfd:
            os.close(tmpfd)
        if tmpfilename and os.path.isfile(tmpfilename):
            os.unlink(tmpfilename)


# Adapted from https://stackoverflow.com/a/54278929
def read_lines_from_end(filename: Path) -> Iterable[str]:
    with filename.open('rb') as f:
        try:  # catch OSError in case of a one line file
            f.seek(-2, os.SEEK_END)
            while True:
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
                curpos = f.tell()
                yield f.readline().decode()
                # Jump back to just before the newline we read
                f.seek(curpos-2)
        except OSError:
            f.seek(0)
            yield f.readline().decode()


TIMESTAMP_PATTERN = re.compile(r'^\[(?P<timestamp>[0-9: -]*)]')


def read_last_timestamp(filename: Path) -> float:
    for line in read_lines_from_end(filename):
        match = TIMESTAMP_PATTERN.search(line)
        if match:
            return datetime.strptime(match.group('timestamp'), "%Y-%m-%d %H:%M:%S").timestamp()
    # If we didn't find any timestamp, error
    raise ValueError(f"No timestamp found in file {filename}")


def make_name(record):
    name = str(record["id"])
    if record["name"]:
        name = record["name"]
    elif record["profileName"]:
        name = "~" + record["profileName"]
    elif record["type"] == "group":
        name = "Unknown group"
    # Names in Signal now use these direction indicators, so we need to remove them or they'll confuse our unidecode
    chars_to_remove = ['\u2068', '\u2069']
    return name.translate({ord(c): None for c in chars_to_remove})


def make_text_log(id_list, outgoing_name, message):
    message_time = time.localtime(int(message.get('received_at_ms', message['received_at'])) / 1000.0)
    time_string = time.strftime('[%Y-%m-%d %H:%M:%S]', message_time)

    message_type = message.get("type", "unknown")
    if message_type == "incoming":
        message_id = message.get("source", None) or message.get("sourceUuid", None)
        name = id_list[message_id] if message_id else "Unknown"
        if message["attachments"]:
            attach_message = "[Attachment(s): %s] " % ", ".join(
                ["%s(%s)" % (x.get("fileName", None) or x["contentType"], x.get("path", "N/A")) for x in message["attachments"]])
        else:
            attach_message = ''
        body = attach_message + demojize(message.get('body') or "")
    elif message_type == "outgoing":
        name = outgoing_name
        if message["attachments"]:
            attach_message = "[Attachment(s): %s] " % ", ".join(
                ["%s(%s)" % (x.get("fileName", None) or x["contentType"], x.get("path", "N/A")) for x in message["attachments"]])
        else:
            attach_message = ''
        body = attach_message + demojize(message.get('body') or "")
    elif message_type == "keychange":
        name = id_list.get(message.get("key_changed", ''), "Unknown")
        body = "[Safety number changed]"
    elif message_type == "verified-change":
        name = id_list.get(message["verifiedChanged"], "Unknown")
        body = "[Contact verification status set to %s]" % message["verified"]
    else:
        if DEBUG:
            print("Error: message with unknown type")
            print("Message contents:")
            print(json.dumps(message, indent=4))
        return None

    outstring = u"{} {}: {}".format(time_string, name, body)
    return unidecode(outstring)


def ensure_dir(dirname):
    try:
        os.makedirs(dirname)
    except OSError:
        if not os.path.isdir(dirname):
            raise


def copy_attachments(attachment_path, output_dir, message):
    atch_out_dir = Path(output_dir) / "attachments"
    atch_out_dir.mkdir(parents=True, exist_ok=True)
    for atch in message.get("attachments", []):
        # If we don't have a local copy of the file, we're done.
        if "path" not in atch.keys():
            continue

        if atch.get("fileName", None):
            filename = atch["fileName"]
        else:
            extension = mimetypes.guess_extension(atch["contentType"])
            if not extension:
                extension = "." + atch["contentType"].split("/")[-1]
            if extension == ".jpe":
                extension = ".jpg"
            identifier = (atch.get("attachment_identifier", None) or
                          atch.get("id", None) or
                          atch.get("cdnKey", None) or
                          md5(str(atch).encode('utf-8')).hexdigest())
            filename = "%s%s" % (identifier, extension)
        src = Path(attachment_path) / atch["path"]
        dest = Path(atch_out_dir) / filename
        shutil.copy2(src, dest)


def process_convo(cur, id_list, convo_map, convo_id, outgoing_name, process_attachments, attachment_path, base_output_dir):
    convo_name = slugify(demojize(convo_map[convo_id]))
    cur.execute("select json from messages where conversationId = ? order by sent_at asc", [convo_id])
    convo_objs = [json.loads(x["json"]) for x in cur.fetchall()]
    current_file = None
    current_month = None
    current_time = 0
    output_dir = Path(base_output_dir) / convo_name
    output_dir.mkdir(parents=True, exist_ok=True)
    for message in convo_objs:
        message_timestamp = int(message.get('received_at_ms', message['received_at'])) / 1000.0
        time_string = time.strftime('%Y_%m', time.localtime(message_timestamp))
        if time_string != current_month:
            if current_file:
                current_file.close()
            out_filename = output_dir / f"{convo_name}_{time_string}.txt"
            if out_filename.exists():
                try:
                    current_time = read_last_timestamp(out_filename)
                except ValueError:
                    # Only update our current time if we've successfully parsed the last time
                    print(f"WARNING: no timestamp found for pre-existing file {out_filename}")
                    pass
            current_file = out_filename.open("a")
            current_month = time_string

        # Adding one second here so we don't repeat the last line of the file when rerunning
        if message_timestamp < (current_time + 1.0):
            continue

        line = make_text_log(id_list, outgoing_name, message)
        if line:
            current_file.write(line + "\n")
        if process_attachments:
            copy_attachments(attachment_path, output_dir, message)
    if current_file:
        current_file.close()


def main(key, db_path, outgoing_name, process_attachments, attachment_path, output_dir):
    with open_db(key, db_path) as cur:
        cur.execute("select * from conversations;")
        raw_conversations = cur.fetchall()
        id_list = {x["e164"]: make_name(x) for x in raw_conversations if x["e164"] is not None}
        id_list.update({x["uuid"]: make_name(x) for x in raw_conversations if x.get("uuid", None)})
        convo_map = {x["id"]: make_name(x) for x in raw_conversations}
        for convo_id in convo_map.keys():
            process_convo(cur, id_list, convo_map, convo_id, outgoing_name, process_attachments, attachment_path, output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    key_methods = parser.add_mutually_exclusive_group()
    key_methods.add_argument('-j', '--json', default=CONFIG_PATH,
                             help="Location of Signal's config.json with the decryption key")
    key_methods.add_argument('-k', '--key', help="Decryption key for Signal Desktop database")
    parser.add_argument('-d', '--db-path', default=DB_PATH, help="Location of the encrypted Signal sqlite.db file")
    parser.add_argument('-i', '--i-am', default="me", help="Name to tag outgoing messages with")
    parser.add_argument('--extract-attachments', action="store_true", help="Extract attachments as well as text")
    parser.add_argument('--attachment-path', default=ATTACHMENT_PATH, help="Location of the attachments to extract")
    parser.add_argument('output_dir', help="Directory to output log files to")

    args = parser.parse_args()
    if args.key:
        resolved_key = args.key
    else:
        with open(args.json, 'r') as config:
            resolved_key = json.load(config).get("key")

    if not find_executable('sqlcipher'):
        parser.error("sqlcipher must be on your path for this script to function")

    if version.parse(sqlite3.sqlite_version) < version.parse('3.43.1'):
        howto_url = "https://shuaib.org/technical-guide/how-to-update-or-upgrade-sqlite3-version-in-python/"
        download_url = "https://www.sqlite.org/download.html"
        print("Signal uses a more recent version of sqlite than you have installed")
        print(f"To update your version, see {howto_url} for linux/macos,")
        print(f"or just download the windows .dll from {download_url} and replace sqlite.dll in the DLLs folder of your Python installation")
        parser.error("sqlite3 version is too old (<3.43.1)")

    main(resolved_key, args.db_path, args.i_am, args.extract_attachments, args.attachment_path, args.output_dir)
