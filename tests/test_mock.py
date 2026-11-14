import hashlib
import unittest
from fastapi.testclient import TestClient
from mock.backend import app,db,Outbound

class MockAPITests(unittest.TestCase):
    def setUp(self):
        db.captures.clear();db.outbound.clear()
        self.c=TestClient(app)
        self.h={'Authorization':'Bearer mock-test-token'}
    def test_auth_and_idempotent_capture(self):
        body={'schema_version':1,'message_id':hashlib.sha256(b'x').hexdigest(),'conversation_id':'abc','tab_id':9,'text':'line1\n```py\nprint(1)\n```','observed_at':'2026-11-14T12:00:00Z'}
        self.assertEqual(self.c.post('/api/bridge/v1/captures',json=body).status_code,401)
        a=self.c.post('/api/bridge/v1/captures',json=body,headers=self.h).json()
        b=self.c.post('/api/bridge/v1/captures',json=body,headers=self.h).json()
        self.assertEqual((a['status'],b['status']),('accepted','duplicate'))
        self.assertEqual(db.captures[body['message_id']].text,body['text'])
    def test_stage_and_ack(self):
        db.outbound['x']=Outbound(id='x',conversation_id='abc',tab_id=1,mode='STAGE_ONLY',text='hi')
        self.assertEqual(len(self.c.get('/api/bridge/v1/outbound',headers=self.h).json()['items']),1)
        r=self.c.post('/api/bridge/v1/outbound/x/ack',json={'status':'STAGED'},headers=self.h)
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.c.get('/api/bridge/v1/outbound',headers=self.h).json()['items'],[])
    def test_auto_send_requires_approval_and_is_single_use(self):
        db.outbound['x']=Outbound(id='x',conversation_id='abc',tab_id=1,mode='AUTO_SEND_APPROVED_RESULT',text='hi')
        url='/api/bridge/v1/outbound/x/claim'; body={'conversation_id':'abc','tab_id':1}
        self.assertEqual(self.c.post(url,json=body,headers=self.h).status_code,403)
        db.outbound['x'].approved_ssh_result=True
        self.assertEqual(self.c.post(url,json={**body,'tab_id':2},headers=self.h).status_code,409)
        claim=self.c.post(url,json=body,headers=self.h)
        self.assertEqual(claim.status_code,200)
        self.assertEqual(self.c.post(url,json=body,headers=self.h).status_code,403)
        self.assertEqual(self.c.post('/api/bridge/v1/outbound/x/ack',json={'status':'SUBMIT_CLICKED','claim_id':'fake'},headers=self.h).status_code,403)
        self.assertEqual(self.c.post('/api/bridge/v1/outbound/x/ack',json={'status':'SUBMIT_CLICKED','claim_id':claim.json()['claim_id']},headers=self.h).status_code,200)

if __name__=='__main__': unittest.main()
