from __future__ import unicode_literals
from frappe import _

# Change: 将用户模块加入可配置数据
def get_data():
	return [
		{
			"label": _("Core"),
			"icon": "fa fa-wrench",
			"items": []
		}
	]