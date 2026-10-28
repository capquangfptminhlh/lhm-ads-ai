/* LHM Vòng lặp Tối ưu — JS port of ads_core/optimization_playbook.py.
 * The Python module is the reference: thresholds, wording, conflict guard and
 * outcome verification must match it byte for byte (tests/fixtures/core).
 * Pure data in/out: no network, no storage. Advice only, never edits Ads.
 */
import {pyFixed,pyGrouped,pyRound,pyG,pySum,median} from './pyfmt.js';

export const NO_CONVERSION_MIN_CLICKS=50, CPA_REVIEW_RATIO=1.2, CPA_CRITICAL_RATIO=1.5, CPA_MIN_CONVERSIONS=5,
 SCALE_CPA_RATIO=0.8, SCALE_MIN_CONVERSIONS=10, ROAS_CRITICAL_RATIO=0.7, ROAS_SCALE_RATIO=1.3,
 LOW_CTR_MAX_PERCENT=0.5, LOW_CTR_MIN_CLICKS=100, LOW_CTR_MIN_IMPRESSIONS=1000, HEALTHY_CTR_MIN_PERCENT=1.0,
 HIGH_CTR_NO_CONV_MIN_CLICKS=100, SMART_BIDDING_MIN_CONVERSIONS_7D=15, MAX_STEP_PERCENT=20,
 DRIFT_CPA_REVIEW_RATIO=1.25, DRIFT_CPA_CRITICAL_RATIO=1.5, DRIFT_ROAS_REVIEW_RATIO=0.8, DRIFT_ROAS_CRITICAL_RATIO=0.65,
 ACCOUNT_FRAGMENT_MIN_CAMPAIGNS=4, ACCOUNT_FRAGMENT_MAX_CONVERSIONS=SMART_BIDDING_MIN_CONVERSIONS_7D,
 ACCOUNT_INEFFICIENT_SPEND_SHARE=0.40, PLATFORM_TARGET_REVIEW_RATIO=1.3, PLATFORM_TARGET_CRITICAL_RATIO=1.6,
 PLATFORM_HEADROOM_CPA_RATIO=0.8, PLATFORM_HEADROOM_ROAS_RATIO=1.25, MANUAL_BIDDING_MIN_CONVERSIONS=30,
 GOOGLE_MANUAL_STRATEGIES=['MANUAL_CPC','MANUAL_CPM','MANUAL_CPV'], BUDGET_LOST_IS_MIN=0.20,
 ADSET_TARGET_REVIEW_RATIO=PLATFORM_TARGET_REVIEW_RATIO, ADSET_TARGET_CRITICAL_RATIO=PLATFORM_TARGET_CRITICAL_RATIO,
 FATIGUE_FREQUENCY_REVIEW=4.0, FATIGUE_FREQUENCY_HIGH=6.0, FATIGUE_CTR_MAX_PERCENT=1.0, FATIGUE_MIN_IMPRESSIONS=1000,
 ACCOUNT_INEFFICIENT_CPA_RATIO=CPA_CRITICAL_RATIO, OUTCOME_NOISE_BAND=0.05, OUTCOME_MIN_CONVERSIONS=5, MAX_FINDINGS=100;

export const ACTIVE_STATUSES=['ENABLED','ACTIVE'];
export const APPROVAL_NOTE='Mọi thay đổi phải do người phụ trách duyệt trong trình quản lý quảng cáo; '+
 'hệ thống chỉ tư vấn, không tự sửa quảng cáo và không hứa kết quả.';
export const SCALE_CODES=['cpa_well_below_target_scale','roas_above_target_scale','platform_target_headroom','budget_constrained_winner'];
export const CUT_CODES=['cpa_above_target','roas_below_target','cpa_drift_vs_baseline','roas_drift_vs_baseline',
 'spend_no_conversions','high_ctr_no_conversions','platform_target_missed','adset_target_missed'];

// --- Python-compatible helpers ------------------------------------------------
const PY_FLOAT=/^\s*[+-]?((\d+(_\d+)*)?\.?\d+(_\d+)*([eE][+-]?\d+)?|\d+(_\d+)*\.([eE][+-]?\d+)?|inf(inity)?|nan)\s*$/i;
/** _num: finite, non-negative float or null; missing data is never 0. */
export function num(value){
 if(value===null||value===undefined||typeof value==='boolean')return null;
 let v;
 if(typeof value==='number')v=value;
 else if(typeof value==='string'&&PY_FLOAT.test(value))v=Number(value.replace(/_/g,'').replace(/inf(inity)?/i,'Infinity'));
 else return null;
 return Number.isFinite(v)&&v>=0?v:null;
}
const isDict=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const dictList=v=>Array.isArray(v)?v.filter(isDict):[];
export function money(value,currency){
 value=num(value);
 if(value===null)return '—';
 if((currency||'').toUpperCase()==='VND')return pyGrouped(value,0).replace(/,/g,'.')+' VND';
 return (pyGrouped(value,2)+' '+(currency||'')).trim();
}
const ratio=v=>{v=num(v);return v===null?'—':pyFixed(v,2);};
function pctDelta(actual,reference){
 if(!reference)return 0;
 const delta=(actual/reference-1)*100;
 if(!Number.isFinite(delta))return delta>0?1e15:-100;
 return pyRound(delta);
}
const int=v=>Math.trunc(v);
const get=(o,k)=>o[k]===undefined?null:o[k];
function isActive(c,platform){
 if(!ACTIVE_STATUSES.includes(get(c,'status')))return false;
 if(platform==='meta'){const e=get(c,'effective_status');if(e!==null&&e!=='ACTIVE')return false;}
 return true;
}
function goalTargets(goal,currency){
 const out={cpa_target:null,roas_target:null,min_conversions:CPA_MIN_CONVERSIONS};
 if(!isDict(goal)||!goal.enabled)return out;
 if(goal.currency&&currency&&goal.currency!==currency)return out;
 const target=num(goal.target);
 if(target===null||target<=0)return out;
 if(goal.objective==='cpa')out.cpa_target=target;
 else if(goal.objective==='roas')out.roas_target=target;
 const minConv=goal.min_conversions;
 if(Number.isInteger(minConv)&&minConv>0)out.min_conversions=Math.max(CPA_MIN_CONVERSIONS,minConv);
 return out;
}
function finding(campaignId,entry,level,message,why,actions,guardrails){
 return {campaign_id:String(campaignId),level,code:entry.code,category:entry.category,message,
   playbook:{title:entry.title,why,actions:[...actions],guardrails:[...guardrails,APPROVAL_NOTE]}};
}

// --- Conditions ------------------------------------------------------------------
function spendNoConversions(c,t,ctx){
 const clicks=num(get(c,'clicks')),conversions=num(get(c,'conversions')),spend=num(get(c,'spend'));
 if(clicks===null||conversions===null||spend===null)return null;
 if(clicks<NO_CONVERSION_MIN_CLICKS||conversions!==0||spend<=0)return null;
 const platformName=ctx.platform==='google'?'Google Ads':'Meta Ads';
 return {level:'review',
  message:`Đã chi ${money(spend,ctx.currency)} với ${int(clicks)} lượt nhấp trong 7 ngày `+
   `nhưng chưa ghi nhận chuyển đổi nào. Kiểm tra tracking trước khi kết luận lãng phí.`,
  why:'0 chuyển đổi trên dữ liệu thật thường do một trong ba nguyên nhân: đo lường hỏng/thiếu, '+
   'độ trễ ghi nhận chuyển đổi, hoặc lưu lượng không tạo chuyển đổi. Cắt ngân sách khi chưa '+
   'kiểm chứng tracking sẽ phá dữ liệu học của nền tảng.',
  actions:['Kiểm tra sự kiện chuyển đổi có bắn đúng: Google Tag/Tag Assistant (Google) hoặc Events Manager + Test Events, gồm cả CAPI nếu có (Meta).',
   'Đối chiếu số đơn/lead thực tế trong CRM hoặc kênh bán hàng với số chuyển đổi nền tảng báo, tính cả độ trễ quy đổi (attribution lag).',
   'Kiểm tra trang đích: tải được, form/thanh toán hoạt động, không lỗi trên di động.',
   'Chỉ sau khi tracking được xác nhận đúng mới đánh giá lại chất lượng lưu lượng của chiến dịch này.'],
  guardrails:['Không tự tắt/dừng chiến dịch vì cảnh báo này.',
   `Đây là tín hiệu cấp ${platformName}: kiểm chứng trên đúng nền tảng đang chạy.`]};
}
function cpaAboveTarget(c,t,ctx){
 const target=t.cpa_target;
 const cpa=num(get(c,'cpa')),conversions=num(get(c,'conversions')),spend=num(get(c,'spend'));
 if(target===null||cpa===null||conversions===null)return null;
 if(conversions<t.min_conversions||cpa<=target*CPA_REVIEW_RATIO)return null;
 const level=cpa>target*CPA_CRITICAL_RATIO?'critical':'review';
 const over=pctDelta(cpa,target);
 return {level,
  message:`CPA thực tế ${money(cpa,ctx.currency)} cao hơn mục tiêu ${money(target,ctx.currency)} `+
   `khoảng ${over}% (dựa trên ${int(conversions)} chuyển đổi, chi ${money(spend,ctx.currency)} trong 7 ngày). `+
   `Xem xét giảm giá thầu/ngân sách theo từng bước nhỏ.`,
  why:'CPA vượt mục tiêu có đủ lượng chuyển đổi làm bằng chứng cho thấy đấu thầu đang mua chuyển đổi '+
   'đắt hơn mức tổ chức chấp nhận. Nhưng CPA cũng bị nhiễu bởi độ trễ chuyển đổi và pha học, '+
   'nên phải chỉnh từng bước nhỏ thay vì cắt mạnh.',
  actions:['Kiểm chứng nhanh tracking và độ trễ chuyển đổi (cảnh báo tracking phải được loại trừ trước).',
   `Nếu CPA cao kéo dài qua nhiều kỳ: hạ mục tiêu tCPA hoặc giá thầu tối đa từng bước tối đa ${MAX_STEP_PERCENT}%, chờ ít nhất 7 ngày sau mỗi bước.`,
   'Chuyển dần ngân sách sang các chiến dịch đang đạt mục tiêu CPA trong cùng tài khoản.',
   'Rà soát chất lượng lưu lượng theo checklist: truy vấn tìm kiếm/từ khóa (Google), đối tượng và vị trí (Meta) — công cụ này không nhìn thấy các lớp dữ liệu đó.'],
  guardrails:[`Không chỉnh quá ${MAX_STEP_PERCENT}% trong một lần; không đổi đồng thời giá thầu và ngân sách.`,
   'Tôn trọng pha học: sau mỗi lần chỉnh, nền tảng cần thời gian học lại trước khi đánh giá tiếp.']};
}
function cpaWellBelowTargetScale(c,t,ctx){
 const target=t.cpa_target;
 const cpa=num(get(c,'cpa')),conversions=num(get(c,'conversions'));
 if(target===null||cpa===null||conversions===null)return null;
 if(conversions<SCALE_MIN_CONVERSIONS||cpa>=target*SCALE_CPA_RATIO)return null;
 const under=Math.abs(pctDelta(cpa,target));
 return {level:'opportunity',
  message:`CPA thực tế ${money(cpa,ctx.currency)} thấp hơn mục tiêu ${money(target,ctx.currency)} `+
   `khoảng ${under}% với ${int(conversions)} chuyển đổi trong 7 ngày: có dư địa mở rộng để mua thêm chuyển đổi.`,
  why:'Khi CPA ổn định dưới mục tiêu với lượng chuyển đổi đủ lớn, mục tiêu/ngân sách hiện tại có thể '+
   'đang kìm lưu lượng rẻ. Nới dần từng bước giúp mua thêm chuyển đổi trong khi CPA còn trong tầm kiểm soát.',
  actions:[`Tăng ngân sách ngày HOẶC nới mục tiêu tCPA từng bước tối đa ${MAX_STEP_PERCENT}% — chỉ chọn một biến mỗi lần.`,
   'Theo dõi CPA 3–7 ngày sau mỗi bước; dừng mở rộng khi CPA tiệm cận mục tiêu.',
   'Ưu tiên mở rộng ở khung giờ/nhóm quảng cáo đang có CPA tốt nhất thay vì tăng đều toàn chiến dịch.'],
  guardrails:['Cơ hội không phải cam kết: CPA có thể tăng khi mở rộng lưu lượng.',
   'Cơ hội này tự động bị ẩn khi chiến dịch có cảnh báo cắt/giảm (conflict guard) — xử lý cảnh báo đó trước.']};
}
function roasBelowTarget(c,t,ctx){
 const target=t.roas_target;
 const roas=num(get(c,'roas')),value=num(get(c,'conversion_value')),conversions=num(get(c,'conversions'));
 if(target===null||roas===null||value===null||conversions===null)return null;
 if(conversions<t.min_conversions||roas>=target)return null;
 const level=roas<target*ROAS_CRITICAL_RATIO?'critical':'review';
 return {level,
  message:`ROAS thực tế ${ratio(roas)} thấp hơn mục tiêu ${ratio(target)} `+
   `(doanh thu ghi nhận ${money(value,ctx.currency)}, ${int(conversions)} chuyển đổi trong 7 ngày). `+
   `Kiểm tra ghi nhận doanh thu và xem xét giảm tốc chi tiêu theo từng bước.`,
  why:'ROAS dưới mục tiêu với doanh thu đã được ghi nhận cho thấy đấu thầu theo giá trị đang mua doanh thu '+
   'kém hiệu quả hơn mức chấp nhận. Cần loại trừ lỗi ghi nhận doanh thu/độ trễ trước khi chỉnh, '+
   'vì thiếu doanh thu ghi nhận sẽ làm ROAS trông tệ giả tạo.',
  actions:['Đối chiếu doanh thu nền tảng báo với doanh thu thực (đơn hoàn/hủy, độ trễ thanh toán, cửa sổ quy đổi).',
   `Nếu ROAS thấp là thật và kéo dài: giảm ngân sách chiến dịch này từng bước tối đa ${MAX_STEP_PERCENT}% hoặc tăng mục tiêu tROAS một bước nhỏ.`,
   'Chuyển dần ngân sách sang chiến dịch có ROAS đạt mục tiêu.',
   'Rà soát nhóm sản phẩm/dịch vụ giá trị thấp đang ăn ngân sách (checklist — công cụ không thấy dữ liệu cấp sản phẩm).'],
  guardrails:[`Không chỉnh quá ${MAX_STEP_PERCENT}% trong một lần; chờ qua pha học rồi mới đánh giá bước tiếp.`,
   'Không kết luận từ ROAS khi doanh thu chưa được ghi nhận đầy đủ.']};
}
function roasAboveTargetScale(c,t,ctx){
 const target=t.roas_target;
 const roas=num(get(c,'roas')),value=num(get(c,'conversion_value')),conversions=num(get(c,'conversions')),spend=num(get(c,'spend'));
 if(target===null||roas===null||value===null||conversions===null||spend===null)return null;
 if(conversions<SCALE_MIN_CONVERSIONS||spend<=0||roas<=target*ROAS_SCALE_RATIO)return null;
 return {level:'opportunity',
  message:`ROAS thực tế ${ratio(roas)} vượt mục tiêu ${ratio(target)} với ${int(conversions)} chuyển đổi `+
   `và chi ${money(spend,ctx.currency)} trong 7 ngày: có dư địa tăng ngân sách để mở rộng doanh thu.`,
  why:'ROAS cao bền vững trên lượng chuyển đổi đủ lớn cho thấy chiến dịch còn "đói" ngân sách: '+
   'tăng dần giúp mua thêm doanh thu trước khi hiệu quả bị pha loãng.',
  actions:[`Tăng ngân sách ngày từng bước tối đa ${MAX_STEP_PERCENT}%, theo dõi ROAS sau 3–7 ngày mỗi bước.`,
   'Hoặc nới mục tiêu tROAS một bước nhỏ (tối đa 10–20%) để hệ thống dám chi rộng hơn — chỉ chọn một biến.',
   'Dừng mở rộng khi ROAS tiệm cận mục tiêu.'],
  guardrails:['ROAS thường giảm khi mở rộng; đó là đánh đổi có chủ đích, không phải lỗi.',
   'Cơ hội này tự động bị ẩn khi chiến dịch có cảnh báo cắt/giảm (conflict guard) — xử lý cảnh báo đó trước.']};
}
function lowCtr(c,t,ctx){
 const clicks=num(get(c,'clicks')),impressions=num(get(c,'impressions')),ctr=num(get(c,'ctr_percent'));
 if(clicks===null||impressions===null||ctr===null)return null;
 if(clicks<LOW_CTR_MIN_CLICKS||impressions<LOW_CTR_MIN_IMPRESSIONS||ctr>=LOW_CTR_MAX_PERCENT)return null;
 return {level:'review',
  message:`CTR ${ratio(ctr)}% dưới 0,5% với ${int(clicks)} lượt nhấp / ${int(impressions)} lượt hiển thị: `+
   `kiểm tra mức độ liên quan của nội dung và đối tượng; không tự tắt quảng cáo.`,
  why:'CTR thấp trên mẫu đủ lớn thường nghĩa là quảng cáo chưa khớp ý định người xem hoặc đối tượng quá rộng/sai. '+
   'CTR thấp cũng kéo chất lượng quảng cáo và giá mỗi nhấp đi xuống theo thời gian.',
  actions:['So thông điệp quảng cáo với nội dung trang đích: hứa gì ở quảng cáo phải thấy ngay ở trang đích.',
   'Rà soát creative: thử biến thể tiêu đề/hình ảnh mới thay vì sửa nhỏ giọt trên mẫu cũ (checklist — công cụ không thấy cấp quảng cáo).',
   'Kiểm tra độ khớp đối tượng/từ khóa với ý định mua hàng; loại trừ vị trí hiển thị kém liên quan nếu có dữ liệu.'],
  guardrails:['Không tắt quảng cáo chỉ vì CTR: CTR thấp nhưng chuyển đổi tốt vẫn có thể có lãi.']};
}
function highCtrNoConversions(c,t,ctx){
 const clicks=num(get(c,'clicks')),ctr=num(get(c,'ctr_percent')),conversions=num(get(c,'conversions'));
 if(clicks===null||ctr===null||conversions===null)return null;
 if(ctr<HEALTHY_CTR_MIN_PERCENT||clicks<HIGH_CTR_NO_CONV_MIN_CLICKS||conversions!==0)return null;
 return {level:'review',
  message:`CTR khỏe ${ratio(ctr)}% với ${int(clicks)} lượt nhấp nhưng 0 chuyển đổi: quảng cáo thu hút được nhấp `+
   `mà trang đích/tracking không chuyển thành kết quả — kiểm tra độ khớp thông điệp và đo lường.`,
  why:'Nhấp nhiều chứng tỏ quảng cáo hứa hẹn hấp dẫn; 0 chuyển đổi ở cuối phễu thường do trang đích không '+
   'giữ đúng lời hứa, trải nghiệm sau nhấp kém, hoặc sự kiện chuyển đổi không ghi nhận. Đây là tín hiệu '+
   'lệch phễu, khác với quảng cáo yếu.',
  actions:['Kiểm chứng sự kiện chuyển đổi bắn đúng sau hành động thật (đặt đơn/gửi form thử nghiệm).',
   'Đọc lại trang đích bằng mắt người mua: thông điệp, giá, bằng chứng tin cậy và nút hành động có khớp quảng cáo không.',
   'Kiểm tra tốc độ tải và lỗi form/thanh toán trên di động.'],
  guardrails:['Không tăng ngân sách cho chiến dịch này trước khi rõ nguyên nhân ở cuối phễu.']};
}
function lowConversionVolume(c,t,ctx){
 const conversions=num(get(c,'conversions')),spend=num(get(c,'spend'));
 if(conversions===null||spend===null)return null;
 if(!(conversions>0&&conversions<SMART_BIDDING_MIN_CONVERSIONS_7D)||spend<=0)return null;
 let learning,actions;
 if(ctx.platform==='google'){
   learning='Google Smart Bidding (tCPA/tROAS) cần lượng chuyển đổi ổn định để học; '+
    'dưới ~15 chuyển đổi/7 ngày, pha học kéo dài và CPA dao động mạnh.';
   actions=['Gộp các chiến dịch/nhóm quảng cáo cùng mục tiêu bị phân mảnh để dồn lượng chuyển đổi về một chỗ học.',
    'Đánh giá theo cửa sổ 14–30 ngày thay vì phản ứng theo từng tuần.',
    'Cân nhắc nới mục tiêu tCPA/tROAS tạm thời để hệ thống có thêm tín hiệu, chỉnh lại khi lượng tăng.'];
 }else{
   learning='Meta cần đủ chuyển đổi mỗi nhóm quảng cáo để thoát giai đoạn học (Learning/Learning Limited); '+
    'dưới ~15 chuyển đổi/7 ngày, phân phối thiếu ổn định và CPA dao động mạnh.';
   actions=['Gộp các nhóm quảng cáo (ad set) cùng mục tiêu bị phân mảnh để dồn lượng chuyển đổi.',
    'Đánh giá theo cửa sổ 14–30 ngày thay vì phản ứng theo từng tuần.',
    'Cân nhắc dùng sự kiện chuyển đổi gần hơn (micro-conversion) làm tín hiệu tối ưu nếu sự kiện chính quá thưa — chỉ khi sự kiện đó có ý nghĩa kinh doanh thật.'];
 }
 return {level:'review',
  message:`Chỉ ${pyG(conversions)} chuyển đổi trong 7 ngày (chi ${money(spend,ctx.currency)}): lượng quá thấp `+
   `để đấu thầu thông minh học ổn định. Ưu tiên gộp và dồn tín hiệu thay vì chỉnh giá thầu liên tục.`,
  why:learning,actions,
  guardrails:['Tránh chỉnh giá thầu/ngân sách liên tục khi đang thiếu dữ liệu — mỗi lần chỉnh đều khởi động lại pha học.']};
}
function deadCampaign(c,t,ctx){
 const spend=num(get(c,'spend')),impressions=num(get(c,'impressions'));
 if(spend===null||impressions===null)return null;
 if(spend!==0||impressions!==0)return null;
 return {level:'review',
  message:'Chiến dịch đang bật nhưng 7 ngày qua không chi tiêu và không có lượt hiển thị nào: '+
   'nhiều khả năng là sự cố phân phối, cần kiểm tra theo danh sách trước khi kết luận.',
  why:'Một chiến dịch đang bật mà im lặng hoàn toàn thường do ngân sách/lịch/giá thầu/đối tượng chặn phân phối, '+
   'hoặc quảng cáo bị từ chối — không phải do hiệu quả kém.',
  actions:['Kiểm tra ngân sách ngày và ngân sách dùng chung có bị chiến dịch khác ăn hết không.',
   'Kiểm tra giá thầu có thấp hơn sàn đấu giá, đối tượng có quá hẹp hoặc chồng chéo tự cạnh tranh không.',
   'Kiểm tra lịch chạy, vị trí địa lý, ngày bắt đầu/kết thúc chiến dịch.',
   'Kiểm tra trạng thái duyệt quảng cáo trong trình quản lý (công cụ này không nhìn thấy lý do từ chối).'],
  guardrails:['Chỉ bật lại phân phối sau khi rõ nguyên nhân; tránh tăng giá thầu mù để "ép chạy".']};
}
const periodsText=b=>'periods' in b?(b.periods===null?'None':String(b.periods)):'?';
function cpaDriftVsBaseline(c,t,ctx){
 const baseline=(ctx.baselines||{})[String(get(c,'id'))];
 if(!isDict(baseline))return null;
 const medianCpa=num(get(baseline,'median_cpa')),cpa=num(get(c,'cpa'));
 const conversions=num(get(c,'conversions'));
 if(medianCpa===null||medianCpa<=0||cpa===null||conversions===null)return null;
 if(conversions<CPA_MIN_CONVERSIONS||cpa<=medianCpa*DRIFT_CPA_REVIEW_RATIO)return null;
 const level=cpa>medianCpa*DRIFT_CPA_CRITICAL_RATIO?'critical':'review';
 const drift=pctDelta(cpa,medianCpa);
 const band=num(get(baseline,'cpa_volatility'));
 const bandText=band!==null?` (biên dao động lịch sử ±${pyRound(band*100)}%)`:'';
 return {level,
  message:`CPA kỳ này ${money(cpa,ctx.currency)} lệch +${drift}% so với CPA trung vị của chính chiến dịch `+
   `(${money(medianCpa,ctx.currency)} qua ${periodsText(baseline)} kỳ)${bandText}: hiệu quả đang xấu đi `+
   `so với nền của chính nó, kể cả khi chưa chạm ngưỡng mục tiêu.`,
  why:'So với nền lịch sử của chính chiến dịch bắt được suy giảm sớm hơn so với mục tiêu chung: một chiến dịch '+
   'quen chạy CPA thấp bỗng đắt lên thường do cạnh tranh tăng, creative mệt, hoặc thay đổi ở trang đích.',
  actions:['Xác định thời điểm CPA bắt đầu lệch và đối chiếu thay đổi đã làm (creative, đối tượng, trang đích, ngân sách).',
   'Kiểm chứng tracking vẫn ghi nhận đúng (loại trừ nguyên nhân đo lường trước).',
   `Nếu lệch là thật: giảm tốc theo từng bước tối đa ${MAX_STEP_PERCENT}% và theo dõi CPA quay về vùng nền.`],
  guardrails:['Nền dựa trên dữ liệu quá khứ của chính tài khoản này; kỳ nền quá ít (dưới 3 kỳ) thì chỉ nên tham khảo.']};
}
function roasDriftVsBaseline(c,t,ctx){
 const baseline=(ctx.baselines||{})[String(get(c,'id'))];
 if(!isDict(baseline))return null;
 const medianRoas=num(get(baseline,'median_roas')),roas=num(get(c,'roas'));
 const conversions=num(get(c,'conversions'));
 if(medianRoas===null||medianRoas<=0||roas===null||conversions===null)return null;
 if(conversions<CPA_MIN_CONVERSIONS||roas>=medianRoas*DRIFT_ROAS_REVIEW_RATIO)return null;
 const level=roas<medianRoas*DRIFT_ROAS_CRITICAL_RATIO?'critical':'review';
 const drift=Math.abs(pctDelta(roas,medianRoas));
 return {level,
  message:`ROAS kỳ này ${ratio(roas)} tụt ${drift}% so với ROAS trung vị của chính chiến dịch `+
   `(${ratio(medianRoas)} qua ${periodsText(baseline)} kỳ): hiệu quả đang xấu đi so với nền của chính nó.`,
  why:'ROAS tụt so với nền của chính chiến dịch thường báo hiệu creative mệt, cạnh tranh tăng, hoặc thay đổi '+
   'ghi nhận doanh thu — cần tìm nguyên nhân trước khi chỉnh ngân sách.',
  actions:['Đối chiếu doanh thu ghi nhận với doanh thu thực để loại trừ lỗi đo lường.',
   'Xác định thời điểm ROAS bắt đầu tụt và các thay đổi đã làm quanh thời điểm đó.',
   `Nếu tụt là thật: giảm tốc chi tiêu từng bước tối đa ${MAX_STEP_PERCENT}% ở phần kém hiệu quả nhất.`],
  guardrails:['Nền dựa trên dữ liệu quá khứ của chính tài khoản này; kỳ nền quá ít (dưới 3 kỳ) thì chỉ nên tham khảo.']};
}
function platformTargetMissed(c,t,ctx){
 const conversions=num(get(c,'conversions'));
 if(conversions===null||conversions<CPA_MIN_CONVERSIONS)return null;
 const targetCpa=num(get(c,'bid_target_cpa')),cpa=num(get(c,'cpa'));
 if(targetCpa&&cpa&&cpa>targetCpa*PLATFORM_TARGET_REVIEW_RATIO){
   const level=cpa>targetCpa*PLATFORM_TARGET_CRITICAL_RATIO?'critical':'review';
   const over=pctDelta(cpa,targetCpa);
   const actions=['Đối chiếu target trên nền tảng với CPA thực tế 30 ngày: nếu target thấp hơn nhiều so với thực tế bền vững, nới target từng bước tối đa 20% về gần thực tế thay vì để hệ thống "đuổi" một con số không tưởng.',
    'Kiểm chứng tracking và độ trễ chuyển đổi trước khi kết luận (loại trừ cảnh báo tracking nếu đang mở).',
    'Dồn ngân sách về các chiến dịch đang bám sát target trong cùng tài khoản trong lúc hiệu chỉnh.'];
   if(ctx.platform==='google')actions.push('Lưu ý thay đổi Google từ 17/8/2026: chiến dịch tCPA/tROAS bị giới hạn ngân sách được đặt giá hướng về đúng target — kiểm tra cả trạng thái giới hạn ngân sách trước khi chỉnh target.');
   return {level,
    message:`CPA thực tế ${money(cpa,ctx.currency)} cao hơn target tCPA ${money(targetCpa,ctx.currency)} `+
     `đang đặt trên nền tảng khoảng ${over}% (dựa trên ${int(conversions)} chuyển đổi trong 7 ngày).`,
    why:'Target trên nền tảng là con số hệ thống đấu thầu dùng trực tiếp. Khi CPA thực tế cao hơn target '+
     'kéo dài, hoặc target đang phi thực tế, hoặc lưu lượng đang đắt hơn mức hệ thống được phép mua — '+
     'cả hai đều cần hiệu chỉnh theo bước nhỏ, không cắt mạnh.',
    actions,
    guardrails:[`Không chỉnh target quá ${MAX_STEP_PERCENT}% trong một lần; chờ ít nhất 7 ngày sau mỗi bước.`,
     'Không kết luận từ một kỳ duy nhất nếu chiến dịch vừa đổi cấu trúc/ngân sách (pha học).']};
 }
 const targetRoas=num(get(c,'bid_target_roas')),roas=num(get(c,'roas'));
 if(targetRoas&&roas!==null&&roas<targetRoas/PLATFORM_TARGET_REVIEW_RATIO){
   const level=roas<targetRoas/PLATFORM_TARGET_CRITICAL_RATIO?'critical':'review';
   const under=Math.abs(pctDelta(roas,targetRoas));
   return {level,
    message:`ROAS thực tế ${ratio(roas)} thấp hơn target tROAS ${ratio(targetRoas)} `+
     `đang đặt trên nền tảng khoảng ${under}% (dựa trên ${int(conversions)} chuyển đổi trong 7 ngày).`,
    why:'Đấu thầu theo giá trị chỉ đúng khi doanh thu ghi nhận đầy đủ. ROAS dưới target kéo dài thường do '+
     'một trong ba: giá trị chuyển đổi ghi thiếu/sai, target cao hơn thực tế thị trường, hoặc lưu lượng '+
     'kém chất lượng — phải loại trừ ghi nhận doanh thu trước.',
    actions:['Kiểm chứng ghi nhận doanh thu: giá trị đơn hàng thật, trừ hoàn/hủy, không trùng lặp sự kiện.',
     'Nếu ghi nhận đúng mà ROAS vẫn dưới target qua nhiều kỳ: hạ target tROAS từng bước tối đa 20% về gần thực tế, hoặc dồn ngân sách sang chiến dịch đạt target.',
     'Rà soát phân bổ theo sản phẩm/nhóm quảng cáo trong trình quản lý quảng cáo (lớp dữ liệu công cụ này không nhìn thấy).'],
    guardrails:[`Không chỉnh target quá ${MAX_STEP_PERCENT}% trong một lần; chờ ít nhất 7 ngày sau mỗi bước.`,
     'Không hạ target chỉ vì một kỳ xấu khi lượng chuyển đổi còn ít.']};
 }
 return null;
}
function platformTargetHeadroom(c,t,ctx){
 const conversions=num(get(c,'conversions'));
 if(conversions===null||conversions<SCALE_MIN_CONVERSIONS)return null;
 const targetCpa=num(get(c,'bid_target_cpa')),cpa=num(get(c,'cpa'));
 if(targetCpa&&cpa&&cpa<targetCpa*PLATFORM_HEADROOM_CPA_RATIO){
   const under=Math.abs(pctDelta(cpa,targetCpa));
   return {level:'opportunity',
    message:`CPA thực tế ${money(cpa,ctx.currency)} thấp hơn target tCPA ${money(targetCpa,ctx.currency)} `+
     `khoảng ${under}% với ${int(conversions)} chuyển đổi trong 7 ngày: có dư địa mua thêm chuyển đổi.`,
    why:'Hiệu quả đang tốt hơn target nền tảng với lượng chuyển đổi đủ tin cậy. Nới dần target hoặc '+
     'ngân sách theo bước nhỏ giúp mua thêm chuyển đổi trong khi CPA còn dư địa an toàn.',
    actions:[`Tăng ngân sách ngày HOẶC nới target từng bước tối đa ${MAX_STEP_PERCENT}% — chỉ một biến mỗi lần.`,
     'Theo dõi CPA 3–7 ngày sau mỗi bước; dừng khi CPA tiệm cận target.'],
    guardrails:['Cơ hội không phải cam kết: mở rộng lưu lượng thường làm CPA tăng dần.',
     'Bị chặn tự động nếu chiến dịch đang có cảnh báo cắt/giảm (conflict guard).']};
 }
 const targetRoas=num(get(c,'bid_target_roas')),roas=num(get(c,'roas'));
 if(targetRoas&&roas!==null&&roas>targetRoas*PLATFORM_HEADROOM_ROAS_RATIO){
   const over=pctDelta(roas,targetRoas);
   return {level:'opportunity',
    message:`ROAS thực tế ${ratio(roas)} cao hơn target tROAS ${ratio(targetRoas)} `+
     `khoảng ${over}% với ${int(conversions)} chuyển đổi trong 7 ngày: có dư địa mở rộng.`,
    why:'ROAS vượt target ổn định cho thấy target/ngân sách đang kìm lưu lượng có lãi. Hạ dần target '+
     'tROAS hoặc tăng ngân sách theo bước nhỏ để mua thêm doanh thu có kiểm soát.',
    actions:[`Hạ target tROAS HOẶC tăng ngân sách từng bước tối đa ${MAX_STEP_PERCENT}% — chỉ một biến mỗi lần.`,
     'Theo dõi ROAS 3–7 ngày sau mỗi bước; dừng khi ROAS tiệm cận target.'],
    guardrails:['Cơ hội không phải cam kết: ROAS thường giảm khi mở rộng lưu lượng.',
     'Bị chặn tự động nếu chiến dịch đang có cảnh báo cắt/giảm (conflict guard).']};
 }
 return null;
}
function manualBiddingAtScale(c,t,ctx){
 const strategy=String(get(c,'bidding_strategy')||'');
 const conversions=num(get(c,'conversions'));
 if(conversions===null||conversions<MANUAL_BIDDING_MIN_CONVERSIONS)return null;
 if(ctx.platform==='google'&&GOOGLE_MANUAL_STRATEGIES.includes(strategy)){
   return {level:'review',
    message:`Chiến dịch vẫn đấu thầu thủ công (${strategy}) nhưng đã có ${int(conversions)} chuyển đổi `+
     `trong 7 ngày — đủ dữ liệu để thử nghiệm đấu thầu thông minh có kiểm soát.`,
    why:'Ở lượng chuyển đổi này, Smart Bidding (tCPA/Maximize Conversions) thường học tốt hơn chỉnh '+
     'tay, nhưng chuyển đổi chiến lược là thay đổi lớn: phải thử nghiệm có đối chứng thay vì '+
     'chuyển thẳng toàn bộ.',
    actions:['Tạo bản thử nghiệm (experiment) chia lưu lượng: giữ chiến dịch bid tay làm đối chứng, bản thử dùng Maximize Conversions, sau khi ổn định mới gắn tCPA quanh CPA thực tế.',
     'Chạy thử ít nhất 2–3 tuần hoặc đủ ~30 chuyển đổi cho bản thử trước khi kết luận.',
     'Nếu bản thử thắng: chuyển dần và gỡ bản đối chứng; nếu thua: quay lại bid tay, không coi là thất bại.'],
    guardrails:['Không chuyển thẳng 100% lưu lượng sang Smart Bidding trong một lần.',
     'Không gắn tCPA chặt hơn CPA thực tế hiện tại khi mới chuyển (hệ thống sẽ nghẽn phân phối).']};
 }
 if(ctx.platform==='meta'&&strategy==='LOWEST_COST_WITH_BID_CAP'){
   return {level:'review',
    message:`Chiến dịch đang dùng bid cap nhưng đã có ${int(conversions)} chuyển đổi trong 7 ngày — `+
     `nên thử nghiệm cost per result goal để giảm nghẽn phân phối.`,
    why:'Bid cap kiểm soát chặt giá từng phiên đấu giá nhưng dễ làm nghẽn phân phối và CPA dao động '+
     'khi thị trường đổi. Cost per result goal giữ CPA quanh mục tiêu ở cấp độ trung bình, '+
     'thường ổn định hơn khi lượng chuyển đổi đã đủ lớn.',
    actions:['Nhân bản một chiến dịch thử với cost per result goal đặt quanh CPA bền vững hiện tại; giữ chiến dịch bid cap làm đối chứng.',
     'So sánh sau ít nhất 7 ngày và đủ lượng chuyển đổi ở cả hai bản trước khi quyết định.'],
    guardrails:['Cost per result goal đặt ở cấp ad set trên Meta — kiểm tra cấu trúc chiến dịch thử trước khi so sánh.',
     'Không tắt bid cap đồng loạt; chỉ chuyển khi bản thử chứng minh được hiệu quả.']};
 }
 return null;
}
function budgetConstrainedWinner(c,t,ctx){
 if(ctx.platform!=='google')return null;
 const lost=num(get(c,'budget_lost_is')),conversions=num(get(c,'conversions'));
 if(lost===null||lost<BUDGET_LOST_IS_MIN)return null;
 if(conversions===null||conversions<SCALE_MIN_CONVERSIONS)return null;
 const cpa=num(get(c,'cpa')),roas=num(get(c,'roas'));
 const btc=num(get(c,'bid_target_cpa')),btr=num(get(c,'bid_target_roas'));
 const healthy=(t.cpa_target!==null&&cpa!==null&&cpa<=t.cpa_target)
   ||(t.roas_target!==null&&roas!==null&&roas>=t.roas_target)
   ||(btc!==null&&cpa!==null&&cpa<=btc)
   ||(btr!==null&&roas!==null&&roas>=btr);
 if(!healthy)return null;
 const lostPct=pyRound(lost*100);
 return {level:'opportunity',
  message:`Chiến dịch đang đạt mục tiêu nhưng mất khoảng ${lostPct}% thị phần hiển thị vì ngân sách `+
   `(lost impression share do ngân sách, 7 ngày) với ${int(conversions)} chuyển đổi: ngân sách `+
   `đang là nút thắt tăng trưởng. Trước tiên hãy xác nhận đây là chiến dịch dạng Search — chỉ số `+
   `này chỉ có ý nghĩa với Search, và công cụ không nhìn thấy loại chiến dịch.`,
  why:'Khi hiệu quả đã đạt mục tiêu mà thị phần hiển thị bị mất vì ngân sách, mỗi đồng ngân sách thêm '+
   'có xác suất cao mua được chuyển đổi ở mức CPA/ROAS tương đương — khác hẳn tăng ngân sách cho '+
   'chiến dịch chưa đạt mục tiêu. Nhưng impression share bị mất vì ngân sách chỉ đo được đáng tin '+
   'ở chiến dịch Search; ở các dạng khác con số này không mang cùng ý nghĩa.',
  actions:['Xác nhận trong Google Ads đây là chiến dịch Search (và ngân sách không dùng chung với chiến dịch khác) trước khi làm bất cứ điều gì.',
   `Tăng ngân sách ngày từng bước tối đa ${MAX_STEP_PERCENT}%, theo dõi CPA/ROAS và lost IS sau mỗi bước 3–7 ngày.`,
   'Nếu không muốn tăng tổng ngân sách: chuyển dần ngân sách từ các chiến dịch chưa đạt mục tiêu trong cùng tài khoản sang chiến dịch này.',
   'Dừng tăng khi lost IS vì ngân sách về gần 0 hoặc CPA bắt đầu vượt mục tiêu.'],
  guardrails:['Chỉ áp dụng cho chiến dịch Search đã xác nhận; không suy ra từ con số này cho Display/Video/Performance Max.',
   `Không tăng quá ${MAX_STEP_PERCENT}% ngân sách trong một bước; không tăng đồng thời ngân sách và target.`,
   'Cơ hội này tự động bị ẩn khi chiến dịch có cảnh báo cắt/giảm (conflict guard) — xử lý cảnh báo đó trước.']};
}
function adsetTargetMissed(c,t,ctx){
 if(ctx.platform!=='meta')return null;
 if(num(get(c,'bid_target_cpa'))!==null)return null;
 const target=num(get(c,'adset_bid_target_cpa'));
 const cpa=num(get(c,'cpa')),conversions=num(get(c,'conversions'));
 if(target===null||cpa===null||conversions===null)return null;
 if(conversions<CPA_MIN_CONVERSIONS||cpa<=target*ADSET_TARGET_REVIEW_RATIO)return null;
 const level=cpa>target*ADSET_TARGET_CRITICAL_RATIO?'critical':'review';
 const over=pctDelta(cpa,target);
 return {level,
  message:`CPA thực tế ${money(cpa,ctx.currency)} cao hơn mục tiêu giá mỗi kết quả `+
   `${money(target,ctx.currency)} khoảng ${over}% (dựa trên ${int(conversions)} chuyển đổi `+
   `trong 7 ngày). Lưu ý: trên Meta mục tiêu này nằm ở cấp nhóm quảng cáo (ad set), không phải `+
   `cấp chiến dịch; con số mục tiêu ở đây là giá trị trung vị của các ad set trong chiến dịch — `+
   `một xấp xỉ để tham chiếu, từng ad set có thể đặt mục tiêu khác nhau.`,
  why:'Cost per result goal ở cấp ad set là con số hệ thống Meta dùng để giữ CPA trung bình của từng '+
   'ad set. CPA toàn chiến dịch cao hơn hẳn trung vị goal cho thấy phần lớn ad set đang mua kết quả '+
   'đắt hơn mục tiêu đã khai — cần rà soát theo từng ad set thay vì kết luận ở cấp chiến dịch.',
  actions:['Mở chiến dịch trong Meta Ads Manager và đối chiếu CPA TỪNG ad set với goal của chính ad set đó; xử lý các ad set lệch nhất trước.',
   'Kiểm chứng tracking/CAPI và độ trễ chuyển đổi trước khi kết luận (loại trừ cảnh báo tracking nếu đang mở).',
   `Với ad set lệch kéo dài: hạ chi tiêu hoặc nới goal từng bước tối đa ${MAX_STEP_PERCENT}%, chờ ít nhất 7 ngày sau mỗi bước.`,
   'Dồn ngân sách về các ad set đang bám sát goal trong cùng chiến dịch.'],
  guardrails:['Giá trị trung vị chỉ là xấp xỉ: không dùng nó để kết luận về một ad set cụ thể.',
   `Không chỉnh quá ${MAX_STEP_PERCENT}% trong một lần; tôn trọng giai đoạn học của ad set sau mỗi lần chỉnh.`]};
}
function audienceFatigueRisk(c,t,ctx){
 const frequency=num(get(c,'frequency')),impressions=num(get(c,'impressions')),ctr=num(get(c,'ctr_percent'));
 if(frequency===null||impressions===null||impressions<FATIGUE_MIN_IMPRESSIONS)return null;
 const high=frequency>=FATIGUE_FREQUENCY_HIGH;
 const tired=frequency>=FATIGUE_FREQUENCY_REVIEW&&ctr!==null&&ctr<FATIGUE_CTR_MAX_PERCENT;
 if(!(high||tired))return null;
 const message=high
  ?`Tần suất hiển thị ${ratio(frequency)} lần/người trong 7 ngày với ${int(impressions)} lượt hiển thị: `+
   `cùng một nhóm người đang bị lặp quảng cáo ở mức cao, kể cả khi CTR chưa tụt rõ.`
  :`Tần suất hiển thị ${ratio(frequency)} lần/người trong 7 ngày với CTR ${ratio(ctr)}% `+
   `(${int(impressions)} lượt hiển thị): người xem thấy quảng cáo lặp lại mà phản hồi đang yếu đi.`;
 return {level:'review',message,
  why:'Tần suất cao kéo dài làm creative mất tác dụng: cùng thông điệp chạm cùng người quá nhiều lần '+
   'khiến tỉ lệ nhấp và chuyển đổi suy giảm, chi phí mỗi kết quả tăng dần — dấu hiệu cổ điển của '+
   'mệt mỏi đối tượng (audience fatigue) trên Meta. Tần suất là số liệu cấp chiến dịch; công cụ '+
   'KHÔNG nhìn thấy dữ liệu từng mẫu quảng cáo/creative, nên phần xử lý dưới đây là checklist để '+
   'người phụ trách tự kiểm tra trong Ads Manager, không phải kết luận về một creative cụ thể.',
  actions:['Checklist làm mới creative trong Ads Manager: xác định mẫu quảng cáo nào có tần suất cao nhất và CTR tụt rõ nhất, thay bằng biến thể mới (hình ảnh/video, hook, thông điệp) thay vì chỉ tăng ngân sách.',
   'Checklist mở rộng đối tượng: nới độ tuổi/khu vực/sở thích hoặc gộp các ad set chồng lấp đang tranh cùng một nhóm người.',
   'Checklist giới hạn lặp lại: cân nhắc loại trừ người đã tương tác/mua hàng khỏi tập prospecting, và tách ngân sách remarketing riêng để không dồn tần suất vào một tập.',
   'Sau khi làm mới creative hoặc mở rộng đối tượng, theo dõi tần suất và CTR thêm 3–7 ngày trước khi kết luận.'],
  guardrails:['Không kết luận một creative cụ thể "cháy" chỉ từ số liệu cấp chiến dịch — phải đối chiếu cấp quảng cáo trong Ads Manager.',
   'Tần suất cao ở remarketing là bình thường hơn prospecting; đối chiếu đúng vai trò chiến dịch trước khi xử lý.']};
}

export const PLAYBOOK=[
 {code:'spend_no_conversions',platform:'both',category:'tracking',severity:'review',title:'Chi tiêu chưa ghi nhận chuyển đổi — kiểm tra tracking trước'},
 {code:'cpa_above_target',platform:'both',category:'bid_cost',severity:'review',title:'CPA vượt mục tiêu — giảm tốc theo bước nhỏ'},
 {code:'cpa_well_below_target_scale',platform:'both',category:'scale',severity:'opportunity',title:'CPA thấp hơn mục tiêu — cơ hội mở rộng có kiểm soát'},
 {code:'roas_below_target',platform:'both',category:'roas',severity:'review',title:'ROAS dưới mục tiêu — kiểm tra doanh thu rồi giảm tốc'},
 {code:'roas_above_target_scale',platform:'both',category:'scale',severity:'opportunity',title:'ROAS vượt mục tiêu — cơ hội tăng ngân sách theo bước'},
 {code:'low_ctr',platform:'both',category:'structure',severity:'review',title:'CTR thấp — rà soát nội dung và đối tượng'},
 {code:'high_ctr_no_conversions',platform:'both',category:'tracking',severity:'review',title:'CTR khỏe nhưng 0 chuyển đổi — lệch ở trang đích/tracking'},
 {code:'low_conversion_volume_for_smart_bidding',platform:'both',category:'bid_cost',severity:'review',title:'Lượng chuyển đổi thấp cho đấu thầu thông minh — gộp và dồn tín hiệu'},
 {code:'dead_campaign',platform:'both',category:'structure',severity:'review',title:'Chiến dịch đang bật nhưng không phân phối'},
 {code:'cpa_drift_vs_baseline',platform:'both',category:'bid_cost',severity:'review',title:'CPA lệch khỏi nền của chính chiến dịch'},
 {code:'roas_drift_vs_baseline',platform:'both',category:'roas',severity:'review',title:'ROAS lệch khỏi nền của chính chiến dịch'},
 {code:'platform_target_missed',platform:'both',category:'bid_cost',severity:'review',title:'Lệch target giá thầu thật trên nền tảng — hiệu chỉnh theo bước'},
 {code:'platform_target_headroom',platform:'both',category:'scale',severity:'opportunity',title:'Dư địa so với target nền tảng — cơ hội mở rộng có kiểm soát'},
 {code:'manual_bidding_at_scale',platform:'both',category:'structure',severity:'review',title:'Vẫn đấu thầu thủ công ở lượng chuyển đổi lớn — thử nghiệm Smart Bidding'},
 {code:'budget_constrained_winner',platform:'google',category:'scale',severity:'opportunity',title:'Đang đạt mục tiêu nhưng nghẽn ngân sách — cơ hội tăng ngân sách có kiểm soát'},
 {code:'adset_target_missed',platform:'meta',category:'bid_cost',severity:'review',title:'Lệch mục tiêu giá thầu cấp ad set (Meta) — rà soát theo từng ad set'},
 {code:'audience_fatigue_risk',platform:'meta',category:'structure',severity:'review',title:'Nguy cơ mệt mỏi đối tượng — tần suất hiển thị lặp lại cao'},
 {code:'account_fragmentation',platform:'both',category:'structure',severity:'opportunity',title:'Tài khoản phân mảnh — cơ hội gộp chiến dịch'},
 {code:'account_budget_reallocation',platform:'both',category:'scale',severity:'opportunity',title:'Tái phân bổ ngân sách khỏi chiến dịch kém hiệu quả'},
];
const CONDITIONS={spend_no_conversions:spendNoConversions,cpa_above_target:cpaAboveTarget,
 cpa_well_below_target_scale:cpaWellBelowTargetScale,roas_below_target:roasBelowTarget,
 roas_above_target_scale:roasAboveTargetScale,low_ctr:lowCtr,high_ctr_no_conversions:highCtrNoConversions,
 low_conversion_volume_for_smart_bidding:lowConversionVolume,dead_campaign:deadCampaign,
 cpa_drift_vs_baseline:cpaDriftVsBaseline,roas_drift_vs_baseline:roasDriftVsBaseline,
 platform_target_missed:platformTargetMissed,platform_target_headroom:platformTargetHeadroom,
 manual_bidding_at_scale:manualBiddingAtScale,budget_constrained_winner:budgetConstrainedWinner,
 adset_target_missed:adsetTargetMissed,audience_fatigue_risk:audienceFatigueRisk};
const BY_CODE=Object.fromEntries(PLAYBOOK.map(e=>[e.code,e]));

// --- Baselines and outcome verification -----------------------------------------
export function computeBaselines(snapshots){
 const grouped={};
 for(const snap of dictList(snapshots)){
   if(get(snap,'id')===null)continue;
   (grouped[String(snap.id)]||(grouped[String(snap.id)]=[])).push(snap);
 }
 const baselines={};
 for(const [id,rows] of Object.entries(grouped)){
   const cpas=rows.map(r=>num(get(r,'cpa'))).filter(v=>v!==null);
   const roases=rows.map(r=>num(get(r,'roas'))).filter(v=>v!==null);
   const b={campaign_id:id,periods:rows.length,median_cpa:null,median_roas:null,cpa_volatility:null,roas_volatility:null};
   if(cpas.length){const m=median(cpas);b.median_cpa=pyRound(m,4);
     if(cpas.length>=2&&m>0)b.cpa_volatility=pyRound((Math.max(...cpas)-Math.min(...cpas))/m,4);}
   if(roases.length){const m=median(roases);b.median_roas=pyRound(m,4);
     if(roases.length>=2&&m>0)b.roas_volatility=pyRound((Math.max(...roases)-Math.min(...roases))/m,4);}
   baselines[id]=b;
 }
 return baselines;
}
const TRACKING_CODES=['spend_no_conversions','high_ctr_no_conversions'];
const CPA_CODES=['cpa_above_target','cpa_well_below_target_scale','cpa_drift_vs_baseline'];
const ROAS_CODES=['roas_below_target','roas_above_target_scale','roas_drift_vs_baseline'];
const band=(change,lowerBetter)=>{
 const improved=lowerBetter?change< -OUTCOME_NOISE_BAND:change>OUTCOME_NOISE_BAND;
 const worsened=lowerBetter?change>OUTCOME_NOISE_BAND:change< -OUTCOME_NOISE_BAND;
 return improved?'improved':worsened?'worsened':'unchanged';
};
export function verifyOutcome(base,cur,code){
 if(!isDict(base)||!isDict(cur))return 'insufficient_data';
 const bc=num(get(base,'conversions')),cc=num(get(cur,'conversions'));
 const enough=()=>bc!==null&&cc!==null&&bc>=OUTCOME_MIN_CONVERSIONS&&cc>=OUTCOME_MIN_CONVERSIONS;
 if(TRACKING_CODES.includes(code)){
   if(bc===null||cc===null)return 'insufficient_data';
   if(bc===0)return cc>=OUTCOME_MIN_CONVERSIONS?'improved':'unchanged';
   return 'insufficient_data';
 }
 if(code==='low_ctr'||code==='audience_fatigue_risk'){
   const b=num(get(base,'ctr_percent')),c=num(get(cur,'ctr_percent'));
   if(b===null||c===null||b<=0)return 'insufficient_data';
   return band(c/b-1,false);
 }
 if(code==='low_conversion_volume_for_smart_bidding'){
   if(bc===null||cc===null)return 'insufficient_data';
   if(bc===0)return cc>0?'improved':'unchanged';
   return band(cc/bc-1,false);
 }
 if(code==='dead_campaign'){
   const b=num(get(base,'impressions')),c=num(get(cur,'impressions'));
   if(b===null||c===null)return 'insufficient_data';
   if(b===0)return c>0?'improved':'unchanged';
   return 'insufficient_data';
 }
 if(code==='budget_constrained_winner'){
   if(!enough())return 'insufficient_data';
   return band(cc/bc-1,false);
 }
 if(code==='adset_target_missed'){
   if(!enough())return 'insufficient_data';
   const b=num(get(base,'cpa')),c=num(get(cur,'cpa'));
   if(b===null||c===null||b<=0)return 'insufficient_data';
   return band(c/b-1,true);
 }
 if(['platform_target_missed','platform_target_headroom','manual_bidding_at_scale'].includes(code)){
   if(!enough())return 'insufficient_data';
   const [key,lower]=num(get(base,'bid_target_roas'))&&code!=='manual_bidding_at_scale'?['roas',false]:['cpa',true];
   const b=num(get(base,key)),c=num(get(cur,key));
   if(b===null||c===null||b<=0)return 'insufficient_data';
   return band(c/b-1,lower);
 }
 if(CPA_CODES.includes(code)||ROAS_CODES.includes(code)){
   if(!enough())return 'insufficient_data';
   const key=CPA_CODES.includes(code)?'cpa':'roas';
   const b=num(get(base,key)),c=num(get(cur,key));
   if(b===null||c===null||b<=0)return 'insufficient_data';
   return band(c/b-1,CPA_CODES.includes(code));
 }
 return 'insufficient_data';
}

// --- Evaluation ----------------------------------------------------------------------
export function evaluateAccount(campaigns,platform,currency='',goal=null){
 const targets=goalTargets(goal,currency);
 const active=dictList(campaigns).filter(c=>isActive(c,platform));
 const findings=[];
 const fragmented=active.filter(c=>{const v=num(get(c,'conversions')),s=num(get(c,'spend'));
   return v!==null&&s!==null&&s>0&&v<ACCOUNT_FRAGMENT_MAX_CONVERSIONS;});
 if(fragmented.length>=ACCOUNT_FRAGMENT_MIN_CAMPAIGNS){
   const total=pySum(fragmented.map(c=>num(get(c,'spend'))||0));
   findings.push(finding('ACCOUNT',BY_CODE.account_fragmentation,'opportunity',
    `${fragmented.length} chiến dịch đang chạy đều dưới ${ACCOUNT_FRAGMENT_MAX_CONVERSIONS} chuyển đổi trong 7 ngày `+
    `(tổng chi ${money(total,currency)}): tín hiệu học đang bị phân mảnh khắp tài khoản. `+
    `Cân nhắc gộp các chiến dịch cùng mục tiêu.`,
    'Mỗi chiến dịch/con dấu quảng cáo là một "người học" riêng của nền tảng. Chia ngân sách cho quá nhiều '+
    'chiến dịch ít chuyển đổi khiến không chiến dịch nào đủ dữ liệu để đấu thầu thông minh ổn định.',
    ['Liệt kê các chiến dịch cùng mục tiêu/đối tượng/sản phẩm — đó là ứng viên gộp trước tiên.',
     'Gộp theo từng cụm nhỏ, giữ lại chiến dịch có dữ liệu lịch sử tốt nhất làm khung.',
     'Sau khi gộp, chờ ít nhất 7–14 ngày dữ liệu trước khi đánh giá lại; đừng gộp tất cả cùng lúc.'],
    ['Gộp là thay đổi cấu trúc lớn: làm từng cụm và giữ bản ghi để đối chiếu trước/sau.']));
 }
 const {cpa_target:cpaTarget,roas_target:roasTarget}=targets;
 if(cpaTarget!==null||roasTarget!==null){
   let total=0,ineffSpend=0,ineffCount=0;
   for(const c of active){
     const spend=num(get(c,'spend'));
     if(spend===null||spend<=0)continue;
     total+=spend;
     const cpa=num(get(c,'cpa')),roas=num(get(c,'roas'));
     let bad=false;
     if(cpaTarget!==null&&cpa!==null&&cpa>cpaTarget*ACCOUNT_INEFFICIENT_CPA_RATIO)bad=true;
     if(roasTarget!==null&&roas!==null&&roas<roasTarget)bad=true;
     if(bad){ineffSpend+=spend;ineffCount++;}
   }
   if(total>0&&ineffSpend/total>ACCOUNT_INEFFICIENT_SPEND_SHARE){
     const share=pyRound(ineffSpend/total*100);
     const yardstick=cpaTarget!==null?`CPA trên ${pyG(ACCOUNT_INEFFICIENT_CPA_RATIO)}x mục tiêu ${money(cpaTarget,currency)}`
       :`ROAS dưới mục tiêu ${ratio(roasTarget)}`;
     findings.push(finding('ACCOUNT',BY_CODE.account_budget_reallocation,'opportunity',
      `${share}% tổng chi 7 ngày (${money(ineffSpend,currency)} trên ${money(total,currency)}) `+
      `đang dồn vào ${ineffCount} chiến dịch không đạt mục tiêu (${yardstick}): cân nhắc tái phân bổ dần `+
      `sang các chiến dịch đạt mục tiêu.`,
      'Ở cấp tài khoản, đòn bẩy lớn nhất thường không nằm trong từng chiến dịch mà ở cách ngân sách được '+
      'chia giữa các chiến dịch. Tiền đang nuôi các chiến dịch kém hiệu quả là tiền không mua được chuyển đổi rẻ.',
      [`Chuyển ngân sách theo từng bước tối đa ${MAX_STEP_PERCENT}% mỗi lần từ chiến dịch kém sang chiến dịch đạt mục tiêu.`,
       'Giữ lại một phần ngân sách thử nghiệm cho chiến dịch đang cải thiện — đừng cắt về 0 ngay.',
       'Đo lại sau mỗi bước bằng chính các quy tắc của playbook này (vòng kiểm chứng kết quả).'],
      ['Không tái phân bổ dựa trên một kỳ dữ liệu duy nhất nếu chuyển đổi còn độ trễ lớn.']));
   }
 }
 return findings;
}

export function evaluateCampaigns(campaigns,platform,currency,goal=null,baselines=null){
 const targets=goalTargets(goal,currency);
 const ctx={platform,currency,baselines:isDict(baselines)?baselines:{}};
 let findings=[];
 for(const c of dictList(campaigns)){
   if(get(c,'id')===null||!isActive(c,platform))continue;
   for(const entry of PLAYBOOK){
     const cond=CONDITIONS[entry.code];
     if(!cond)continue;
     if(entry.platform!=='both'&&entry.platform!==platform)continue;
     const r=cond(c,targets,ctx);
     if(r)findings.push(finding(c.id,entry,r.level,r.message,r.why,r.actions,r.guardrails));
   }
 }
 findings.push(...evaluateAccount(campaigns,platform,currency,goal));
 findings=applyConflictGuard(findings);
 return findings.slice(0,MAX_FINDINGS);
}

function applyConflictGuard(findings){
 const byCampaign={};
 for(const f of findings)(byCampaign[f.campaign_id]||(byCampaign[f.campaign_id]=[])).push(f);
 const suppressed={};
 for(const [id,group] of Object.entries(byCampaign)){
   if(id==='ACCOUNT')continue;
   const blockers=group.filter(f=>f.level==='critical'||(CUT_CODES.includes(f.code)&&f.level==='review'));
   const scale=group.filter(f=>SCALE_CODES.includes(f.code));
   if(blockers.length&&scale.length)suppressed[id]=scale.map(f=>f.code);
 }
 if(!Object.keys(suppressed).length)return findings;
 const kept=[];
 for(let f of findings){
   const codes=suppressed[f.campaign_id];
   if(codes&&SCALE_CODES.includes(f.code))continue;
   if(codes&&(f.level==='critical'||CUT_CODES.includes(f.code))){
     f={...f,suppressed:[...codes]};
     suppressed[f.campaign_id]=null;
   }
   kept.push(f);
 }
 return kept;
}
