"""Bounded synchronous MCP stdio session; one owner per refresh, no shell."""
from __future__ import annotations
import json
import os
import selectors
import signal
import subprocess
import time
from .tushare_client import TushareRequestError


class StdioMcpTransport:
    def __init__(self, command: list[str], timeout: float = 45):
        self.timeout = timeout
        self.process = None
        self.selector = selectors.DefaultSelector()
        self.buffer = b''
        self.sequence = 0
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, start_new_session=True, bufsize=0)
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            result = self.request('initialize', {'protocolVersion':'2024-11-05', 'capabilities':{},
                'clientInfo':{'name':'dragonfuture','version':'0.1.0'}})
            if result.get('protocolVersion') not in {'2024-11-05','2025-03-26','2025-06-18','2025-11-25'}:
                raise ValueError('protocol')
            self._send({'jsonrpc':'2.0','method':'notifications/initialized'})
            inventory = self.request('tools/list', {})
            required = {'data_source_guide','tushare_call','futures_price_limits','trading_calendar'}
            if not required <= {t['name'] for t in inventory.get('tools', [])}:
                raise ValueError('capabilities')
            guide = self.call_tool('data_source_guide', {})
            if guide.get('isError'):
                raise ValueError('guide')
        except BaseException as exc:
            self.close()
            if isinstance(exc, (KeyboardInterrupt, SystemExit, TushareRequestError)):
                raise
            raise TushareRequestError('MCP_START_FAILED', 'MCP initialization failed') from None

    def _send(self, value):
        if self.process is None or self.process.poll() is not None:
            raise TushareRequestError('MCP_CLOSED', 'MCP session is closed')
        payload = (json.dumps(value, allow_nan=False)+'\n').encode()
        self.process.stdin.write(payload)
        self.process.stdin.flush()

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        deadline = time.monotonic()+self.timeout
        try:
            self._send({'jsonrpc':'2.0','id':request_id,'method':method,'params':params})
            while True:
                if time.monotonic() >= deadline:
                    try:
                        self._send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':request_id,'reason':'timeout'}})
                    finally:
                        raise TushareRequestError('MCP_TIMEOUT', 'MCP request timed out')
                if b'\n' not in self.buffer:
                    ready = self.selector.select(max(0, deadline-time.monotonic()))
                    if not ready:
                        continue
                    chunk = os.read(self.process.stdout.fileno(), 65536)
                    if not chunk:
                        raise TushareRequestError('MCP_CLOSED', 'MCP process ended')
                    self.buffer += chunk
                    if len(self.buffer) > 16*1024*1024:
                        raise TushareRequestError('MCP_RESPONSE_TOO_LARGE', 'MCP response exceeded limit')
                    continue
                line, self.buffer = self.buffer.split(b'\n',1)
                message = json.loads(line)
                if message.get('jsonrpc') != '2.0':
                    raise ValueError('protocol')
                if 'method' in message:
                    if 'id' in message:
                        self._send({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Unsupported client method'}})
                    continue
                if message.get('id') != request_id or 'error' in message or not isinstance(message.get('result'),dict):
                    raise ValueError('response')
                return message['result']
        except BaseException as exc:
            self.close()
            if isinstance(exc,(KeyboardInterrupt,SystemExit,TushareRequestError)):
                raise
            raise TushareRequestError('MCP_PROTOCOL_ERROR', 'Invalid MCP response') from None

    def call_tool(self, name, arguments):
        return self.request('tools/call', {'name':name,'arguments':arguments})

    def close(self):
        process, self.process = self.process, None
        self.selector.close()
        if process is not None:
            # The launcher may already have exited while descendants still own
            # its process group. Reap the leader and always terminate that group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            for stream in (process.stdin,process.stdout):
                if stream:
                    stream.close()
