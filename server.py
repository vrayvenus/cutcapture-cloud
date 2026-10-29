import os, re, time, json, secrets, shutil, threading, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, session, jsonify, send_file, redirect, render_template_string

app=Flask(__name__,static_folder=None)
app.secret_key=os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SECURE=os.environ.get('TESTING')!='1',SESSION_COOKIE_SAMESITE='Lax',MAX_CONTENT_LENGTH=16384)
ROOT=Path(__file__).parent
DATA=Path(os.environ.get('DATA_DIR','/tmp/cutcapture'));DATA.mkdir(exist_ok=True,parents=True)
PASSWORD=os.environ.get('APP_PASSWORD','')
jobs={};lock=threading.Lock();last_start=0;login_attempts={}

def normalize(url):
 p=urlparse(url.strip())
 if p.scheme!='https' or p.username or p.password or p.port:raise ValueError('ใช้ลิงก์ HTTPS ของ YouTube')
 if p.hostname=='youtu.be':vid=p.path.strip('/')
 elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
  vid=parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else (p.path.split('/')[2] if p.path.startswith(('/shorts/','/live/')) else '')
 else:raise ValueError('รองรับเฉพาะลิงก์ YouTube รายคลิป')
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):raise ValueError('ลิงก์วิดีโอไม่ถูกต้อง')
 return 'https://www.youtube.com/watch?v='+vid

@app.before_request
def protect():
 if request.path=='/health':return
 if not PASSWORD:return 'Service requires APP_PASSWORD configuration',503
 if request.path=='/login':return
 if not session.get('ok'):
  if request.path.startswith('/api/'):return jsonify(error='กรุณาเข้าสู่ระบบ'),401
  return redirect('/login')
 if request.method=='POST' and not secrets.compare_digest(request.headers.get('X-CSRF',''),session.get('csrf','')):return jsonify(error='กรุณารีเฟรชหน้าเว็บ'),403

@app.get('/health')
def health():return jsonify(status='ok')
@app.route('/login',methods=['GET','POST'])
def login():
 error=''
 if request.method=='POST':
  # Global bounded rate limiting: avoids trusting spoofed proxy IP headers.
  now=time.time();attempts=login_attempts.setdefault('global',[]);attempts[:]=[x for x in attempts if now-x<60]
  if len(attempts)>=10:return 'Too many attempts. Please wait one minute.',429
  attempts.append(now)
  if secrets.compare_digest(request.form.get('password',''),PASSWORD):
   session.clear();session['ok']=True;session['csrf']=secrets.token_urlsafe(24);return redirect('/')
  error='รหัสเข้าใช้งานไม่ถูกต้อง'
 return render_template_string('''<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CutCapture · Sign in</title><body style="background:#101a1e;color:#edf4f1;font:16px system-ui;display:grid;place-items:center;min-height:90vh"><form method="post" style="max-width:360px;padding:32px"><h1>CutCapture Cloud</h1><p>วางลิงก์ → ดาวน์โหลดวิดีโอ → แยกภาพ</p><label>รหัสเข้าใช้งาน<input type="password" name="password" required autocomplete="current-password" style="display:block;padding:12px;margin:16px 0;width:90%"></label><button style="padding:12px 22px;background:#a7edcf;border:0;border-radius:8px">เข้าสู่ระบบ</button><p>{{error}}</p></form></body></html>''',error=error)
@app.get('/')
def index():return send_file(ROOT/'index.html')
@app.get('/<name>')
def asset(name):
 if name not in ('app.js','cloud.js','style.css','demo.mp4'):return '',404
 return send_file(ROOT/name)
@app.get('/api/session')
def get_session():return jsonify(csrf=session['csrf'])

def expire():
 now=time.time()
 for jid,j in list(jobs.items()):
  if j['state'] not in ('queued','downloading') and now-j['created']>3600:
   shutil.rmtree(DATA/jid,ignore_errors=True);del jobs[jid]

def work(jid,url):
 folder=DATA/jid;folder.mkdir();job=jobs[jid];job['state']='downloading'
 try:
  process=subprocess.run([sys.executable,str(ROOT/'worker.py'),url,str(folder)],capture_output=True,text=True,timeout=600)
  if process.returncode:
   # Preserve useful failure categories without exposing signed media URLs or raw logs.
   detail=(process.stderr or '').lower()
   reason='YouTube ไม่อนุญาตให้ดาวน์โหลดจากเซิร์ฟเวอร์นี้ หรือรูปแบบไฟล์ยังไม่รองรับ'
   if 'sign in' in detail or 'bot' in detail:reason='YouTube ขอให้ยืนยันผู้ใช้บนเซิร์ฟเวอร์นี้ จึงดาวน์โหลดไม่ได้ ระบบจะไม่ข้ามการยืนยัน'
   elif '15 minutes' in detail:reason='แผนทดสอบรองรับคลิปไม่เกิน 15 นาที'
   elif 'size limit' in detail:reason='วิดีโอเกินขนาด 180 MB ที่กำหนดไว้'
   raise ValueError(reason)
  meta=json.loads((folder/'result.json').read_text())
  video=folder/meta['file']
  if not video.is_file() or video.stat().st_size<1000:raise ValueError('ไม่ได้รับไฟล์วิดีโอที่ใช้งานได้')
  job.update(state='ready',title=meta['title'],file=meta['file'],bytes=video.stat().st_size)
 except subprocess.TimeoutExpired:job.update(state='failed',error='ดาวน์โหลดเกินเวลา 10 นาที กรุณาลองคลิปสั้นลง')
 except Exception as e:job.update(state='failed',error=str(e))
 if job['state']=='failed':shutil.rmtree(folder,ignore_errors=True)

@app.post('/api/jobs')
def create_job():
 global last_start
 try:url=normalize((request.get_json(silent=True) or {}).get('url',''))
 except (ValueError,AttributeError):return jsonify(error='กรุณาใช้ลิงก์ YouTube รายคลิปที่ถูกต้อง'),400
 with lock:
  expire()
  if any(j['state'] in ('queued','downloading') for j in jobs.values()):return jsonify(error='มีงานกำลังดาวน์โหลด กรุณารอให้เสร็จก่อน'),429
  if time.time()-last_start<30:return jsonify(error='กรุณารอ 30 วินาทีก่อนเริ่มงานใหม่'),429
  if len(jobs)>=3:return jsonify(error='เก็บผลลัพธ์ได้ครั้งละ 3 งาน กรุณาดาวน์โหลดและลบงานเก่า'),429
  jid=secrets.token_hex(16);jobs[jid]={'id':jid,'state':'queued','created':time.time()};last_start=time.time()
  threading.Thread(target=work,args=(jid,url),daemon=True).start()
 return jsonify(id=jid),202
@app.get('/api/jobs/<jid>')
def job_status(jid):
 job=jobs.get(jid)
 if not job:return jsonify(error='งานหมดอายุหรือเซิร์ฟเวอร์เริ่มใหม่ กรุณาส่งลิงก์อีกครั้ง'),404
 return jsonify({k:v for k,v in job.items() if k!='file'})
@app.get('/api/jobs/<jid>/video')
def video_file(jid):
 job=jobs.get(jid)
 if not job or job['state']!='ready':return jsonify(error='วิดีโอยังไม่พร้อม'),404
 return send_file(DATA/jid/job['file'],mimetype='video/mp4',as_attachment=request.args.get('download')=='1',download_name='CutCapture_video.mp4',conditional=True)
@app.post('/api/jobs/<jid>/delete')
def delete(jid):
 with lock:
  job=jobs.get(jid)
  if not job:return jsonify(ok=True)
  if job['state'] in ('queued','downloading'):return jsonify(error='รอให้ดาวน์โหลดเสร็จก่อนลบ'),409
  shutil.rmtree(DATA/jid,ignore_errors=True);del jobs[jid]
 return jsonify(ok=True)
@app.get('/api/jobs')
def all_jobs():
 with lock:
  expire()
  return jsonify(jobs=[{k:v for k,v in j.items() if k!='file'} for j in jobs.values()])


def janitor():
 while True:
  time.sleep(60)
  with lock:expire()
threading.Thread(target=janitor,daemon=True).start()
