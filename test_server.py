import os, tempfile, unittest
from unittest.mock import patch
os.environ.update(APP_PASSWORD='test-only',TESTING='1',DATA_DIR=tempfile.mkdtemp())
import server
class API(unittest.TestCase):
 def setUp(self):
  self.c=server.app.test_client();server.jobs.clear();server.last_start=0;server.login_attempts.clear()
 def login(self):
  self.c.post('/login',data={'password':'test-only'})
  return {'X-CSRF':self.c.get('/api/session').json['csrf']}
 def test_access(self):
  self.assertEqual(self.c.get('/health').status_code,200)
  self.assertEqual(self.c.get('/api/jobs').status_code,401)
  self.assertEqual(self.c.post('/login',data={'password':'wrong'}).status_code,200)
  self.login();self.assertEqual(self.c.post('/api/jobs',json={}).status_code,403)
 def test_urls(self):
  for url in ['http://youtube.com/watch?v=-zXND6ZBkjg','https://youtube.com.evil.test/watch?v=-zXND6ZBkjg','https://127.0.0.1','https://youtube.com:443/watch?v=-zXND6ZBkjg']:
   with self.assertRaises(ValueError):server.normalize(url)
  self.assertEqual(server.normalize('https://youtu.be/-zXND6ZBkjg'),'https://www.youtube.com/watch?v=-zXND6ZBkjg')
 def test_job_and_video(self):
  h=self.login()
  with patch('server.threading.Thread.start'):
   r=self.c.post('/api/jobs',json={'url':'https://youtu.be/-zXND6ZBkjg'},headers=h)
  self.assertEqual(r.status_code,202);jid=r.json['id']
  self.assertEqual(self.c.post('/api/jobs',json={'url':'https://youtu.be/-zXND6ZBkjg'},headers=h).status_code,429)
  folder=server.DATA/jid;folder.mkdir();(folder/'source.mp4').write_bytes(b'0'*2048)
  server.jobs[jid].update(state='ready',file='source.mp4')
  self.assertNotIn('file',self.c.get('/api/jobs/'+jid).json)
  self.assertEqual(self.c.get('/api/jobs/'+jid+'/video',headers={'Range':'bytes=0-99'}).status_code,206)
  self.assertEqual(self.c.post('/api/jobs/'+jid+'/delete',headers=h,json={}).status_code,200)
  self.assertFalse(folder.exists())
if __name__=='__main__':unittest.main()
