import json
import sys
import pytest
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_transport import StdioMcpTransport
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError

SERVER = '''
import sys,json,time
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 m=r['method']
 if m=='initialize':v={'protocolVersion':'2024-11-05'}
 elif m=='tools/list':v={'tools':[{'name':x} for x in ['data_source_guide','tushare_call','futures_price_limits','trading_calendar']]}
 elif r['params']['name']=='hang':time.sleep(30);continue
 else:v={'content':[{'type':'text','text':'{}'}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':v}),flush=True)
'''

def test_stdio_handshake_and_clean_close(tmp_path):
    p=tmp_path/'server.py';p.write_text(SERVER)
    t=StdioMcpTransport([sys.executable,str(p)],timeout=1)
    process=t.process
    assert t.call_tool('example',{})['content']
    t.close();t.close()
    assert process.poll() is not None

def test_timeout_kills_process_and_sanitizes(tmp_path):
    p=tmp_path/'server.py';p.write_text(SERVER)
    t=StdioMcpTransport([sys.executable,str(p)],timeout=.1);process=t.process
    with pytest.raises(TushareRequestError,match='MCP_TIMEOUT'):
        t.call_tool('hang',{})
    assert process.poll() is not None

def test_start_failure_is_sanitized():
    with pytest.raises(TushareRequestError) as e:StdioMcpTransport(['/not-existing/secret-command'])
    assert 'secret-command' not in str(e.value)

def test_close_kills_remaining_process_group(monkeypatch):
    import signal
    from unittest.mock import Mock
    import dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_transport as module
    calls=[];monkeypatch.setattr(module.os,'killpg',lambda pid,sig:calls.append((pid,sig)))
    t=object.__new__(StdioMcpTransport);t.selector=Mock();t.process=Mock()
    t.process.pid=123;t.process.poll.return_value=0
    t.close()
    assert (123,signal.SIGTERM) in calls
    assert (123,signal.SIGKILL) in calls
