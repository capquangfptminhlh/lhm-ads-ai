/* PWA live Ads features: connect Google/Meta in the browser, live reports,
 * campaign scan with the LHM playbook, and guarded pause. Data and tokens stay
 * in the on-device vault; nothing is sent to LHM servers. Same results as the
 * Windows app (static/core/* mirrors ads_core/*). Hard lock: every action needs
 * an active Gmail plan (window.LHMCustomer) and an unlocked vault.
 */
import {consumeOAuthReturn,startConnect,listGoogleAccounts,listMetaAccounts,googleReport,metaReport,
  googleCampaignScan,metaCampaignScan,googlePause,metaPause,adsConfig} from './ads-api.js';
import {resolveDateRange} from './reports.js';
import {evaluateCampaigns,computeBaselines} from './playbook.js';

const returned=consumeOAuthReturn();
let pending=returned&&!returned.error?returned:null;
let lastError=returned&&returned.error?returned:null;
const vault=()=>window.LHMDeviceVault;
const ready=()=>window.LHMCustomer?.state==='active'&&vault()?.isUnlocked();
const $=id=>document.getElementById(id);
const el=(tag,attrs={},...children)=>{
 const n=document.createElement(tag);
 for(const [k,v] of Object.entries(attrs)){
   if(k==='class')n.className=v;else if(k==='text')n.textContent=v;
   else if(k.startsWith('on'))n.addEventListener(k.slice(2),v);else if(v!==false&&v!==null&&v!==undefined)n.setAttribute(k,v===true?'':v);
 }
 n.append(...children.filter(c=>c!==null&&c!==undefined));
 return n;
};
const fmt=(v,cur)=>v===null||v===undefined?'—':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:cur?0:2}).format(v)+(cur?' '+cur:'');
const PLATFORM={google:'Google Ads',meta:'Meta Ads'};
const PERIODS=[['last_7d','7 ngày qua'],['yesterday','Hôm qua'],['today','Hôm nay'],['last_14d','14 ngày qua'],
 ['last_30d','30 ngày qua'],['this_month','Tháng này'],['last_month','Tháng trước']];

function guard(){
 if(window.LHMCustomer?.state!=='active')throw Error('Gói chưa hoạt động: phần mềm đang khoá.');
 if(!vault()?.isUnlocked())throw Error('Kho dữ liệu trên thiết bị đang khoá.');
}
function token(platform){
 guard();
 const c=vault().getConnection(platform);
 if(!c)throw Object.assign(Error('Chưa kết nối '+PLATFORM[platform]+'.'),{code:'NOT_CONNECTED',platform});
 if(c.expired)throw Object.assign(Error('Phiên '+PLATFORM[platform]+' đã hết hạn. Bấm "Kết nối lại".'),{code:'TOKEN_EXPIRED',platform});
 return c.accessToken;
}
async function withToken(platform,fn){
 try{return await fn(token(platform));}
 catch(e){
   if(e.code==='TOKEN_EXPIRED'){await vault().clearConnection(platform).catch(()=>{});renderConnections();}
   throw e;
 }
}
const apiAccounts=()=>vault().listAccounts().filter(a=>a.platform==='google'||a.platform==='meta');
function accountOptions(select,{keep=true}={}){
 const previous=select.value;
 select.replaceChildren(...apiAccounts().map(a=>el('option',{value:a.localId,text:PLATFORM[a.platform]+' · '+a.label+' ('+a.accountId+')'})));
 if(keep&&[...select.options].some(o=>o.value===previous))select.value=previous;
}
function status(node,text,error=false){node.textContent=text;node.classList.toggle('lhm-error',error);}

// ------------------------------------------------------------------ Connections
function connectionCard(){
 const card=el('article',{class:'pwa-card lhm-live',id:'lhm-api-connect'},
  el('h2',{text:'Kết nối API quảng cáo'}),
  el('p',{class:'pwa-muted',text:'Đăng nhập Google Ads / Meta ngay trong trình duyệt. Quyền truy cập chỉ lưu mã hoá trên thiết bị này và tự hết hạn sau khoảng 1–2 giờ.'}),
  el('div',{id:'lhm-connections'}),
  el('p',{id:'lhm-connect-status',role:'status',class:'pwa-muted'}),
  el('div',{id:'lhm-candidates'}));
 return card;
}
function renderConnections(){
 const box=$('lhm-connections');if(!box)return;
 box.replaceChildren();
 for(const platform of ['google','meta']){
   const c=ready()?vault().getConnection(platform):null;
   const state=c?(c.expired?'Phiên đã hết hạn':'Đã kết nối'+(c.email?' · '+c.email:'')+' · hết hạn '+new Date(c.expiresAt).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})):'Chưa kết nối';
   box.append(el('div',{class:'lhm-conn-row'},
     el('b',{text:PLATFORM[platform]}),el('span',{class:'pwa-muted',text:state}),
     el('button',{class:'pwa-btn'+(c&&!c.expired?'':' primary'),type:'button','data-connect':platform,
       text:c?(c.expired?'Kết nối lại':'Kết nối lại'):'Kết nối '+PLATFORM[platform],
       onclick:()=>startConnect(platform,{silent:Boolean(c)&&platform==='google'}).catch(e=>status($('lhm-connect-status'),e.message,true))}),
     c&&!c.expired?el('button',{class:'pwa-btn',type:'button','data-discover':platform,text:'Lấy danh sách tài khoản',
       onclick:()=>discover(platform)}):null));
 }
}
async function discover(platform){
 const out=$('lhm-candidates'),note=$('lhm-connect-status');
 status(note,'Đang lấy danh sách tài khoản '+PLATFORM[platform]+'…');
 try{
   const list=await withToken(platform,t=>platform==='google'?listGoogleAccounts(t):listMetaAccounts(t));
   const saved=new Set(vault().listAccounts().filter(a=>a.platform===platform).map(a=>a.accountId));
   out.replaceChildren(el('h3',{text:'Tài khoản '+PLATFORM[platform]+' bạn có quyền'}),
     list.length?el('ul',{class:'lhm-cand-list'},...list.map(a=>el('li',{},
       el('span',{text:a.label+' · '+a.id+' · '+a.currency+(a.login_customer_id?' · qua MCC '+a.login_customer_id:'')}),
       saved.has(a.id)?el('small',{text:'Đã lưu'}):el('button',{class:'pwa-btn',type:'button',text:'Thêm vào kho',
         disabled:a.currency==='XXX'?true:null,title:a.currency==='XXX'?'Không đọc được tiền tệ tài khoản':null,
         onclick:async ev=>{
           const button=ev.currentTarget; // currentTarget is null after the first await
           button.disabled=true;
           try{
             await vault().upsertAccount({platform,accountId:a.id,label:a.label,currency:a.currency,
               loginCustomerId:a.login_customer_id||'',source:'api'});
             button.replaceWith(el('small',{text:'Đã lưu'}));refreshSelectors();
             window.dispatchEvent(new Event('lhm:vault-changed'));
           }catch(e){status(note,e.message,true);button.disabled=false;}
         }}))))
     :el('p',{class:'pwa-muted',text:'Không tìm thấy tài khoản nào.'}));
   status(note,'');
 }catch(e){status(note,e.message,true);}
}

// ------------------------------------------------------------------ Live dashboard + reports
function periodSelect(id){return el('select',{id,class:'pwa-select','aria-label':'Khoảng thời gian'},...PERIODS.map(([v,t])=>el('option',{value:v,text:t})));}
function liveDashboardCard(){
 return el('article',{class:'pwa-card lhm-live',id:'lhm-live-dashboard'},
  el('div',{class:'pwa-chart-head'},el('h2',{text:'Số liệu trực tiếp từ API'}),periodSelect('lhm-dash-period'),
    el('button',{class:'pwa-btn primary',type:'button',id:'lhm-dash-load',text:'Tải số liệu',onclick:loadDashboard})),
  el('p',{id:'lhm-dash-status',class:'pwa-muted',role:'status',text:'Kết nối Google/Meta ở mục Tài khoản Ads rồi bấm Tải số liệu.'}),
  el('div',{class:'lhm-table-wrap'},el('table',{class:'lhm-table',id:'lhm-dash-table'})));
}
const KPI_HEAD=['Tài khoản','Chi tiêu','Hiển thị','Nhấp','CTR','CPC','Chuyển đổi','CPA','ROAS'];
const kpiRow=(name,r)=>[name,fmt(r.spend,r.currency),fmt(r.impressions),fmt(r.clicks),r.ctr+'%',fmt(r.cpc,r.currency),
 fmt(r.conversions),fmt(r.cpa,r.currency),r.roas===null?'—':String(r.roas)];
function table(node,head,rows){
 node.replaceChildren(el('thead',{},el('tr',{},...head.map(h=>el('th',{text:h})))),
   el('tbody',{},...rows.map(r=>el('tr',{},...r.map(c=>c instanceof Node?el('td',{},c):el('td',{text:String(c)}))))));
}
async function fetchReport(acc,period,from,to){
 const [start,end]=resolveDateRange(period,from,to);
 return withToken(acc.platform,t=>acc.platform==='google'?googleReport(acc,t,start,end):metaReport(acc,t,start,end));
}
async function loadDashboard(){
 const note=$('lhm-dash-status');
 try{
   guard();
   const accounts=apiAccounts();
   if(!accounts.length){status(note,'Chưa có tài khoản API nào trong kho.');return;}
   status(note,'Đang tải số liệu '+accounts.length+' tài khoản…');
   const rows=[],errors=[];
   for(const a of accounts){
     try{rows.push(kpiRow(a.label,await fetchReport(vault().accountRef(a.localId),$('lhm-dash-period').value)));}
     catch(e){errors.push(a.label+': '+e.message);}
   }
   table($('lhm-dash-table'),KPI_HEAD,rows);
   status(note,errors.length?'Một số tài khoản lỗi — '+errors.join(' · '):'Số liệu đọc trực tiếp từ API lúc '+new Date().toLocaleTimeString('vi-VN')+'. Ngày tính theo múi giờ của tài khoản quảng cáo.',Boolean(errors.length));
 }catch(e){status(note,e.message,true);}
}
function liveReportCard(){
 return el('article',{class:'pwa-card lhm-live',id:'lhm-live-report'},
  el('div',{class:'pwa-chart-head'},el('h2',{text:'Báo cáo API theo ngày'}),
    el('select',{id:'lhm-report-account',class:'pwa-select','aria-label':'Tài khoản'}),periodSelect('lhm-report-period'),
    el('button',{class:'pwa-btn primary',type:'button',text:'Xem',onclick:loadReport}),
    el('button',{class:'pwa-btn',type:'button',id:'lhm-report-csv',text:'Tải CSV',disabled:true,onclick:downloadCsv})),
  el('p',{id:'lhm-report-status',class:'pwa-muted',role:'status'}),
  el('div',{class:'lhm-table-wrap'},el('table',{class:'lhm-table',id:'lhm-report-table'})));
}
let lastReport=null;
async function loadReport(){
 const note=$('lhm-report-status');
 try{
   guard();
   const localId=$('lhm-report-account').value;
   if(!localId){status(note,'Chưa có tài khoản API nào.');return;}
   const acc=vault().accountRef(localId);
   status(note,'Đang tải…');
   const r=await fetchReport(acc,$('lhm-report-period').value);
   lastReport={acc,r};
   table($('lhm-report-table'),['Ngày','Chi tiêu','Hiển thị','Nhấp','Chuyển đổi','Giá trị'],
     r.daily.map(d=>[d.date,fmt(d.spend,r.currency),fmt(d.impressions),fmt(d.clicks),fmt(d.conversions??null),fmt(d.conversion_value??null,d.conversion_value!==undefined?r.currency:'')]));
   status(note,'Tổng: '+kpiRow(acc.label,r).slice(1).join(' · '));
   $('lhm-report-csv').disabled=false;
 }catch(e){status(note,e.message,true);}
}
function downloadCsv(){
 if(!lastReport)return;
 const {acc,r}=lastReport;
 const rows=[['date','spend','impressions','clicks','conversions','conversion_value','currency']]
   .concat(r.daily.map(d=>[d.date,d.spend,d.impressions,d.clicks,d.conversions??'',d.conversion_value??'',r.currency]));
 const blob=new Blob(['﻿'+rows.map(x=>x.join(',')).join('\n')],{type:'text/csv;charset=utf-8'});
 const a=el('a',{href:URL.createObjectURL(blob),download:'lhm-'+acc.platform+'-'+acc.accountId+'.csv'});
 document.body.append(a);a.click();a.remove();
}

// ------------------------------------------------------------------ Optimizer
function optimizerCard(){
 return el('article',{class:'pwa-card lhm-live',id:'lhm-optimizer'},
  el('h2',{text:'Trợ lý tối ưu (chạy trên thiết bị)'}),
  el('p',{class:'pwa-muted',text:'Cùng bộ quy tắc LHM với bản PC: quét chiến dịch 7 ngày, so với mục tiêu và với nền lịch sử của chính chiến dịch. Chỉ tư vấn; mọi thay đổi cần bạn xác nhận.'}),
  el('div',{class:'lhm-form-row'},el('select',{id:'lhm-opt-account',class:'pwa-select','aria-label':'Tài khoản',onchange:loadGoal}),
    el('button',{class:'pwa-btn primary',type:'button',text:'Quét chiến dịch',onclick:scan})),
  el('details',{class:'lhm-goal'},el('summary',{text:'Mục tiêu của tài khoản (tuỳ chọn)'}),
    el('form',{id:'lhm-goal-form',class:'lhm-form-row',onsubmit:saveGoal},
      el('label',{},'Bật ',el('input',{type:'checkbox',name:'enabled'})),
      el('select',{name:'objective','aria-label':'Chỉ tiêu'},el('option',{value:'cpa',text:'CPA tối đa'}),el('option',{value:'roas',text:'ROAS tối thiểu'})),
      el('input',{name:'target',type:'number',step:'any',min:'0',placeholder:'Mục tiêu','aria-label':'Mục tiêu'}),
      el('input',{name:'min_conversions',type:'number',min:'3',max:'1000',value:'5','aria-label':'Chuyển đổi tối thiểu'}),
      el('input',{name:'meta_action_type',placeholder:'Sự kiện Meta (vd purchase, lead)','aria-label':'Sự kiện Meta'}),
      el('button',{class:'pwa-btn',type:'submit',text:'Lưu mục tiêu'}))),
  el('p',{id:'lhm-opt-status',class:'pwa-muted',role:'status'}),
  el('div',{class:'lhm-table-wrap'},el('table',{class:'lhm-table',id:'lhm-opt-campaigns'})),
  el('div',{id:'lhm-findings'}),
  el('dialog',{id:'lhm-pause-dialog'},el('form',{method:'dialog',id:'lhm-pause-form'},
    el('h3',{text:'Tạm dừng chiến dịch'}),el('p',{id:'lhm-pause-text'}),
    el('label',{},el('input',{type:'checkbox',id:'lhm-pause-confirm',required:true}),' Tôi đã kiểm tra và muốn tạm dừng chiến dịch này'),
    el('div',{class:'lhm-form-row'},el('button',{class:'pwa-btn',value:'cancel',type:'submit',formnovalidate:true,text:'Huỷ'}),
      el('button',{class:'pwa-btn primary',value:'ok',type:'submit',text:'Tạm dừng'})))),
  el('h3',{text:'Nhật ký thao tác trên thiết bị'}),el('ul',{id:'lhm-audit',class:'lhm-audit'}));
}
function loadGoal(){
 const f=$('lhm-goal-form'),id=$('lhm-opt-account').value;
 if(!f||!id||!ready())return;
 const g=vault().getGoal(id)||{enabled:false,objective:'cpa',target:'',min_conversions:5,meta_action_type:''};
 f.enabled.checked=Boolean(g.enabled);f.objective.value=g.objective;f.target.value=g.target||'';
 f.min_conversions.value=g.min_conversions||5;f.meta_action_type.value=g.meta_action_type||'';
}
async function saveGoal(ev){
 ev.preventDefault();
 const f=ev.target,id=$('lhm-opt-account').value;
 try{
   guard();
   const acc=vault().accountRef(id);
   await vault().setGoal(id,{enabled:f.enabled.checked,objective:f.objective.value,target:Number(f.target.value),
     min_conversions:Number.parseInt(f.min_conversions.value,10),currency:acc.currency,
     meta_action_type:acc.platform==='meta'?f.meta_action_type.value.trim()||null:null});
   status($('lhm-opt-status'),'Đã lưu mục tiêu trên thiết bị.');
 }catch(e){status($('lhm-opt-status'),e.message,true);}
}
const LEVEL={critical:'Nghiêm trọng',review:'Cần xem',opportunity:'Cơ hội'};
async function scan(){
 const note=$('lhm-opt-status');
 try{
   guard();
   const id=$('lhm-opt-account').value;
   if(!id){status(note,'Chưa có tài khoản API nào.');return;}
   const acc=vault().accountRef(id),goal=vault().getGoal(id);
   status(note,'Đang quét chiến dịch 7 ngày…');
   const campaigns=await withToken(acc.platform,t=>acc.platform==='google'?googleCampaignScan(acc,t):metaCampaignScan(acc,t,goal));
   const baselines=computeBaselines(vault().listSnapshots(id));
   const findings=evaluateCampaigns(campaigns,acc.platform,acc.currency,goal,baselines);
   await vault().saveSnapshot(id,campaigns);
   renderCampaigns(acc,campaigns);renderFindings(campaigns,findings);
   status(note,campaigns.length+' chiến dịch · '+findings.length+' đề xuất · quét lúc '+new Date().toLocaleTimeString('vi-VN')+'.');
 }catch(e){status(note,e.message,true);}
}
function renderCampaigns(acc,campaigns){
 table($('lhm-opt-campaigns'),['Chiến dịch','Trạng thái','Chi tiêu','Nhấp','CTR','Chuyển đổi','CPA','ROAS',''],
   campaigns.map(c=>{
     const live=acc.platform==='google'?c.status==='ENABLED':(c.status==='ACTIVE'&&(c.effective_status===undefined||c.effective_status==='ACTIVE'));
     return [c.name,c.status,fmt(c.spend,acc.currency),fmt(c.clicks),c.ctr_percent===null?'—':c.ctr_percent+'%',
       fmt(c.conversions),fmt(c.cpa,acc.currency),c.roas===null?'—':String(c.roas),
       live?el('button',{class:'pwa-btn',type:'button',text:'Tạm dừng…',onclick:()=>confirmPause(acc,c)}):''];
   }));
}
function renderFindings(campaigns,findings){
 const names=new Map(campaigns.map(c=>[c.id,c.name]));
 $('lhm-findings').replaceChildren(el('h3',{text:'Đề xuất'}),
  findings.length?el('ol',{class:'lhm-findings'},...findings.map(f=>el('li',{class:'lhm-finding lhm-'+f.level},
    el('b',{text:'['+LEVEL[f.level]+'] '+f.playbook.title}),
    el('div',{class:'pwa-muted',text:(f.campaign_id==='ACCOUNT'?'Toàn tài khoản':names.get(f.campaign_id)||f.campaign_id)}),
    el('p',{text:f.message}),
    el('details',{},el('summary',{text:'Vì sao và nên làm gì'}),el('p',{text:f.playbook.why}),
      el('ul',{},...f.playbook.actions.map(a=>el('li',{text:a}))),
      el('p',{class:'pwa-muted',text:'Lưu ý: '+f.playbook.guardrails.join(' ')})),
    f.suppressed?el('small',{class:'pwa-muted',text:'Đã ẩn cơ hội mở rộng mâu thuẫn: '+f.suppressed.join(', ')}):null)))
  :el('p',{class:'pwa-muted',text:'Không có đề xuất nào cho kỳ này.'}));
}
function confirmPause(acc,c){
 const dialog=$('lhm-pause-dialog');
 $('lhm-pause-text').textContent='Tạm dừng "'+c.name+'" ('+c.id+') trên '+PLATFORM[acc.platform]+' · '+acc.label+
   '. Chi tiêu 7 ngày: '+fmt(c.spend,acc.currency)+'. Lệnh được gửi thẳng tới nền tảng sau khi kiểm tra quyền; LHM không tự gửi lại.';
 $('lhm-pause-confirm').checked=false;
 dialog.returnValue='';
 dialog.onclose=async()=>{
   if(dialog.returnValue!=='ok')return;
   const note=$('lhm-opt-status');
   try{
     guard();
     status(note,'Đang tạm dừng…');
     const r=await withToken(acc.platform,t=>acc.platform==='google'?googlePause(acc,t,c.id):metaPause(acc,t,c.id));
     await vault().appendAudit({action:'pause_campaign',localId:acc.localId,target:c.id,result:r.verification});
     status(note,r.verification);
   }catch(e){
     await vault().appendAudit({action:'pause_campaign_failed',localId:acc.localId,target:c.id,result:e.message}).catch(()=>{});
     status(note,e.message,true);
   }
   renderAudit();
 };
 dialog.showModal();
}
function renderAudit(){
 const list=$('lhm-audit');if(!list||!ready())return;
 list.replaceChildren(...vault().listAudit().slice(0,20).map(x=>el('li',{text:new Date(x.at).toLocaleString('vi-VN')+' · '+x.action+' · '+x.target+' · '+x.result})));
}

// ------------------------------------------------------------------ Mount
function refreshSelectors(){
 if(!ready())return;
 for(const id of ['lhm-report-account','lhm-opt-account']){const s=$(id);if(s)accountOptions(s);}
 loadGoal();
}
function mount(){
 const accounts=document.querySelector('.pwa-page[data-view="accounts"]');
 // Anchor on the static page heading: #login moves into the sign-in gate while locked.
 if(accounts&&!$('lhm-api-connect'))accounts.querySelector('.pwa-heading')?.after(connectionCard());
 const kpis=document.querySelector('.pwa-page[data-view="dashboard"] .pwa-kpis');
 if(kpis&&!$('lhm-live-dashboard'))kpis.after(liveDashboardCard());
 const reports=document.querySelector('.pwa-page[data-view="reports"]');
 if(reports&&!$('lhm-live-report'))reports.querySelector('.pwa-heading')?.after(liveReportCard());
 const assistant=document.querySelector('.pwa-page[data-view="assistant"]');
 if(assistant&&!$('lhm-optimizer'))assistant.querySelector('.pwa-heading')?.after(optimizerCard());
 for(const node of document.querySelectorAll('[data-live-hide]'))node.hidden=true;
}
async function onReady(){
 mount();
 if(pending&&ready()){
   const p=pending;pending=null;
   try{await vault().setConnection(p.platform,{accessToken:p.accessToken,expiresAt:p.expiresAt});
     status($('lhm-connect-status'),'Đã kết nối '+PLATFORM[p.platform]+'. Bấm "Lấy danh sách tài khoản".');
     window.dispatchEvent(new CustomEvent('lhm:go',{detail:'accounts'}));
   }catch(e){status($('lhm-connect-status'),e.message,true);}
 }
 if(lastError){
   status($('lhm-connect-status'),(lastError.error==='interaction_required'||lastError.error==='login_required'
     ?'Google cần bạn xác nhận lại: bấm "Kết nối lại".':'Kết nối '+(PLATFORM[lastError.platform]||'')+' chưa thành công: '+(lastError.errorDescription||lastError.error)),true);
   lastError=null;
 }
 renderConnections();refreshSelectors();renderAudit();
 adsConfig().then(cfg=>{
   if(!cfg.google_client_id&&!cfg.meta_app_id)status($('lhm-connect-status'),'Máy chủ chưa cấu hình kết nối Google/Meta cho PWA.',true);
 }).catch(()=>{});
}
window.addEventListener('lhm:customer-ready',()=>onReady());
window.addEventListener('lhm:vault-changed',refreshSelectors);
window.addEventListener('lhm:vault-locked',()=>{
 for(const id of ['lhm-dash-table','lhm-report-table','lhm-opt-campaigns','lhm-findings','lhm-candidates','lhm-audit']){
   const n=$(id);if(n)n.replaceChildren();
 }
 lastReport=null;renderConnections();
});
mount();
if(ready())onReady();
