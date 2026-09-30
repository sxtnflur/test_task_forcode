

class HttpClientError(Exception):
    message: str = "HTTP Client Error"

    def __init__(self, message: str | None = None, *args):
        if message:
            self.message += f': {message}'

        super().__init__(message, *args)


class InvalidResponseError(HttpClientError):
    message = 'Invalid Response'


class ClientRequestError(HttpClientError):
    message = 'Error during request'


class ClientTimeoutError(ClientRequestError):
    message = 'Timeout error'


class ClientRequestFailed(ClientRequestError):
    message = 'HTTP Client Request Failed'


class ClientInvalidResponseError(HttpClientError):
    message = 'HTTP Client received invalid response'
