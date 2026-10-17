import subprocess
from pathlib import Path

class GitManager:
    def __init__(self, repo_path): self.repo_path=Path(repo_path)
    def _run(self, *args):
        r=subprocess.run(['git']+list(args),cwd=str(self.repo_path),capture_output=True,text=True,encoding='utf-8',errors='ignore')
        return r.stdout.strip()
    def is_git_repo(self): return self._run('rev-parse','--is-inside-work-tree')=='true'
    def init(self): self._run('init')
    def add(self, filepath='.'): self._run('add',filepath)
    def commit(self, message="自动提交"): self._run('commit','-m',message)
    def log(self, max_count=10):
        output=self._run('log',f'--max-count={max_count}','--pretty=format:%h|%s|%ai')
        if not output: return []
        return [{'hash':p[0],'message':p[1],'date':p[2]} for line in output.split('\n') if len(p:=line.split('|',2))==3]
    def save_file(self, filepath, content, commit_message=None):
        fp=self.repo_path/filepath; fp.parent.mkdir(parents=True,exist_ok=True)
        with open(fp,'w',encoding='utf-8') as f: f.write(content)
        self.add(filepath); self.commit(commit_message or f"更新 {filepath}")
