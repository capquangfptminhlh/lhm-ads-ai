/* Offline MCP-compatible JSON-RPC dispatcher on CUSTOMER DEVICE ONLY.
 * No listener, no HTTP endpoint, no remote access, no token retrieval and no
 * write tools. External agents cannot connect until a separately authenticated,
 * encrypted and customer-approved relay exists.
 */
'use strict';
(() => {
  const vault=window.LHMDeviceVault;
  if(!vault)return;
  const METHODS=[
    {name:'lhm_accounts',description:'Read customer-local Ads account metadata; no credentials',
      inputSchema:{type:'object',properties:{},additionalProperties:false}},
    {name:'lhm_report',description:'Read manually imported, offline Ads metrics (not live API data)',
      inputSchema:{type:'object',properties:{
        period:{type:'string',enum:['today','yesterday','last_7d','last_30d']},
        localId:{type:'string'}},additionalProperties:false}},
    {name:'lhm_alerts',description:'Read local budget overruns based only on imported CSV',
      inputSchema:{type:'object',properties:{},additionalProperties:false}}
  ];
  function invalid(message,code=-32602){
    const error=new Error(message);error.rpcCode=code;throw error;
  }
  function localDay(offset=0){
    const d=new Date();d.setHours(12,0,0,0);
    d.setDate(d.getDate()+offset);
    const year=d.getFullYear(),month=String(d.getMonth()+1).padStart(2,'0'),
      day=String(d.getDate()).padStart(2,'0');
    return year+'-'+month+'-'+day;
  }
  function runTool(name,args){
    if(!vault.isUnlocked())invalid('Device vault is locked',-32001);
    if(!args||typeof args!=='object'||Array.isArray(args))invalid('Invalid arguments');
    const tool=METHODS.find(x=>x.name===name);
    if(!tool)invalid('Write actions and unknown tools are unavailable');
    if(Object.keys(args).some(key=>!(key in tool.inputSchema.properties)))
      invalid('Unknown tool arguments');
    if(name==='lhm_accounts'){
      return {storage:'customer_device_only',accounts:vault.listAccounts()
        .map(({localId,platform,accountId,label,currency})=>
          ({localId,platform,accountId,label,currency}))};
    }
    if(name==='lhm_alerts')return {
      source:'manual_csv',realtime:false,alerts:vault.listLocalAlerts()
    };
    const period=args.period||'last_7d';
    if(!['today','yesterday','last_7d','last_30d'].includes(period))
      invalid('Unsupported period');
    if(args.localId!=null&&typeof args.localId!=='string')
      invalid('Invalid account ID');
    const start=period==='today'?localDay(0):period==='yesterday'?localDay(-1):
      period==='last_7d'?localDay(-6):localDay(-29);
    const end=period==='yesterday'?localDay(-1):localDay(0);
    const rows=vault.listDailyReports(args.localId||undefined)
      .filter(x=>x.date>=start&&x.date<=end);
    return {period,start,end,source:'manual_csv',realtime:false,
      note:'Offline imported CSV; not verified by Google/Meta/TikTok Ads API.',
      reports:rows};
  }
  async function handle(message){
    const id=message&&Object.prototype.hasOwnProperty.call(message,'id')?message.id:null;
    const base={jsonrpc:'2.0',id};
    try{
      if(!message||message.jsonrpc!=='2.0'||typeof message.method!=='string')
        invalid('Invalid JSON-RPC request',-32600);
      if(id===null)return null;
      if(!vault.isUnlocked())invalid('Device vault is locked',-32001);
      let result;
      if(message.method==='initialize'){
        result={protocolVersion:'2025-06-18',
          capabilities:{tools:{listChanged:false}},
          serverInfo:{name:'lhm-ads-pwa-local',version:'0.1.0'}};
      }else if(message.method==='ping')result={};
      else if(message.method==='tools/list')result={tools:METHODS};
      else if(message.method==='tools/call'){
        const params=message.params;
        if(!params||typeof params.name!=='string')invalid('Tool name required');
        const output=runTool(params.name,params.arguments||{});
        result={content:[{type:'text',text:JSON.stringify(output)}],isError:false};
      }else invalid('Method not found',-32601);
      return {...base,result};
    }catch(err){
      return {...base,error:{code:err.rpcCode||-32603,
        message:err.rpcCode?-1===err.rpcCode?'Unknown':'Request not allowed':'Tool unavailable'}};
    }
  }
  Object.defineProperty(window,'LHMDeviceTools',{value:Object.freeze({
    handle,capabilities:()=>({transport:'in_page_only',remoteAccess:false,
      tools:METHODS.map(x=>x.name),writesAllowed:false})
  }),writable:false,configurable:false});
})();
