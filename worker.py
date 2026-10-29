import sys,json,subprocess
from pathlib import Path
import yt_dlp
MAX=180*1024*1024

def run(url,folder):
 def match(info,*,incomplete=False):
  if info.get('is_live'):return 'Live video unsupported'
  if info.get('duration',0)>900:return '15 minutes limit'
 def hook(d):
  if d.get('downloaded_bytes',0)>MAX:raise ValueError('size limit')
  if sum(p.stat().st_size for p in folder.glob('*') if p.is_file())>MAX*2:raise ValueError('size limit')
 opts={'outtmpl':str(folder/'source.%(ext)s'),'noplaylist':True,'format':'bestvideo[ext=mp4][vcodec^=avc1][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]', 'merge_output_format':'mp4','max_filesize':MAX,'match_filter':match,'progress_hooks':[hook],'socket_timeout':20,'retries':1,'fragment_retries':1,'concurrent_fragment_downloads':1,'quiet':True,'js_runtimes':{'deno':{}}}
 with yt_dlp.YoutubeDL(opts) as ydl:
  info=ydl.extract_info(url,download=True)
 if not info:raise ValueError('No video returned')
 files=list(folder.glob('source.mp4'))
 if not files:raise ValueError('No playable mp4')
 path=files[0]
 probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30)
 duration=float(json.loads(probe.stdout)['format']['duration'])
 if duration>901:raise ValueError('15 minutes limit')
 if path.stat().st_size>MAX:raise ValueError('size limit')
 (folder/'result.json').write_text(json.dumps({'title':info.get('title','YouTube video'),'file':path.name,'duration':duration}),encoding='utf-8')
if __name__=='__main__':run(sys.argv[1],Path(sys.argv[2]))
