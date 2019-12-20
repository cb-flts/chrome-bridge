import socket
from uuid import uuid4
import json


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


class ChromeMessagingHandler(object):
    """
    Manages requests and responses to Chrome from CB-FLTS, through the
    FLTS-Chrome bridge.
    """
    def __init__(self, port=-1):
        self._port_number = port

    @property
    def port_number(self):
        """
        :return: Returns the TCP port number for communicating with the
        FLTS-Chrome bridge.
        :rtype: int
        """
        return self._port_number

    @port_number.setter
    def port_number(self, port):
        """
        Sets the port number to communicate with the FLTS-Chrome bridge.
        :param port: Port number.
        :type port: int
        """
        self._port_number = port

    def send_request(self, chrome_request):
        """
        Sends a request to Chrome for a given operation specified in the
        request. This message is sent through the FLTS-Chrome bridge.
        :param chrome_request: Request object containing the requested
        operation.
        :type chrome_request: ChromeRequest
        :return: Returns the response from Chrome through the FLTS-Chrome
        bridge.
        :rtype: ChromeResponse
        """
        if self._port_number == -1:
            raise ChromeMessageException(
                'Port number for communication with Chrome bridge not '
                'specified.'
            )
        chrome_resp = ChromeResponse()
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(('localhost', self._port_number))
            cr_json = chrome_request.to_json()
            client.sendall(cr_json)
            # Wait for response
            json_resp = client.recv(4096)
            chrome_resp.load_from_json(json_resp)
        except socket.error as se:
            raise ChromeMessageException(str(se))
        finally:
            client.close()

        return chrome_resp


def exit_bridge(msg_handler):
    cr = ChromeRequest()
    cr.message_type = ChromeRequest.EXIT
    cr.data = {}
    chrome_response = msg_handler.send_request(cr)
    print chrome_response.to_json()


def rename_tab(msg_handler):
    cr = ChromeRequest()
    cr.message_type = ChromeRequest.RENAME
    cr.data = {
        'current_name': 'WhatsApp',
        'new_name': 'We have updated the title!!'
    }
    chrome_response = msg_handler.send_request(cr)
    print chrome_response.to_json()

    # Attempt to close tab
    if chrome_response.is_successful():
        tab_id = chrome_response.data['tabId']
        cr_close = ChromeRequest()
        cr_close.message_type = ChromeRequest.EXIT
        cr_close.data = {
            'tabIds': [tab_id]
        }
        print cr_close.to_json()
        cr_resp_close = msg_handler.send_request(cr_close)
        print cr_resp_close.to_json()


def client_init():
    cmh = ChromeMessagingHandler(9413)
    # Request to exit the bridge
    exit_bridge(cmh)


if __name__ == '__main__':
    client_init()
