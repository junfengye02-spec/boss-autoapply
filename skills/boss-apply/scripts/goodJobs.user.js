// ==UserScript==
// @name         BOSS Application Runner
// @namespace    codex-skill-boss-apply
// @version      1.0.0
// @description  根据本轮授权与画像筛选去重，只点击一次立即沟通
// @match        https://www.zhipin.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==
(function () {
'use strict';
if (window.top !== window.self) return;
const HOST='http://127.0.0.1:18764', OWNER='boss-skill-owner', TASK='boss-skill-task';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const api=(path,data={})=>new Promise((resolve,reject)=>GM_xmlhttpRequest({
    method:'POST',url:HOST+path,headers:{'Content-Type':'application/json'},data:JSON.stringify(data),timeout:20000,
    onload:r=>{try{const d=JSON.parse(r.responseText);r.status===200?resolve(d):reject(Error(d.error));}catch(e){reject(e);}},
    onerror:()=>reject(Error('本地服务连接失败')),ontimeout:()=>reject(Error('本地服务超时'))
}));
const text=s=>document.querySelector(s)?.innerText?.trim()||'';
const button=()=>document.querySelector('.btn-startchat');
const id=()=>location.pathname.match(/\/job_detail\/([\w~-]+)\.html/)?.[1];
const panel=document.createElement('section');
Object.assign(panel.style,{position:'fixed',right:'10px',bottom:'10px',zIndex:'2147483647',background:'#fff',border:'2px solid #008f91',padding:'14px',width:'330px',color:'#123',fontSize:'14px',borderRadius:'8px'});
const h=document.createElement('strong');h.textContent='BOSS 本轮投递 · 单次招呼';
const log=document.createElement('pre');Object.assign(log.style,{whiteSpace:'pre-wrap',maxHeight:'180px',overflow:'auto'});
const start=document.createElement('button');start.textContent='继续本轮授权投递';
const stop=document.createElement('button');stop.textContent='暂停投递';
panel.append(h,log,start,stop);document.body.append(panel);
const show=s=>{log.textContent=s;};
const counts=c=>`本轮已确认 ${c.confirmedToday}/${c.target}\n本轮已筛选 ${c.screened}，待核验 ${c.pending}\n${c.state} ${c.reason||''}`;
let busy=false,stopped=false;
async function pause(reason){stopped=true;sessionStorage.removeItem(OWNER);await api('/campaign/stop',{reason}).catch(()=>{});show('已暂停：'+reason);}
stop.onclick=()=>pause('用户/助手点击暂停');
async function navigate(){
    if(stopped||sessionStorage.getItem(OWNER)!=='yes')return;
    const c=await api('/campaign/status');show(counts(c));
    if(c.state!=='running'||c.confirmedToday>=c.target){sessionStorage.removeItem(OWNER);return;}
    const task=await api('/campaign/next');
    if(task.kind==='exhausted'){await pause('候选待助手审核或搜索已遍历');return;}
    sessionStorage.setItem(TASK,JSON.stringify(task));
    await sleep(1800);
    if(!stopped)location.assign(task.url);
}
async function waitFor(fn,limit=18000){const end=Date.now()+limit;while(Date.now()<end){if(stopped)throw Error('已暂停');const value=fn();if(value)return value;await sleep(500);}return null;}
function barrier(){
    const b=document.body.innerText;
    if(/请完成.*验证|请拖动.*滑块|安全验证|访问过于频繁|操作过于频繁|异常访问/.test(b))return '页面要求验证/操作限制';
    if(/今日.{0,20}(?:沟通|打招呼).{0,20}(?:上限|用完)|(?:沟通|打招呼).{0,20}(?:已达上限|次数已用完)|明天再来/.test(b))return 'BOSS提示今日沟通上限';
    return '';
}
async function collect(task){
    const loaded=await waitFor(()=>document.querySelector('a[href*="/job_detail/"]'));
    if(!loaded){const why=barrier();if(why)throw Error(why);await api('/campaign/collect',{url:task.url,jobs:[]});return;}
    const jobs=new Map();let stable=0;
    for(let i=0;i<16;i++){
        const before=jobs.size;
        const links=Array.from(document.querySelectorAll('a[href*="/job_detail/"]'));
        for(const a of links){if(a.href&&a.innerText.trim())jobs.set(a.href.split('?')[0],{url:a.href,title:a.innerText.trim()});}
        if(!links.length)throw Error('列表选择器未找到岗位，暂停核验页面');
        links[links.length-1].scrollIntoView({block:'end'});
        await sleep(700);
        if(jobs.size===before)stable++;else stable=0;
        if(stable>=3)break;
        if(barrier())throw Error(barrier());
    }
    show(`本页读取 ${jobs.size} 个岗位，先筛选再发送`);
    await api('/campaign/collect',{url:task.url,jobs:[...jobs.values()]});
}
async function inspect(task){
    const loaded=await waitFor(()=>text('.name h1')&&text('.job-sec-text')&&button());
    if(!loaded){if(barrier())throw Error(barrier());await api('/campaign/skip',{key:task.key});return;}
    if(barrier())throw Error(barrier());
    if('boss:'+id()!==task.key)throw Error('岗位身份不符');
    const requirements=text('.job-primary .info-primary')||text('.info-primary');
    const companyName=document.title.match(/」_(.+?)招聘-BOSS直聘/)?.[1]||'';
    const companyAnchor=Array.from(document.querySelectorAll('a[href*="/gongsi/"]')).find(a=>/\/gongsi\/[\w~]+\.html/.test(a.href)&&a.innerText.trim()===companyName);
    const job={jobId:id(),url:location.origin+location.pathname,title:text('.name h1'),detail:text('.job-sec-text'),requirements,
        company:companyName,pageTitle:document.title,companyUrl:companyAnchor?.href?.split('?')[0]||'',
        degree:requirements.match(/本科|硕士|博士|大专|学历不限/)?.[0]||'',
        city:text('.info-primary a[href*="/c"]')||'',
        experience:requirements.match(/\d+-\d+年|\d+年以上|经验不限|在校\/应届/)?.[0]||'',
        buttonText:button().innerText.trim(),source:'本人授权批次：实时DOM'};
    const d=await api('/campaign/candidate',{job});
    show(`${job.company} ${job.title}\n${d.status} ${d.score}\n${d.reasons.join('；')}`);
    if(d.status!=='pass')return;
    if(button().innerText.trim()!=='立即沟通')return;
    await sleep(1800);
    if(stopped)return;
    const claim=await api('/campaign/claim',{key:task.key});
    if(!claim.allowed)throw Error('未获取单次投递资格');
    // Never type a second greeting. Only the native BOSS start-chat button is clicked once.
    const before=button().innerText.trim();
    if(before!=='立即沟通'||'boss:'+id()!==task.key)throw Error('点击前岗位状态变化，待核验');
    button().click();
    const success=await waitFor(()=>button()?.innerText.trim()==='继续沟通'||barrier(),20000);
    const after=button()?.innerText.trim()||'';
    const observed={jobId:id(),action:'greet',beforeCaptured:true,afterCaptured:true,beforeButton:before,afterButton:after,
        reason:barrier()||(!success?'页面未确认，不能自动重试':''),
        sentToast:document.body.innerText.includes('已发送'),title:job.title,company:job.company,observedAt:new Date().toISOString()};
    const c=await api('/campaign/result',{key:task.key,observed});show(counts(c));
    if(c.state!=='running'){stopped=true;sessionStorage.removeItem(OWNER);}
    await sleep(2000);
}
async function run(){
    if(busy||sessionStorage.getItem(OWNER)!=='yes')return;busy=true;
    try{const c=await api('/campaign/status');show(counts(c));if(c.state!=='running'){sessionStorage.removeItem(OWNER);return;}
        const task=JSON.parse(sessionStorage.getItem(TASK)||'null');
        if(task){
            if(task.kind==='job')await inspect(task);else if(task.kind==='search')await collect(task);
            sessionStorage.removeItem(TASK);
        }
        await navigate();
    }catch(e){await pause(String(e.message||e));}finally{busy=false;}
}
start.onclick=async()=>{try{stopped=false;await api('/campaign/start');sessionStorage.setItem(OWNER,'yes');await run();}catch(e){show(e.message);}};
api('/campaign/status').then(c=>show(counts(c))).catch(e=>show(e.message));
if(sessionStorage.getItem(OWNER)==='yes')setTimeout(run,1000);
})();
