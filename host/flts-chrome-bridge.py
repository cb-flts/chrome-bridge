#!/usr/bin/env python
# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
An adaptation of Google Chrome's native messaging app. This bridge enables
the CB-FLTS to communicate with Google Chrome when used as a PDF viewer.
"""

import struct
import sys
import threading
from Queue import Queue
import socket
import os, msvcrt
from uuid import uuid4
import json
import logging
from ConfigParser import (
  ConfigParser,
  NoOptionError,
  NoSectionError
)


class BaseMessage(object):
    """
    Base class for CB-FLTS message requests and responses.
    """
    def __init__(self, **kwargs):
        prop_dict = kwargs.get('prop_dict', {})
        if len(prop_dict) > 0:
            self._load_prop_from_dict(prop_dict)

        # Name that uniquely identifies the app generating the message
        self.client_source = ''
        self.id = ''
        self.message_type = -1
        self.data = {}

    def _prop_mapping(self):
        # Contains property names for corresponding representation in JSON.
        return {
            'id': 'requestId',
            'client_source': 'source',
            'message_type': 'type',
            'data': 'data'
        }

    def to_json(self):
        """
        :return: Returns the object data in JSON format.
        :rtype: str
        """
        json_dict = {}
        for prop, pseudo in self._prop_mapping().iteritems():
            if hasattr(self, prop):
                json_dict[pseudo] = getattr(self, prop)

        return json.dumps(json_dict, separators=(',',':'))

    def load_from_json(self, json_obj):
        """
        Sets the object properties based on the given JSON object.
        :param json_obj: Object data in JSON format.
        :type json_obj: str
        """
        prop_vals = json.loads(json_obj)
        self._load_prop_from_dict(prop_vals)

    @staticmethod
    def source(json_obj):
        """
        Extracts the client source from the JSON object.
        :param json_obj: Object data in JSON format.
        :type json_obj: str
        :return: Return the client source from the message.
        :rtype: str
        """
        msg = BaseMessage()
        msg.load_from_json(json_obj)

        return msg.client_source

    def _load_prop_from_dict(self, prop_vals):
        for prop, pseudo in self._prop_mapping().iteritems():
            if pseudo in prop_vals:
                if hasattr(self, prop):
                    setattr(self, prop, prop_vals[pseudo])

    def __str__(self):
        return self.to_json()


class ChromeRequest(BaseMessage):
    """
    Contains information that will be sent to Chrome through the bridge.
    """
    # Message request types
    RENAME, CLOSE, EXIT = range(0, 3)

    def __init__(self, **kwargs):
        super(ChromeRequest, self).__init__(**kwargs)
        self.client_source = 'flts'
        self.id = str(uuid4())


class ChromeResponse(BaseMessage):
    """
    Contains information that will be sent back to the CB-FLTS through the
    bridge.
    """
    SUCCESS, ERROR, UNKNOWN = range(0, 3)

    def __init__(self, **kwargs):
        super(ChromeResponse, self).__init__(**kwargs)
        self.client_source = 'chrome'
        self.message_type = ChromeResponse.UNKNOWN

    def is_successful(self):
        """
        :return: Returns True if a response was successfully received else
        False. False might mean an error or the response type is unknown.
        """
        return self.message_type == ChromeResponse.SUCCESS


class ChromeMessageException(Exception):
    """
    For exceptions raised in sending requests and responses to Chrome.
    """
    pass


msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

# Setup a file logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('flts-chrome-bridge.log')
formatter = logging.Formatter('%(asctime)s : %(levelname)s : %(name)s : %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def port_number():
    """
    :return: Returns the port number specified in the configuration file or -1
    if there was an issue in reading the port number from the config.
    :rtype: int
    """
    port_num = -1
    try:
        cp = ConfigParser()
        cp.read('conf')
        port_num = int(cp.get('PORT', 'Number'))
    except NoSectionError:
        logger.exception('Config section error')
    except NoOptionError:
        logger.exception('Section option error')

    return port_num


# Helper function that sends a message to Chrome
def send_request_to_chrome(message):
    # Write message size.
    sys.stdout.write(struct.pack('I', len(message)))
    # Write the message itself.
    sys.stdout.write(message)
    sys.stdout.flush()


def read_thread_func(socket_queue, logger_obj):
    while 1:
        # Read the message length (first 4 bytes).
        text_length_bytes = sys.stdin.read(4)

        if len(text_length_bytes) == 0:
            if socket_queue:
                socket_queue.put(None)
            sys.exit(0)

        # Unpack message length as 4 byte integer.
        text_length = struct.unpack('i', text_length_bytes)[0]

        # Get message and create thread to send it back to FLTS
        response = sys.stdin.read(text_length).decode('utf-8')
        tc = threading.Thread(
          target=send_response_to_flts,
          args=(socket_queue, response)
        )
        tc.start()


def send_response_to_flts(socket_queue, response):
    while not socket_queue.empty():
        client = socket_queue.get()
        if not client:
            break

        if not response:
            client.close()
            sys.exit(0)
            break

        client.sendall(response)
        socket_queue.task_done()
        client.close()


def exit_response(ex_socket, request_id):
    # Mimics a response from Chrome on request to exit the bridge
    resp = ChromeResponse()
    resp.message_type = ChromeResponse.SUCCESS
    resp.data = {'msg': 'Bridge about to close'}
    resp.id = request_id
    ex_socket.sendall(resp.to_json())
    ex_socket.close()


def handle_client_connection(client_socket, socket_queue, ex_q):
    message = client_socket.recv(4096)
    msg_src = BaseMessage.source(message)
    if msg_src == 'flts':
        # Check if the request is for exiting
        req = ChromeRequest()
        req.load_from_json(message)
        if req.message_type == ChromeRequest.EXIT:
            # It is assumed that prior commands for CLOSE have already
            # been sent
            exit_response(client_socket, req.id)
            ex_q.put(None)
            sys.exit(0)

        send_request_to_chrome(message)
        # Insert socket into queue for use in sending back response
        socket_queue.put(client_socket)
    

def start_server(socket_queue, port, exit_q):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    continue_listen = True
    try:
        server.bind(('localhost', port))
        server.listen(5)
        while continue_listen:
            client_sock, address = server.accept()
            client_handler = threading.Thread(
                target=handle_client_connection,
                args=(client_sock, socket_queue, exit_q)
                )
            client_handler.start()
            client_handler.join()

            # Exit if exit queue contains a None item
            while not exit_q.empty():
                if not exit_q.get():
                    continue_listen = False
    except SystemExit:
        logger.exception('System exit')
    except socket.error:
        logger.exception('Server bind error')
    finally:
        server.close()


def start_bridge():
    socket_queue = Queue()
    exit_queue = Queue()

    # Get port number specified in the config
    port_num = port_number()
    if port_num == -1:
        sys.exit(1)

    stdin_thread = threading.Thread(
        target=read_thread_func,
        args=(socket_queue, logger)
    )
    stdin_thread.daemon = True
    stdin_thread.start()
    start_server(socket_queue, port_num, exit_queue)
    stdin_thread.join()
    sys.exit(0)


if __name__ == '__main__':
    start_bridge()
