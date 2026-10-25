/* Campaign-level 7-day data, normalized exactly like ads_core/optimizations.py
 * (google_campaigns / meta_campaigns). Network calls live in google-ads.js and
 * meta-ads.js; these functions only turn API JSON into campaign rows. */
import {pyRound,median} from './pyfmt.js';
import {ReportError} from './reports.js';

const ID=/^\d{5,30}$/;
export const MAX_CAMPAIGNS=500;
export const META_PURCHASE_ACTIONS=new Set(['purchase','offsite_conversion.fb_pixel_purchase','omni_purchase']);

export const GOOGLE_CAMPAIGN_QUERY="SELECT campaign.id, campaign.name, campaign.status, "+
 "campaign.bidding_strategy_type, campaign.target_cpa.target_cpa_micros, "+
 "campaign.maximize_conversions.target_cpa_micros, campaign.target_roas.target_roas, "+
 "campaign.maximize_conversion_value.target_roas, campaign_budget.amount_micros, campaign_budget.period, "+
 "metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, metrics.conversions_value, "+
 "metrics.search_budget_lost_impression_share FROM campaign WHERE campaign.status != REMOVED "+
 "AND segments.date DURING LAST_7_DAYS LIMIT 501";

const pyFloat=v=>{const n=Number(v);if(v===null||v===undefined||v===''||typeof v==='boolean'||Number.isNaN(n))throw TypeError('float');return n;};
const str100=(v,fallback)=>String(v||fallback).slice(0,100);

export function googleCampaigns(pages){
 if(!Array.isArray(pages))throw new ReportError('Không đọc được chiến dịch Google Ads; kiểm tra quyền API.',502);
 const found=[];
 for(const page of pages){
   for(const entry of page.results||[]){
     const item=entry.campaign||{};
     const cid=String(item.id??'');
     if(!ID.test(cid))continue;
     const m=entry.metrics||{};
     const spend=Math.trunc(Number(m.costMicros||0))/1000000;
     const conversions=Number(m.conversions||0);
     const value=Number(m.conversionsValue||0);
     const clicks=Math.trunc(Number(m.clicks||0));
     const impressions=Math.trunc(Number(m.impressions||0));
     let lost=null;
     try{lost=pyFloat(m.searchBudgetLostImpressionShare);}catch{lost=null;}
     const budget=entry.campaignBudget||{};
     const targetCpaMicros=(item.targetCpa||{}).targetCpaMicros||(item.maximizeConversions||{}).targetCpaMicros;
     const targetRoas=(item.targetRoas||{}).targetRoas||(item.maximizeConversionValue||{}).targetRoas;
     found.push({
       id:cid,name:str100(item.name,'Google Campaign'),status:String(item.status||'UNKNOWN'),
       spend:pyRound(spend,2),clicks,impressions,
       conversions:pyRound(conversions,2),conversion_value:pyRound(value,2),
       ctr_percent:impressions?pyRound(clicks*100/impressions,2):null,
       cpa:conversions>0?pyRound(spend/conversions,2):null,
       roas:spend>0?pyRound(value/spend,3):null,
       bidding_strategy:String(item.biddingStrategyType||'')||null,
       bid_target_cpa:targetCpaMicros?pyRound(Math.trunc(Number(targetCpaMicros))/1000000,2):null,
       bid_target_roas:targetRoas?Number(targetRoas):null,
       daily_budget:budget.amountMicros&&(budget.period==='DAILY'||budget.period===null||budget.period===undefined)
         ?pyRound(Math.trunc(Number(budget.amountMicros))/1000000,2):null,
       budget_lost_is:lost,
     });
     if(found.length>MAX_CAMPAIGNS)throw new ReportError('Quá 500 chiến dịch; không thể kiểm tra đầy đủ và tạo cảnh báo an toàn.',409);
   }
 }
 return found;
}

export function metaActionNumber(rows,actionType){
 if(!Array.isArray(rows))return null;
 const matches=rows.filter(r=>r&&typeof r==='object'&&!Array.isArray(r)&&r.action_type===actionType);
 if(matches.length!==1)return null;
 const raw='7d_click' in matches[0]?matches[0]['7d_click']:matches[0].value;
 if(raw===null||raw===undefined||typeof raw==='boolean')return null;
 const value=Number(raw);
 return Number.isFinite(value)&&value>=0&&String(raw).trim()!==''?value:null;
}
export function metaFrequency(raw){
 if(raw===null||raw===undefined||raw===''||typeof raw==='boolean')return null;
 const value=Number(raw);
 return Number.isFinite(value)&&value>0?value:null;
}
export function metaReach(raw){
 if(raw===null||raw===undefined||raw===''||typeof raw==='boolean')return null;
 const value=pyIntOrNull(raw);
 return value!==null&&value>0?value:null;
}
export function metaBidAmount(raw){
 if(raw===null||raw===undefined||typeof raw==='boolean')return null;
 const value=Number(raw)/100;
 return Number.isFinite(value)&&value>=0&&String(raw).trim()!==''?value:null;
}
// Python int(raw): integer strings only; JSON numbers are truncated.
const pyIntOrNull=raw=>{
 if(typeof raw==='number')return Number.isFinite(raw)?Math.trunc(raw):null;
 const s=String(raw).trim();
 return /^[+-]?\d+$/.test(s)?Number(s):null;
};
const metaMoney=raw=>{
 if(raw===null||raw===undefined||raw==='')return null;
 const n=pyIntOrNull(raw);
 return n===null?null:pyRound(n/100,2);
};

/** meta_campaigns: campaigns + 7d campaign insights + ad sets (already paginated). */
export function metaCampaigns({entries,insights,adsets,chosenAction=null,currency}){
 const found=[],known=new Set();
 for(const entry of entries){
   if(!entry||typeof entry!=='object'||Array.isArray(entry))throw new ReportError('Không đọc đủ chiến dịch Meta; kiểm tra phân trang và quyền API.',502);
   const cid=String(entry.id??'');
   if(!ID.test(cid))continue;
   if(known.has(cid))throw new ReportError('Không đọc đủ chiến dịch Meta; kiểm tra phân trang và quyền API.',502);
   known.add(cid);
   found.push({id:cid,name:str100(entry.name,'Meta Campaign'),status:String(entry.status||'UNKNOWN'),
     effective_status:String(entry.effective_status||'UNKNOWN'),
     spend:null,clicks:null,impressions:null,conversions:null,conversion_value:null,
     ctr_percent:null,cpa:null,roas:null,frequency:null,reach:null,
     bidding_strategy:String(entry.bid_strategy||'')||null,bid_target_cpa:null,bid_target_roas:null,
     adset_bid_target_cpa:null,daily_budget:metaMoney(entry.daily_budget),lifetime_budget:metaMoney(entry.lifetime_budget)});
 }
 const insightError='Không thể đọc đầy đủ Meta Insights; không tạo cảnh báo dựa trên dữ liệu thiếu.';
 const values={};
 for(const item of insights){
   if(!item||typeof item!=='object'||Array.isArray(item))throw new ReportError(insightError,502);
   const id=String(item.campaign_id??'');
   if(!ID.test(id)||id in values)throw new ReportError(insightError,502);
   values[id]=item;
 }
 for(const c of found){
   const row=values[c.id];
   if(!row)continue;
   let spend,clicks,impressions;
   try{
     spend=pyFloat(row.spend);
     clicks=pyIntOrNull(row.clicks??'');impressions=pyIntOrNull(row.impressions??'');
     if(clicks===null||impressions===null)throw TypeError();
   }catch{throw new ReportError(insightError,502);}
   if(!Number.isFinite(spend)||spend<0||clicks<0||impressions<0)continue;
   c.spend=pyRound(spend,2);c.clicks=clicks;c.impressions=impressions;
   c.ctr_percent=impressions?pyRound(100*clicks/impressions,2):null;
   c.frequency=metaFrequency(row.frequency);
   c.reach=metaReach(row.reach);
   if(chosenAction&&row.account_currency===currency){
     const count=metaActionNumber(row.actions,chosenAction);
     if(count===null)continue;
     c.conversions=pyRound(count,2);
     c.conversion_action_type=chosenAction;
     c.conversion_source='meta_actions_7d_click';
     c.cpa=count>0?pyRound(spend/count,2):null;
     if(META_PURCHASE_ACTIONS.has(chosenAction)){
       const value=metaActionNumber(row.action_values,chosenAction);
       if(value!==null){c.conversion_value=pyRound(value,2);c.roas=spend>0?pyRound(value/spend,3):null;}
     }
   }
 }
 const bids={};
 for(const row of adsets){
   if(!row||typeof row!=='object'||Array.isArray(row))
     throw new ReportError('Không đọc đủ nhóm quảng cáo Meta; không tạo cảnh báo dựa trên dữ liệu thiếu.',502);
   const id=String(row.campaign_id??'');
   if(!ID.test(id))continue;
   const amount=metaBidAmount(row.bid_amount);
   if(amount!==null)(bids[id]||(bids[id]=[])).push(amount);
 }
 for(const c of found){
   const amounts=bids[c.id];
   if(amounts&&amounts.length&&c.bid_target_cpa===null)c.adset_bid_target_cpa=pyRound(median(amounts),2);
 }
 return found;
}
