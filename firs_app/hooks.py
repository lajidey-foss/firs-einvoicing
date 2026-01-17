app_name = "firs_app"
app_title = "Firs App"
app_publisher = "Jide Olayinka"
app_description = "FIRS Management System"
app_email = "lajide@oasx.io"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "firs_app",
# 		"logo": "/assets/firs_app/logo.png",
# 		"title": "Firs App",
# 		"route": "/firs_app",
# 		"has_permission": "firs_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/firs_app/css/firs_app.css"
# app_include_js = "/assets/firs_app/js/firs_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/firs_app/css/firs_app.css"
# web_include_js = "/assets/firs_app/js/firs_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "firs_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "firs_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "firs_app.utils.jinja_methods",
# 	"filters": "firs_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "firs_app.install.before_install"
# after_install = "firs_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "firs_app.uninstall.before_uninstall"
# after_uninstall = "firs_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "firs_app.utils.before_app_install"
# after_app_install = "firs_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "firs_app.utils.before_app_uninstall"
# after_app_uninstall = "firs_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "firs_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"firs_app.tasks.all"
# 	],
# 	"daily": [
# 		"firs_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"firs_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"firs_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"firs_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "firs_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "firs_app.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "firs_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["firs_app.utils.before_request"]
# after_request = ["firs_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["firs_app.utils.before_job"]
# after_job = ["firs_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"firs_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                (
                    "Address-custom_state_code",
                    "Address-custom_state_name",
                    "Address-custom_country_code",
                    "Address-custom_country_name",
                    "Customer-custom_firs_info",
                    "Customer-custom_email",
                    "Customer-custom_phone",
                    "Item-custom_firs_item_type",
                    "Item-custom_hs_code",
                    "Item-custom_hs_product_description",
                    "Item-custom_firs_service_code",
                    "Item-custom_firs_service_description",
                    "Sales Invoice-custom_firs_data",
                    "Sales Invoice-custom_encrypted_qr_data",
                    "Sales Invoice-custom_qr_code_image",
                    "Sales Invoice-custom_invoice_schema",
                    "Sales Invoice-custom_irn_unix_timestamp"
                )
            ]
        ]
    }
]