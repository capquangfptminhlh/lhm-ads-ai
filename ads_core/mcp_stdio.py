"""Standards-compatible MCP JSON-RPC over local stdio (newline delimited).

Run: LHM_MCP_ACCESS_TOKEN=... python -m ads_core.mcp_stdio
No inbound HTTP listener. stdout is reserved for JSON-RPC responses.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from .db import init_db
from .mcp_bridge import resolve_mcp_identity, run_read_tool, TOOL_SCHEMAS

PROTOCOL='2025-06-18'

async def handle(request, token):
    if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':
        return {'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,
                'error':{'code':-32600,'message':'Invalid request'}}
    method=request.get('method')
    identifier=request.get('id')
    if identifier is None:
        return None  # JSON-RPC notifications have no response.
    try:
        # Check key on EVERY request (including tools/list) for fast revocation.
        ident=resolve_mcp_identity(token)
        if method=='initialize':
            result={'protocolVersion':PROTOCOL,
                'capabilities':{'tools':{'listChanged':False}},
                'serverInfo':{'name':'lhm-ads-ai-local','version':'1.0.0'}}
        elif method=='ping':
            result={}
        elif method=='tools/list':
            result={'tools':TOOL_SCHEMAS}
        elif method=='tools/call':
            params=request.get('params') or {}
            if not isinstance(params,dict) or not isinstance(params.get('name'),str):
                raise ValueError('Invalid tool name')
            data=await run_read_tool(params['name'],params.get('arguments',{}),ident)
            result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False,
                        separators=(',',':'))}], 'isError':False}
        else:
            return {'jsonrpc':'2.0','id':identifier,
                    'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':identifier,'result':result}
    except PermissionError:
        return {'jsonrpc':'2.0','id':identifier,
                'error':{'code':-32001,'message':'MCP authorization failed'}}
    except ValueError:
        return {'jsonrpc':'2.0','id':identifier,
                'error':{'code':-32602,'message':'Invalid tool arguments'}}
    except Exception:
        # Never write raw OAuth/Meta/Google API exceptions to MCP output.
        return {'jsonrpc':'2.0','id':identifier,
                'error':{'code':-32603,'message':'Tool execution failed'}}

def main():
    token=os.environ.get('LHM_MCP_ACCESS_TOKEN','')
    if not token:
        print('LHM_MCP_ACCESS_TOKEN is required',file=sys.stderr)
        raise SystemExit(2)
    init_db()
    for line in sys.stdin:
        if len(line)>65536:
            continue
        try:
            msg=json.loads(line)
            result=asyncio.run(handle(msg,token))
            if result is not None:
                sys.stdout.write(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
                sys.stdout.flush()
        except (json.JSONDecodeError,UnicodeError):
            continue

if __name__=='__main__':
    main()
