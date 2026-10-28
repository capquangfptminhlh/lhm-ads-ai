/* Behavioral test of the customer gate without browser/network dependencies.
 * node --test tests/customer_login_failure.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const script=readFileSync(new URL('../static/customer-login.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,20));

function mount(){
  const elements=new Map();
  const element=id=>{
    if(!elements.has(id)){
      elements.set(id,{
        id,hidden:false,disabled:false,textContent:'',dataset:{},
        listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},
        setAttribute(){},classList:{add(){},remove(){},toggle(){}}
      });
    }
    return elements.get(id);
  };
  const locations=[],events={};
  const root={classList:{add(){},remove(){}}};
  const window={
    LHMDeviceVault:{isUnlocked:()=>false,lock(){}},
    dispatchEvent(){},addEventListener(name,fn){events[name]=fn;}
  };
  const document={
    body:root,getElementById:element,addEventListener(name,fn){events[name]=fn;}
  };
  const fetch=async(path,options={})=>{
    if(path==='/api/auth/session')
      return Response.json({code:'SERVER_NOT_READY',error:'Dịch vụ bản quyền chưa được triển khai'}, {status:503});
    if(path==='/api/auth/logout'&&options.method==='POST')
      return Response.json({error:'Temporary outage'}, {status:503});
    throw Error('unexpected request '+path);
  };
  runInNewContext(script,{window,document,location:{assign:url=>locations.push(url)},
    fetch,Response,Event,Intl,Date,clearInterval,clearTimeout,setInterval,setTimeout,
    confirm:()=>true,navigator:{userAgent:'Chrome Windows'}});
  return {element,locations,events};
}

test('HTTP 503 shows a useful server error, not a misleading Google login prompt',async()=>{
  const app=mount();
  await tick();
  const message=app.element('customer-login-status').textContent;
  assert.match(message,/chưa sẵn sàng/i);
  assert.match(message,/chưa được triển khai/i);
  assert.doesNotMatch(message,/Đăng nhập bằng Google để bắt đầu/);
  assert.equal(app.locations.length,0);
});

test('logout network failure keeps the UI locked and never claims successful sign-out',async()=>{
  const app=mount();
  await tick();
  await app.element('customer-cloud-logout').listeners.click();
  assert.match(app.element('customer-login-status').textContent,/Chưa thể đăng xuất trên máy chủ/);
  assert.equal(app.locations.length,0);
  assert.equal(app.element('customer-login-box').hidden,false);
  assert.equal(app.element('pwa-login-portal').hidden,true);
});
