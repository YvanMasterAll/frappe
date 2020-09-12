from __future__ import unicode_literals
import os
import frappe
from frappe import _
from frappe.utils import get_site_path, cint, get_url, get_backups_path
from frappe.utils.data import convert_utc_to_user_timezone
from frappe.utils.backups import new_backup
from frappe.integrations.offsite_backup_utils import get_latest_backup_file
import datetime

def get_context(context):
	def get_time(path):
		dt = os.path.getmtime(path)
		return convert_utc_to_user_timezone(datetime.datetime.utcfromtimestamp(dt)).strftime('%Y-%m-%d %H:%M')

	def get_size(path):
		size = os.path.getsize(path)
		if size > 1048576:
			return "{0:.1f}M".format(float(size) / 1048576)
		else:
			return "{0:.1f}K".format(float(size) / 1024)

	path = get_site_path('private', 'backups')
	files = [x for x in os.listdir(path) if os.path.isfile(os.path.join(path, x))]
	backup_limit = get_scheduled_backup_limit()

	if len(files) > backup_limit:
		cleanup_old_backups(path, files, backup_limit)

	files = [('/backups/' + _file,
		get_time(os.path.join(path, _file)),
		get_size(os.path.join(path, _file))) for _file in files if _file.endswith('sql.gz')]
	files.sort(key=lambda x: x[1], reverse=True)

	return {"files": files[:backup_limit]}

def get_scheduled_backup_limit():
	backup_limit = frappe.db.get_singles_value('System Settings', 'backup_limit')
	return cint(backup_limit)

def cleanup_old_backups(site_path, files, limit):
	backup_paths = []
	for f in files:
		if f.endswith('sql.gz'):
			_path = os.path.abspath(os.path.join(site_path, f))
			backup_paths.append(_path)

	backup_paths = sorted(backup_paths, key=os.path.getctime)
	files_to_delete = len(backup_paths) - limit

	for idx in range(0, files_to_delete):
		f = os.path.basename(backup_paths[idx])
		files.remove(f)

		os.remove(backup_paths[idx])

def delete_downloadable_backups():
	path = get_site_path('private', 'backups')
	files = [x for x in os.listdir(path) if os.path.isfile(os.path.join(path, x))]
	backup_limit = get_scheduled_backup_limit()

	if len(files) > backup_limit:
		cleanup_old_backups(path, files, backup_limit)

# 将数据备份到LeanCloud
def backup_to_leancloud():
	import leancloud
	# 1).获取备份文件
	if frappe.flags.create_new_backup:
		backup = new_backup(ignore_files=False, backup_path_db=None,
						backup_path_files=None, backup_path_private_files=None, force=True)
		db_filename = os.path.join(get_backups_path(), os.path.basename(backup.backup_path_db))
		site_config = os.path.join(get_backups_path(), os.path.basename(backup.site_config_backup_path))
	else:
		db_filename, site_config = get_latest_backup_file()
	# 2).判断备份文件存在
	if not os.path.exists(db_filename):
		return
	# 3).异常捕获
	try:
		# 4).初始化LeanCloud
		leancloud.init("UTrnPCDic1gQxP00htONgg5W-gzGzoHsz", "EyGwc2A7fFzq8x2UEkClXw2h")
		# 5).文件上传
		with open(db_filename, 'rb') as f:
			file = leancloud.File(os.path.basename(db_filename), f)
			file.save()
	except Exception as ex:
		frappe.log_error(title='数据库备份（LeanCloud）异常', message="%s"%ex)

@frappe.whitelist()
def schedule_files_backup(user_email):
	from frappe.utils.background_jobs import enqueue, get_jobs
	queued_jobs = get_jobs(site=frappe.local.site, queue="long")
	method = 'frappe.desk.page.backups.backups.backup_files_and_notify_user'

	if method not in queued_jobs[frappe.local.site]:
		enqueue("frappe.desk.page.backups.backups.backup_files_and_notify_user", queue='long', user_email=user_email)
		frappe.msgprint(_("Queued for backup. You will receive an email with the download link"))
	else:
		frappe.msgprint(_("Backup job is already queued. You will receive an email with the download link"))

def backup_files_and_notify_user(user_email=None):
	from frappe.utils.backups import backup
	backup_files = backup(with_files=True)
	get_downloadable_links(backup_files)

	subject = _("File backup is ready")
	frappe.sendmail(
		recipients=[user_email],
		subject=subject,
		template="file_backup_notification",
		args=backup_files,
		header=[subject, 'green']
	)

def get_downloadable_links(backup_files):
	for key in ['backup_path_files', 'backup_path_private_files']:
		path = backup_files[key]
		backup_files[key] = get_url('/'.join(path.split('/')[-2:]))
