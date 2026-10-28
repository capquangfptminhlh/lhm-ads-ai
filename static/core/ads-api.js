/* Browser-side Google Ads / Meta Marketing API client for the PWA.
 * Calls go straight from the customer's browser to Google/Meta (both allow CORS
 * from ads.lhmcrm.com); tokens never pass through LHM servers. Each function
 * mirrors the Windows app (ads_core/oauth_connect.py, providers.py,
 * optimizations.py, google_mutations.py) so both give the same answers.
 */
import {reportOutput,googleDailyRows,metaDailyRows,ReportError} from './reports.js';
import {GOOGLE_CAMPAIGN_QUERY,googleCampaigns,metaCampaigns,MAX_CAMPAIGNS} from './campaigns.js';

const GOOGLE_SCOPE='https://www.googleapis.com/auth/adwords';
const META_SCOPES='ads_read';
const STATE_KEY='lhm-oauth-state';
const DIGITS=/^\d{8,20}$/, ID=/^\d{5,30}$/;

export class ApiError extends Error{
 constructor(message,{status=502,code='API_ERROR'}={}){super(message);this.status=status;this.code=code;}
}

let config=null;
/** Public, non-secret client IDs and API versions served by the Worker. */
export async function adsConfig(){
 if(config)return config;
 const r=await fetch('/api/public/ads-config',{cache:'no-store',credentials:'same-origin'});
 if(!r.ok)throw new ApiError('Chưa cấu hình kết nối quảng cáo trên máy chủ.',{status:503,code:'NOT_CONFIGURED'});
 config=await r.json();
 if(!/^v\d+$/.test(config.google_ads_version||''))config.google_ads_version='v25';
 if(!/^v\d+\.\d+$/.test(config.meta_graph_version||''))config.meta_graph_version='v24.0';
 return config;
}

// ---------------------------------------------------------------- OAuth (redirect)
function randomState(platform){
 const bytes=crypto.getRandomValues(new Uint8Array(24));
 return platform+'.'+Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
}
/** Full-window redirect to Google or Meta consent. silent=true asks Google not to show UI. */
export async function startConnect(platform,{silent=false,loginHint=''}={}){
 const cfg=await adsConfig();
 const state=randomState(platform);
 // The state is a CSRF check only; it is not a credential.
 sessionStorage.setItem(STATE_KEY,state);
 const redirect=location.origin+'/local/oauth/'+platform;
 let url;
 if(platform==='google'){
   if(!cfg.google_client_id)throw new ApiError('Chưa cấu hình Google Ads cho PWA.',{status:503,code:'NOT_CONFIGURED'});
   url='https://accounts.google.com/o/oauth2/v2/auth?'+new URLSearchParams({client_id:cfg.google_client_id,
     redirect_uri:redirect,response_type:'token',scope:GOOGLE_SCOPE,include_granted_scopes:'true',state,
     ...(silent?{prompt:'none'}:{prompt:'select_account'}),...(loginHint?{login_hint:loginHint}:{})});
 }else if(platform==='meta'){
   if(!cfg.meta_app_id)throw new ApiError('Chưa cấu hình Meta Ads cho PWA.',{status:503,code:'NOT_CONFIGURED'});
   url='https://www.facebook.com/'+cfg.meta_graph_version+'/dialog/oauth?'+new URLSearchParams({
     client_id:cfg.meta_app_id,redirect_uri:redirect,response_type:'token',scope:cfg.meta_scopes||META_SCOPES,state});
 }else throw new ApiError('Nền tảng không hợp lệ.',{status:422});
 location.assign(url);
}
/** On /local/oauth/<platform>: read the token from the URL fragment, verify state,
 * and wipe it from the address bar immediately. Returns null on other pages. */
export function consumeOAuthReturn(){
 const m=location.pathname.match(/^\/local\/oauth\/(google|meta)\/?$/);
 if(!m)return null;
 const params=new URLSearchParams(location.hash.slice(1)||location.search.slice(1));
 history.replaceState(null,'','/local/');
 const expected=sessionStorage.getItem(STATE_KEY);
 sessionStorage.removeItem(STATE_KEY);
 const platform=m[1];
 if(!expected||params.get('state')!==expected||!expected.startsWith(platform+'.'))
   return {platform,error:'Phiên kết nối không hợp lệ hoặc đã hết hạn. Hãy thử lại.'};
 if(params.get('error'))return {platform,error:params.get('error'),errorDescription:params.get('error_description')||''};
 const token=params.get('access_token')||'';
 const expiresIn=Number(params.get('expires_in')||3600);
 if(!token||token.length>8192)return {platform,error:'Không nhận được quyền truy cập.'};
 return {platform,accessToken:token,expiresAt:Date.now()+Math.min(Math.max(expiresIn,60),86400*60)*1000};
}

// ---------------------------------------------------------------- HTTP helpers
async function call(url,{token,method='GET',headers={},body}={}){
 let r;
 try{
   r=await fetch(url,{method,headers:{Authorization:'Bearer '+token,
     ...(body!==undefined?{'Content-Type':'application/json'}:{}),...headers},
     body:body!==undefined?JSON.stringify(body):undefined,cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer'});
 }catch{throw new ApiError('Không kết nối được tới nền tảng quảng cáo. Kiểm tra Internet.',{status:0,code:'OFFLINE'});}
 const data=await r.json().catch(()=>null);
 if(r.status===401)throw new ApiError('Phiên kết nối đã hết hạn. Bấm "Kết nối lại".',{status:401,code:'TOKEN_EXPIRED'});
 return {status:r.status,ok:r.ok,data};
}
function googleHeaders(account){
 const h={};
 if(account.loginCustomerId){
   if(!DIGITS.test(account.loginCustomerId))throw new ApiError('Google manager ID không hợp lệ',{status:422});
   h['login-customer-id']=account.loginCustomerId;
 }
 return h;
}
const googleCustomer=account=>{
 const id=String(account.accountId).replace(/-/g,'');
 if(!DIGITS.test(id))throw new ApiError('Google customer ID không hợp lệ',{status:422});
 return id;
};
async function gaql(account,token,query){
 const cfg=await adsConfig();
 const r=await call(`https://googleads.googleapis.com/${cfg.google_ads_version}/customers/${googleCustomer(account)}/googleAds:searchStream`,
   {token,method:'POST',headers:googleHeaders(account),body:{query}});
 if(!r.ok)throw new ApiError('Không lấy được Google Ads: kiểm tra quyền API của Google Cloud và customer ID',{status:502});
 return r.data;
}

// ---------------------------------------------------------------- Google
/** oauth_connect.google_candidates */
export async function listGoogleAccounts(token){
 const cfg=await adsConfig();
 const v=cfg.google_ads_version;
 const r=await call(`https://googleads.googleapis.com/${v}/customers:listAccessibleCustomers`,{token});
 if(!r.ok||!Array.isArray(r.data?.resourceNames))throw new ApiError('Google Ads không trả danh sách tài khoản.',{status:502});
 const accounts=new Map();
 for(const name of r.data.resourceNames.slice(0,30)){
   if(typeof name!=='string'||!/^customers\/\d{8,20}$/.test(name))continue;
   const cid=name.split('/').pop();
   accounts.set(cid,{id:cid,label:'Google Ads '+cid,currency:'XXX',login_customer_id:''});
   try{
     const q=await call(`https://googleads.googleapis.com/${v}/customers/${cid}/googleAds:searchStream`,{token,method:'POST',
       body:{query:'SELECT customer_client.id, customer_client.descriptive_name, customer_client.currency_code, '+
         'customer_client.manager FROM customer_client WHERE customer_client.status = ENABLED LIMIT 200'}});
     if(q.status!==200||!Array.isArray(q.data))continue;
     for(const page of q.data){
       for(const item of page.results||[]){
         const c=item.customerClient||{};
         const child=String(c.id??'');
         if(!DIGITS.test(child))continue;
         const label=String(c.descriptiveName||'Google Ads '+child).slice(0,90);
         let cur=String(c.currencyCode||'XXX');cur=/^[A-Z]{3}$/.test(cur)?cur:'XXX';
         if(child===cid)Object.assign(accounts.get(child),{label,currency:cur});
         else if(!accounts.has(child))accounts.set(child,{id:child,label,currency:cur,login_customer_id:cid});
       }
     }
   }catch(e){if(e.code==='TOKEN_EXPIRED')throw e;/* Direct accounts still listed; never fabricate currency. */}
 }
 return [...accounts.values()].slice(0,200);
}
export async function googleReport(account,token,start,end){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(start)||!/^\d{4}-\d{2}-\d{2}$/.test(end))throw new ReportError('Ngày phải có định dạng YYYY-MM-DD');
 const query='SELECT segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks, '+
   'metrics.conversions, metrics.conversions_value '+
   `FROM customer WHERE segments.date BETWEEN '${start}' AND '${end}' ORDER BY segments.date ASC`;
 return reportOutput(googleDailyRows(await gaql(account,token,query)),account.currency,'google_live');
}
export async function googleCampaignScan(account,token){
 return googleCampaigns(await gaql(account,token,GOOGLE_CAMPAIGN_QUERY));
}
/** google_mutations.pause_google_campaign + a read-back of the new status. */
export async function googlePause(account,token,campaignId){
 if(!ID.test(campaignId))throw new ApiError('Chỉ hỗ trợ tạm dừng Google Campaign hợp lệ.',{status:422});
 const cfg=await adsConfig();
 const customer=googleCustomer(account);
 const path=`https://googleads.googleapis.com/${cfg.google_ads_version}/customers/${customer}`;
 const readStatus=async()=>{
   const pages=await gaql(account,token,`SELECT campaign.id,campaign.status FROM campaign WHERE campaign.id = ${campaignId} LIMIT 1`);
   const entries=pages.flatMap(p=>(p.results||[]).map(v=>v.campaign).filter(x=>x&&typeof x==='object'));
   if(entries.length!==1||String(entries[0].id)!==campaignId)throw new ApiError('Chiến dịch không thuộc tài khoản Google Ads đã chọn.',{status:404});
   return entries[0].status;
 };
 const status=await readStatus();
 if(status!=='ENABLED')throw new ApiError(`Chỉ tạm dừng khi chiến dịch đang ENABLED, hiện tại ${status}.`,{status:409});
 const operation={update:{resourceName:`customers/${customer}/campaigns/${campaignId}`,status:'PAUSED'},updateMask:'status'};
 const dry=await call(path+'/campaigns:mutate',{token,method:'POST',headers:googleHeaders(account),
   body:{operations:[operation],validateOnly:true,partialFailure:false}});
 if(dry.status!==200)throw new ApiError('Google Ads từ chối kiểm tra quyền chỉnh sửa (validateOnly).',{status:403});
 const live=await call(path+'/campaigns:mutate',{token,method:'POST',headers:googleHeaders(account),
   body:{operations:[operation],validateOnly:false,partialFailure:false}});
 if(!live.ok)throw new ApiError('Lỗi Google Ads khi cập nhật chiến dịch; không tự gửi lại lệnh.',{status:502});
 if(!live.data?.results||live.data.results[0]?.resourceName!==operation.update.resourceName)
   throw new ApiError('Google Ads trả về dữ liệu không hợp lệ; kiểm tra chiến dịch trước khi thử lại.',{status:502});
 // Post-mutation verification (docs/POST_MUTATION_VERIFICATION.md): read it back.
 let after='UNKNOWN';
 try{after=await readStatus();}catch{}
 return {success:true,provider_accepted:true,status_after:after,
   verification:after==='PAUSED'?'Đã đọc lại: chiến dịch đang PAUSED.':'API đã nhận lệnh; trạng thái có thể cập nhật chậm, hãy kiểm tra lại sau.'};
}

// ---------------------------------------------------------------- Meta
const metaBase=async()=>'https://graph.facebook.com/'+(await adsConfig()).meta_graph_version;
const metaAccountId=account=>{
 const id=String(account.accountId).replace(/^act_/,'');
 if(!/^\d{4,30}$/.test(id))throw new ApiError('ID tài khoản Meta không hợp lệ',{status:422});
 return id;
};
/** _meta_pages: bounded cursor pagination, never follows paging.next URLs. */
async function metaPages(url,token,params){
 const collected=[],seen=new Set(),args={...params};
 for(let i=0;i<6;i++){
   const r=await call(url+'?'+new URLSearchParams(args),{token});
   if(!r.ok||!r.data||!Array.isArray(r.data.data))throw new ApiError('Dữ liệu Meta không hợp lệ.',{status:502});
   collected.push(...r.data.data);
   if(collected.length>MAX_CAMPAIGNS)throw new ApiError('Meta có trên 500 dòng dữ liệu: quét chưa đầy đủ; không đưa ra kết luận.',{status:409});
   const paging=r.data.paging||{};
   if(!paging.next)return collected;
   const cursor=(paging.cursors||{}).after;
   if(typeof cursor!=='string'||cursor.length<1||cursor.length>1024||seen.has(cursor))
     throw new ApiError('Phân trang Meta không hợp lệ.',{status:502});
   seen.add(cursor);args.after=cursor;
 }
 throw new ApiError('Dữ liệu Meta phân trang vượt ngưỡng an toàn.',{status:409});
}
/** oauth_connect.meta_candidates */
export async function listMetaAccounts(token){
 const base=await metaBase();
 const results=[];let after=null;
 for(let i=0;i<5;i++){
   const params={fields:'id,name,currency,account_status',limit:'100',...(after?{after}:{})};
   const r=await call(base+'/me/adaccounts?'+new URLSearchParams(params),{token});
   if(!r.ok)throw new ApiError('Meta không trả danh sách tài khoản quảng cáo; kiểm tra quyền ads_read.',{status:502});
   for(const item of r.data?.data||[]){
     const acc=String(item.id??'').replace(/^act_/,'');
     if(!ID.test(acc))continue;
     const cur=String(item.currency||'XXX');
     results.push({id:'act_'+acc,label:String(item.name||'Meta Ads '+acc).slice(0,90),currency:/^[A-Z]{3}$/.test(cur)?cur:'XXX'});
   }
   after=(r.data?.paging?.cursors||{}).after;
   if(!after||results.length>=300)break;
 }
 return results.slice(0,300);
}
export async function metaReport(account,token,start,end){
 const base=await metaBase();
 const r=await call(`${base}/act_${metaAccountId(account)}/insights?`+new URLSearchParams({fields:'date_start,spend,impressions,clicks',
   time_range:JSON.stringify({since:start,until:end}),time_increment:'1',limit:'500'}),{token});
 if(!r.ok||!r.data||'error' in r.data)throw new ApiError('Không lấy được số liệu Meta: kiểm tra token, quyền ads_read và ID tài khoản',{status:502});
 return reportOutput(metaDailyRows(r.data),account.currency,'meta_live');
}
export async function metaCampaignScan(account,token,goal){
 const base=(await metaBase())+'/act_'+metaAccountId(account);
 const chosenAction=goal&&goal.enabled?goal.meta_action_type||null:null;
 const entries=await metaPages(base+'/campaigns',token,{fields:'id,name,status,effective_status,bid_strategy,daily_budget,lifetime_budget',limit:'100'});
 const params={level:'campaign',fields:'campaign_id,spend,clicks,impressions,frequency,reach',date_preset:'last_7d',limit:'100'};
 if(chosenAction){
   params.fields+=',actions,action_values,account_currency';
   params.action_attribution_windows='["7d_click"]';
   params.action_report_time='conversion';
 }
 const insights=await metaPages(base+'/insights',token,params);
 const adsets=await metaPages(base+'/adsets',token,{fields:'id,campaign_id,bid_strategy,bid_amount',limit:'100'});
 return metaCampaigns({entries,insights,adsets,chosenAction,currency:account.currency});
}
/** providers.pause_meta_campaign + read-back. */
export async function metaPause(account,token,campaignId){
 if(!ID.test(campaignId))throw new ApiError('ID chiến dịch không hợp lệ',{status:422});
 const base=await metaBase();
 const accId=metaAccountId(account);
 const check=await call(`${base}/${campaignId}?fields=id,account_id,status`,{token});
 if(!check.ok)throw new ApiError('Meta API từ chối thao tác: kiểm tra ads_management và quyền tài khoản',{status:502});
 if(String(check.data?.account_id||'').replace(/^act_/,'')!==accId)throw new ApiError('Chiến dịch không thuộc tài khoản đã chọn',{status:403});
 const r=await fetch(`${base}/${campaignId}`,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/x-www-form-urlencoded'},
   body:new URLSearchParams({status:'PAUSED'}),cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer'}).catch(()=>null);
 if(!r)throw new ApiError('Không kết nối được tới Meta.',{status:0,code:'OFFLINE'});
 if(r.status===401)throw new ApiError('Phiên kết nối đã hết hạn. Bấm "Kết nối lại".',{status:401,code:'TOKEN_EXPIRED'});
 const body=await r.json().catch(()=>null);
 if(!r.ok||body?.success!==true)throw new ApiError('Meta chưa xác nhận đã tạm dừng chiến dịch',{status:502});
 let after='UNKNOWN';
 try{const again=await call(`${base}/${campaignId}?fields=status`,{token});after=again.data?.status||'UNKNOWN';}catch{}
 return {success:true,provider_accepted:true,status_after:after,
   verification:after==='PAUSED'?'Đã đọc lại: chiến dịch đang PAUSED.':'Meta đã nhận lệnh; trạng thái có thể cập nhật chậm, hãy kiểm tra lại sau.'};
}
