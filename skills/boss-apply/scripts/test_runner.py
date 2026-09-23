"""Offline behavior tests. All candidate data below are synthetic."""
import json, tempfile, unittest
from pathlib import Path
from datetime import date
from runner import Engine, connect, digest, job_digest

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.e=Engine(self.root,'test-run');self.c=connect(self.root)
        self.profile={'synthetic':True}
        self.c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',('test-run',date.today().isoformat(),1,'send','running','',json.dumps(self.profile),1));self.c.commit()
        self.job={'jobId':'synthetic123','url':'https://www.zhipin.com/job_detail/synthetic123.html','title':'示例开发职位','company':'虚构测试公司','detail':'合成岗位描述','requirements':'合成要求','buttonText':'立即沟通'}
        self.key='boss:synthetic123'
        self.c.execute('INSERT INTO queue VALUES (?,?,?,?,?)',('test-run',self.key,self.job['url'],'queued',None));self.c.commit()
    def tearDown(self): self.c.close();self.temp.cleanup()
    def call(self,path,data=None):return self.e.handle(self.c,'/campaign/'+path,data or {})
    def approve(self):
        d={'status':'pass','score':90,'reasons':['虚构测试匹配'],'profileHash':digest(self.profile),'jobHash':job_digest(self.job)}
        self.c.execute('UPDATE queue SET decision=? WHERE key=?',(json.dumps(d),self.key));self.c.commit()
        return self.call('candidate',{'job':self.job})
    def test_unreviewed_no_claim(self):
        self.assertEqual(self.call('candidate',{'job':self.job})['status'],'review')
        with self.assertRaises(ValueError):self.call('claim',{'key':self.key})
    def test_dry_run_no_claim(self):
        self.c.execute("UPDATE runs SET mode='dry_run'");self.c.commit();self.approve()
        with self.assertRaises(ValueError):self.call('claim',{'key':self.key})
    def test_no_authorization(self):
        self.approve();self.c.execute('UPDATE runs SET authorized=0');self.c.commit()
        with self.assertRaises(ValueError):self.call('claim',{'key':self.key})
    def test_whitespace_does_not_invalidate(self):
        self.approve();self.job['detail']='合 成 岗位 描述'
        self.assertEqual(self.call('candidate',{'job':self.job})['status'],'pass')
    def test_changed_jd_needs_review(self):
        self.approve();self.job['detail']='不同的职责'
        self.assertEqual(self.call('candidate',{'job':self.job})['status'],'review')
        with self.assertRaises(ValueError):self.call('claim',{'key':self.key})
    def test_single_claim_and_limit(self):
        self.approve();self.assertTrue(self.call('claim',{'key':self.key})['allowed'])
        with self.assertRaises(ValueError):self.call('claim',{'key':self.key})
        self.c.rollback()
        result=self.call('result',{'key':self.key,'observed':{'jobId':'synthetic123','beforeCaptured':True,'afterCaptured':True,'beforeButton':'立即沟通','afterButton':'继续沟通'}})
        self.assertEqual(result['confirmedToday'],1);self.assertEqual(result['state'],'complete')
        with self.assertRaises(ValueError):self.call('start')
    def test_uncertain_blocks_all(self):
        self.approve();self.call('claim',{'key':self.key})
        s=self.call('result',{'key':self.key,'observed':{'jobId':'synthetic123','afterButton':'立即沟通'}})
        self.assertEqual(s['pending'],1);self.assertEqual(s['state'],'paused')
        with self.assertRaises(ValueError):self.call('start')
    def test_wrong_identity_not_confirmed(self):
        self.approve();self.call('claim',{'key':self.key})
        s=self.call('result',{'key':self.key,'observed':{'jobId':'wrong','beforeCaptured':True,'afterCaptured':True,'beforeButton':'立即沟通','afterButton':'继续沟通'}})
        self.assertEqual(s['confirmedToday'],0)
    def test_date_boundary(self):
        self.c.execute("UPDATE runs SET day='2000-01-01'");self.c.commit()
        with self.assertRaises(ValueError):self.call('next')
    def test_existing_contact_not_counted(self):
        self.job['buttonText']='继续沟通'
        self.assertEqual(self.call('candidate',{'job':self.job})['status'],'duplicate')
        self.assertEqual(self.call('status')['confirmedToday'],0)
    def test_profile_change_invalidates_review(self):
        self.approve();self.c.execute('UPDATE runs SET profile=?',(json.dumps({'different':True}),));self.c.commit()
        self.assertEqual(self.call('candidate',{'job':self.job})['status'],'review')

if __name__=='__main__':unittest.main()
