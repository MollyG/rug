import os.path
import subprocess

GIT='git'
GIT_DIR='.git'

class GitError(StandardError):
	pass

class InvalidRepoError(GitError):
	pass

def shell_cmd(cmd, args, cwd=None, raise_errors=True, print_output=False):
	if print_output:
		stdout = None
	else:
		stdout = subprocess.PIPE

	if cwd:
		proc = subprocess.Popen([cmd]+args, cwd=cwd, stdout=stdout, stderr=subprocess.PIPE)
	else:
		proc = subprocess.Popen([cmd]+args, stdout=stdout, stderr=subprocess.PIPE)

	(out, err) = proc.communicate()
	ret = proc.returncode
	if raise_errors:
		if ret != 0:
			raise GitError('%s %s: %s' % (cmd, ' '.join(args), err))
		elif print_output:
			return
		else:
			return out.rstrip()
	else:
		return (ret, out, err)

class Repo(object):
	def __init__(self, dir):
		d = os.path.abspath(dir)
		if not self.valid_repo(d):
			raise InvalidRepoError('not a valid git repository')
		self.dir = d
		self.bare = (self.git_cmd(['config', 'core.bare']).lower() == 'true')
		if self.bare:
			self.git_dir = self.dir
		else:
			self.git_dir = os.path.join(self.dir, GIT_DIR)

	@classmethod
	def valid_repo(cls, dir):
		#return not shell_cmd(GIT, ['remote', 'show'], cwd)[0]
		return os.path.exists(os.path.join(dir, GIT_DIR)) or \
			(os.path.exists(dir) and (shell_cmd(GIT, ['config', 'core.bare'], cwd=dir, raise_errors=False)[1].lower() == 'true'))

	@classmethod
	def clone(cls, url, dir=None, remote='origin', rev=None, local_branch=None):
		#A manual clone may be necessary to avoid git's check for an empty directory.  Currently using another workaround.
		#method = 'standard'
		method = 'manual'
		if method == 'standard':
			args = ['clone', url]
			if dir:
				args.append(dir)
		
			shell_cmd(GIT, args)
			return cls(dir)
		elif method == 'manual':
			if dir:
				if not os.path.exists(dir):
					os.makedirs(dir)
			else:
				dir = os.getcwd()

			shell_cmd(GIT, ['init'], cwd=dir)
			repo = cls(dir)
			repo.remote_add(remote, url)
			repo.fetch(remote)
			repo.remote_set_head(remote)

			if rev:
				remote_branch = '%s/%s' % (remote, rev)

			if rev and ('%s/%s' % (remote, rev) not in repo.branch_list(all=True)):
				#rev must be a commit ID or error
				repo.checkout(rev)
			else:
				if rev:
					if not local_branch:
						local_branch = rev
				else:
					remote_branch = repo.symbolic_ref('refs/remotes/%s/HEAD' % remote)
					if not local_branch:
						#remove refs/remotes/<origin>/ for the local version
						local_branch = '/'.join(remote_branch.split('/')[3:])
				print remote_branch, local_branch
				#Strange things can happen here if local_branch is 'master', since git considers
				#the repo to be on branch master, although it doesn't technically exist yet.
				#'checkout -b' doesn't quite to know what to make of this situation, so we branch
				#explicitly.  Also, checkout will try to merge local changes into the checkout
				#(which will delete everything), so we force a clean checkout
				repo.branch_create(local_branch, remote_branch)
				repo.checkout(local_branch, force=True)

			return repo

	def git_cmd(self, args, raise_errors=True, print_output=False):
		#if hasattr(self, 'git_dir'):
		#	return shell_cmd(GIT, args + ['--git-dir=%s' % self.git_dir])
		#else:
		return shell_cmd(GIT, args, cwd = self.dir, raise_errors=raise_errors, print_output=print_output)

	def head(self, full=False):
		ref = open(os.path.join(self.git_dir, 'HEAD')).read()

		if ref.startswith('ref: '):
			ref = ref[5:-1]
			if not full:
				parts = ref.split('/')
				if (len(parts) > 2) and (parts[0] == 'refs') and ((parts[1] == 'heads') or (parts[1] == 'tags')):
					ref = '/'.join(parts[2:])

		return ref

	def dirty(self, ignore_submodules=True):
		args = ['diff', 'HEAD']
		if ignore_submodules:
			args.append('--ignore-submodules')

		#TODO: doesn't account for untracked files (should it?)
		return not (len(self.git_cmd(args)) == 0)

	def remote_list(self):
		return self.git_cmd(['remote', 'show']).split()

	def remote_add(self, remote, url):
		self.git_cmd(['remote','add', remote, url])

	def remote_set_head(self, remote):
		self.git_cmd(['remote', 'set-head', remote, '-a'])

	def fetch(self, remote=None):
		args = ['fetch', '-v']
		if remote:
			args.append(remote)

		self.git_cmd(args, print_output=True)

	def branch_list(self, all=False):
		args = ['branch']
		if all:
			args.append('-a')

		return self.git_cmd(args).split()

	def branch_create(self, dst, src=None):
		args = ['branch', dst]
		if src:
			args.append(src)

		self.git_cmd(args)

	def checkout(self, branch, force=False):
		args = ['checkout', branch]
		if force:
			args.append('-f')

		self.git_cmd(args)

	def update_ref(self, ref, newval):
		self.git_cmd(['update-ref', ref, newval])

	#Branch combination operations
	def merge(self, merge_head):
		return self.git_cmd(['merge', merge_head], print_output=True)

	def rebase(self, base, onto=None):
		args = ['rebase']
		if onto:
			args.extend(['--onto', onto])
		args.append(base)

		self.git_cmd(args)

	#Query functions
	def rev_parse(self, rev):
		return self.git_cmd(['rev-parse', rev])

	def merge_base(self, rev1, rev2):
		return self.git_cmd(['merge-base', rev1, rev2])

	def symbolic_ref(self, ref):
		return self.git_cmd(['symbolic-ref', ref])

	def can_fastforward(self, merge_head, orig_head = 'HEAD'):
		return self.rev_parse(orig_head) == self.merge_base(orig_head, merge_head)

	def is_descendant(self, commit):
		return self.rev_parse(commit) in self.git_cmd(['rev-list', 'HEAD']).split()