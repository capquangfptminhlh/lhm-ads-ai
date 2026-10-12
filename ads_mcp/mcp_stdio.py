"""Minimal MCP stdio gateway. No external package needed; stdout only JSON-RPC.
Use with a compatible stdio MCP client. Remote MCP HTTP is NOT shipped here.
"""
import os
import sys
import json
import urllib.request
from urllib.error import HTTPError, URLError

TOOLS = [
 {'name':'list_accounts','description':'List advertising accounts available to your tenant, without secrets.',
  'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'get_insights','description':'Read account ad performance; demo data is explicitly tagged.',
  'inputSchema':{'type':'object','properties':{'account_id':{'type':'integer'},'period':{'type':'string','enum':['last_7d','yesterday']}},'required':['account_id'],'additionalProperties':False}},
 {'name':'request_pause_campaign','description':'REQUEST human review to pause a Meta campaign. This does NOT execute the pause. Requires operator key.',
  'inputSchema':{'type':'object','properties':{'account_id':{'type':'integer'},'campaign_id':{'type':'string'}},'required':['account_id','campaign_id'],'additionalProperties':False}},
 {'name':'list_actions','description':'Read submitted actions and their review status.',
  'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
]

def call_backend(name,arguments):
    base=os.environ.get('LHM_ADS_URL','http://127.0.0.1:8080').rstrip('/')
    key=os.environ.get('LHM_ADS_API_KEY','')
    if not key:
        raise ValueError('Thiếu LHM_ADS_API_KEY')
    body=json.dumps({'name':name,'arguments':arguments}).encode()
    req=urllib.request.Request(base+'/api/mcp/call',body,headers={
        'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    with urllib.request.urlopen(req,timeout=25) as response:
        return json.load(response)

def dispatch(msg):
    method=msg.get('method')
    if method=='initialize':
        requested=msg.get('params',{}).get('protocolVersion','2025-11-25')
        return {'protocolVersion':requested if requested in ('2024-11-05','2025-03-26','2025-06-18','2025-11-25') else '2025-11-25',
                'capabilities':{'tools':{'listChanged':False}},
                'serverInfo':{'name':'lhm-ads-ai-stdio','version':'0.1.0'}}
    if method=='ping':return {}
    if method=='tools/list':return {'tools':TOOLS}
    if method=='tools/call':
        p=msg.get('params') or {}
        name=p.get('name');args=p.get('arguments') or {}
        if name not in [tool['name'] for tool in TOOLS]:
            raise ValueError('Unknown MCP tool')
        try:
            data=call_backend(name,args)
            return {'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'isError':False}
        except (HTTPError,URLError,ValueError,TimeoutError) as exc:
            # Avoid returning access token/URL or raw HTTP body to AI client.
            detail='Không thực hiện được lệnh; kiểm tra API key, quyền và kết nối máy chủ'
            if isinstance(exc,ValueError):detail=str(exc)[:150]
            return {'content':[{'type':'text','text':detail}],'isError':True}
    raise ValueError('Method not supported')

def main():
    for line in sys.stdin:
        try:
            msg=json.loads(line)
            if 'id' not in msg:continue
            try:
                result=dispatch(msg)
                out={'jsonrpc':'2.0','id':msg['id'],'result':result}
            except (ValueError,TypeError) as e:
                out={'jsonrpc':'2.0','id':msg['id'],'error':{'code':-32601,'message':str(e)[:140]}}
        except (ValueError,TypeError):
            continue
        print(json.dumps(out,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
