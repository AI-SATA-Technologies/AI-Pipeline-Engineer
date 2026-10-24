"""ASGI middleware that caps the size of a whole request body.

Rejects with 413 when Content-Length is over the limit, and also counts the
bytes actually streamed (chunked uploads have no Content-Length), so a client
can't fill the disk/RAM with an oversized multipart upload.
"""
import json

from starlette.exceptions import HTTPException


class _BodyTooLarge(HTTPException):
    """Raised from receive() mid-stream. An HTTPException, so FastAPI's body
    parser re-raises it (instead of turning it into a generic 400) and the app's
    exception handler answers 413."""

    def __init__(self, max_bytes: int):
        super().__init__(status_code=413, detail=f'Request body exceeds {max_bytes}-byte limit')


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        for name, value in scope.get('headers', []):
            if name == b'content-length':
                try:
                    declared = int(value)
                except ValueError:
                    await self._reject(send, 400, 'Invalid Content-Length')
                    return
                if declared > self.max_bytes:
                    await self._reject(send, 413, self._message())
                    return
                break

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > self.max_bytes:
                    raise _BodyTooLarge(self.max_bytes)
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message['type'] == 'http.response.start':
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            # Only reached if nothing inside the app handled it.
            if not response_started:
                await self._reject(send, 413, self._message())

    def _message(self) -> str:
        return f'Request body exceeds {self.max_bytes}-byte limit'

    @staticmethod
    async def _reject(send, status: int, detail: str) -> None:
        body = json.dumps({'detail': detail}).encode()
        await send({
            'type': 'http.response.start',
            'status': status,
            'headers': [(b'content-type', b'application/json'),
                        (b'content-length', str(len(body)).encode())],
        })
        await send({'type': 'http.response.body', 'body': body})
