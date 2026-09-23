#!/usr/bin/env python3
"""Local BOSS ledger and reviewed-candidate queue. No BOSS network requests."""
import argparse, hashlib, json, re, sqlite3
from datetime import datetime, date
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
def digest(value): return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
def job_digest(job):
    return digest({k: re.sub(r'\s+', '', str(job.get(k) or '')) for k in ('jobId','title','company','detail','requirements')})

def identity(url):
    u = urlparse(url)
    m = re.fullmatch(r'/job_detail/([\w~-]+)\.html', u.path)
    return 'boss:' + m[1] if u.hostname == 'www.zhipin.com' and m else None

def connect(root):
    c = sqlite3.connect(root / 'boss.sqlite3', timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,day TEXT,target INTEGER,mode TEXT,state TEXT,reason TEXT,profile TEXT,authorized INTEGER);
    CREATE TABLE IF NOT EXISTS jobs(key TEXT PRIMARY KEY,data TEXT,updated TEXT);
    CREATE TABLE IF NOT EXISTS queue(run TEXT,key TEXT,url TEXT,state TEXT,decision TEXT,PRIMARY KEY(run,key));
    CREATE TABLE IF NOT EXISTS searches(run TEXT,url TEXT,state TEXT,PRIMARY KEY(run,url));
    CREATE TABLE IF NOT EXISTS applications(key TEXT PRIMARY KEY,run TEXT,status TEXT,evidence TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS events(run TEXT,key TEXT,action TEXT,evidence TEXT,created TEXT);
    ''')
    return c

class Engine:
    def __init__(self, root, run): self.root, self.run = Path(root), run
    def status(self, c):
        r = dict(c.execute('SELECT * FROM runs WHERE id=?', (self.run,)).fetchone())
        r.pop('profile')
        r['confirmedToday'] = c.execute("SELECT count(*) FROM applications WHERE run=? AND status='communication_confirmed'", (self.run,)).fetchone()[0]
        r['pending'] = c.execute("SELECT count(*) FROM applications WHERE status='pending_verification'").fetchone()[0]
        r['screened'] = c.execute("SELECT count(*) FROM queue WHERE run=? AND decision IS NOT NULL", (self.run,)).fetchone()[0]
        r['queue'] = dict(c.execute('SELECT state,count(*) FROM queue WHERE run=? GROUP BY state', (self.run,)).fetchall())
        return r
    def active(self, c):
        s = self.status(c)
        if s['day'] != date.today().isoformat(): raise ValueError('日期已变，停止；重新确认本次任务范围')
        if s['state'] != 'running': raise ValueError('当前批次未运行')
        if s['pending']: raise ValueError('存在未核验点击；禁止继续发送')
        if s['confirmedToday'] >= s['target']: raise ValueError('达到本轮上限')
        return s
    def pause(self, c, reason):
        c.execute("UPDATE runs SET state='paused',reason=? WHERE id=?", (reason, self.run)); c.commit()
    def handle(self, c, path, d):
        s = self.status(c)
        if path == '/campaign/status': return s
        if path == '/campaign/stop': self.pause(c,d.get('reason','暂停')); return self.status(c)
        if path == '/campaign/start':
            if s['pending'] or s['day'] != date.today().isoformat() or s['state']=='complete': raise ValueError('日期、待核验记录或完成状态阻止启动')
            c.execute("UPDATE runs SET state='running',reason='' WHERE id=?",(self.run,)); c.commit(); return self.status(c)
        if path == '/campaign/result':
            row=c.execute('SELECT * FROM applications WHERE key=?',(d['key'],)).fetchone()
            if not row or row['run']!=self.run or row['status']!='pending_verification': raise ValueError('没有本轮待核验点击')
            o=d['observed']; ok=('boss:'+o.get('jobId','')==d['key'] and o.get('beforeCaptured') and o.get('afterCaptured') and o.get('beforeButton')=='立即沟通' and o.get('afterButton')=='继续沟通')
            action='communication_confirmed' if ok else 'pending_verification'
            c.execute('UPDATE applications SET status=?,evidence=? WHERE key=?',(action,json.dumps(o,ensure_ascii=False),d['key']))
            c.execute('UPDATE queue SET state=? WHERE run=? AND key=?',('sent' if ok else 'uncertain',self.run,d['key']))
            c.execute('INSERT INTO events VALUES (?,?,?,?,?)',(self.run,d['key'],action,json.dumps(o,ensure_ascii=False),now()))
            if not ok: self.pause(c,'发送未确认，必须检查页面，禁止重试')
            elif self.status(c)['confirmedToday']>=s['target']: c.execute("UPDATE runs SET state='complete',reason='达到本轮目标' WHERE id=?",(self.run,))
            c.commit(); return self.status(c)
        s=self.active(c)
        if path=='/campaign/next':
            reviews=c.execute("SELECT count(*) FROM queue WHERE run=? AND state='review'",(self.run,)).fetchone()[0]
            if reviews>=5: self.pause(c,'待助手审核候选'); return {'kind':'exhausted'}
            row=c.execute("SELECT * FROM queue WHERE run=? AND (state='queued' OR (state='approved' AND ?='send')) ORDER BY CASE state WHEN 'approved' THEN 0 ELSE 1 END,rowid LIMIT 1",(self.run,s['mode'])).fetchone()
            if row:
                c.execute("UPDATE queue SET state='reading' WHERE run=? AND key=?",(self.run,row['key'])); c.commit(); return {'kind':'job','key':row['key'],'url':row['url']}
            row=c.execute("SELECT * FROM searches WHERE run=? AND state='queued' ORDER BY rowid LIMIT 1",(self.run,)).fetchone()
            if row:
                c.execute("UPDATE searches SET state='reading' WHERE run=? AND url=?",(self.run,row['url'])); c.commit(); return {'kind':'search','url':row['url']}
            self.pause(c,'候选待审核或搜索已遍历'); return {'kind':'exhausted'}
        if path=='/campaign/collect':
            for j in d['jobs']:
                k=identity(j['url'])
                if k and not c.execute('SELECT 1 FROM applications WHERE key=?',(k,)).fetchone(): c.execute('INSERT OR IGNORE INTO queue VALUES (?,?,?,?,NULL)',(self.run,k,j['url'].split('?')[0],'queued'))
            c.execute("UPDATE searches SET state='done' WHERE run=? AND url=?",(self.run,d['url'])); c.commit(); return self.status(c)
        if path=='/campaign/candidate':
            j=d['job']; k=identity(j['url'])
            q=c.execute('SELECT * FROM queue WHERE run=? AND key=?',(self.run,k)).fetchone()
            if not q: raise ValueError('不属于本轮候选')
            # The before-click button is not part of the review fingerprint.
            fingerprint=job_digest(j)
            c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',(k,json.dumps(j,ensure_ascii=False),now()))
            prior=c.execute('SELECT 1 FROM applications WHERE key=?',(k,)).fetchone()
            decision=json.loads(q['decision']) if q['decision'] else {}
            ph=c.execute('SELECT profile FROM runs WHERE id=?',(self.run,)).fetchone()[0]
            valid=decision.get('jobHash')==fingerprint and decision.get('profileHash')==digest(json.loads(ph))
            result={'status':'review','score':0,'reasons':['待助手按本轮画像核对完整岗位描述']}
            same_company_title=any(json.loads(r[0]).get('company')==j.get('company') and json.loads(r[0]).get('title')==j.get('title') for r in c.execute('SELECT jobs.data FROM applications JOIN jobs ON jobs.key=applications.key')) if j.get('company') else False
            if prior or same_company_title or j.get('buttonText')=='继续沟通':
                result['status']='duplicate';result['reasons']=['已有沟通或待核验记录']
                c.execute('INSERT OR IGNORE INTO applications VALUES (?,?,?,?,?)',(k,self.run,'previously_contacted','页面继续沟通；不计本轮新发送',now()))
            elif valid: result=decision
            state='approved' if result['status']=='pass' else result['status']
            c.execute('UPDATE queue SET state=? WHERE run=? AND key=?',(state,self.run,k));c.commit()
            # Screening mode can NEVER obtain a click claim.
            if s['mode']=='dry_run' and result['status']=='pass': result=dict(result,status='review',reasons=['只筛选模式：已通过，暂不发送'])
            return result
        if path=='/campaign/claim':
            c.execute('BEGIN IMMEDIATE');s=self.active(c)
            if s['mode']!='send' or not s['authorized']: raise ValueError('尚未获得本轮自动沟通授权')
            q=c.execute('SELECT * FROM queue WHERE run=? AND key=?',(self.run,d['key'])).fetchone()
            if not q or q['state']!='approved' or json.loads(q['decision'] or '{}').get('status')!='pass': raise ValueError('本轮未通过审核')
            if c.execute('SELECT 1 FROM applications WHERE key=?',(d['key'],)).fetchone(): raise ValueError('已经处理，不得重试')
            c.execute('INSERT INTO applications VALUES (?,?,?,?,?)',(d['key'],self.run,'pending_verification','点击前占位',now()));c.commit();return {'allowed':True}
        if path=='/campaign/skip':
            c.execute("UPDATE queue SET state='unreadable' WHERE run=? AND key=?",(self.run,d['key']));c.commit();return self.status(c)
        raise ValueError('未知路径')


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--run',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('init');q.add_argument('--profile',type=Path,required=True);q.add_argument('--target',type=int,required=True);q.add_argument('--authorized',action='store_true')
    q=sub.add_parser('seed');q.add_argument('file',type=Path)
    sub.add_parser('status');sub.add_parser('review');sub.add_parser('export');sub.add_parser('enable-send')
    q=sub.add_parser('decide');q.add_argument('file',type=Path)
    q=sub.add_parser('serve');q.add_argument('--port',type=int,default=18764)
    a=p.parse_args();a.root.mkdir(parents=True,exist_ok=True);e=Engine(a.root,a.run)
    with connect(a.root) as c:
        if a.command=='init':
            profile=json.loads(a.profile.read_text())
            for field in ('background','targets','locations','constraints','greeting'):
                if not profile.get(field): raise ValueError('画像缺少字段：'+field)
            if a.target<1: raise ValueError('目标必须为正整数')
            c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(a.run,date.today().isoformat(),a.target,'dry_run','ready','先筛选核验',json.dumps(profile,ensure_ascii=False),int(a.authorized)));c.commit()
        elif a.command=='seed':
            for url in json.loads(a.file.read_text()):
                u=urlparse(url)
                if u.hostname!='www.zhipin.com' or u.path!='/web/geek/jobs': raise ValueError('只接受界面核实的BOSS搜索URL')
                c.execute('INSERT OR IGNORE INTO searches VALUES (?,?,?)',(a.run,url,'queued'))
            c.commit()
        elif a.command=='review':
            rows=c.execute("SELECT q.key,j.data FROM queue q JOIN jobs j ON q.key=j.key WHERE q.run=? AND q.state='review' LIMIT 5",(a.run,)).fetchall()
            print(json.dumps([dict(r, data=json.loads(r['data'])) for r in rows],ensure_ascii=False,indent=2));return
        elif a.command=='decide':
            profile=json.loads(c.execute('SELECT profile FROM runs WHERE id=?',(a.run,)).fetchone()[0])
            for d in json.loads(a.file.read_text()):
                if d.get('status') not in ('pass','reject','review') or not d.get('reasons') or not isinstance(d.get('score'),(int,float)): raise ValueError('决策必须包含状态、分数及具体理由')
                row=c.execute('SELECT j.data FROM jobs j JOIN queue q ON q.key=j.key WHERE q.run=? AND q.key=?',(a.run,d['key'])).fetchone()
                if not row: raise ValueError('不是本轮已读取岗位')
                j=json.loads(row[0])
                if d['status']=='pass' and not all(j.get(k) for k in ('jobId','company','title','detail')): raise ValueError('岗位身份和完整描述不足，不能通过')
                if not 0<=d['score']<=100: raise ValueError('分数必须在0到100之间')
                d['jobHash']=job_digest(j);d['profileHash']=digest(profile)
                c.execute('UPDATE queue SET state=?,decision=? WHERE run=? AND key=?',('approved' if d['status']=='pass' else 'rejected' if d['status']=='reject' else 'held',json.dumps(d,ensure_ascii=False),a.run,d['key']))
            c.commit()
        elif a.command=='enable-send':
            s=e.status(c)
            if not s['authorized'] or s['pending'] or s['state']=='complete': raise ValueError('缺少本轮授权、有未核验记录或已完成')
            if not c.execute("SELECT 1 FROM queue WHERE run=? AND state='approved'",(a.run,)).fetchone(): raise ValueError('先审核小批量候选')
            c.execute("UPDATE runs SET mode='send',state='paused',reason='筛选核验完成，可继续本轮授权投递' WHERE id=?",(a.run,));c.commit()
        elif a.command=='export':
            s=e.status(c);rows=[dict(r) for r in c.execute('SELECT a.*,j.data FROM applications a LEFT JOIN jobs j ON j.key=a.key WHERE a.run=?',(a.run,))]
            out=a.root/(a.run+'-report.json');out.write_text(json.dumps(dict(s,applications=rows),ensure_ascii=False,indent=2));print(out);return
        elif a.command=='serve': pass
        print(json.dumps(e.status(c),ensure_ascii=False))
    if a.command!='serve': return
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,value,mime='application/json; charset=utf-8'):
            b=(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)).encode();self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            if self.path=='/goodJobs.user.js':
                js=Path(__file__).with_name('goodJobs.user.js').read_text().replace('127.0.0.1:18764','127.0.0.1:'+str(a.port));return self.reply(200,js,'text/javascript; charset=utf-8')
            if self.path=='/campaign/status':
                with connect(a.root) as c: return self.reply(200,e.status(c))
            self.reply(404,{'error':'not found'})
        def do_POST(self):
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<300000:raise ValueError('Invalid body')
                data=json.loads(self.rfile.read(n))
                with connect(a.root) as c: result=e.handle(c,self.path,data)
                self.reply(200,result)
            except (ValueError,KeyError,TypeError,sqlite3.Error) as ex:self.reply(400,{'error':str(ex)})
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()

if __name__=='__main__':main()
